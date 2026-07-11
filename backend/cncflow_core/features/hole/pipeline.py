"""孔特征评估流水线：校验 → 可加工性判定 → 工艺链 → 刀具属性 → SKU 匹配 → 切削参数。

供 app.py 的特征注册表调用；不依赖 Flask。
"""
from ...common import params_calc, sku_match
from ...common.case_retrieval import retrieve_process_cases
from ...common.materials import material_evidence, resolve_material
from ...common.rule_loader import load_rules
from . import machinability, process_chain, tool_attrs
from .models import HoleSpec, validate_tolerance_it

# 无刀具/参数映射的特殊阶段（磨削：文档4未提供砂轮参数库）
_NO_TOOL_PROCESSES = {"grind"}


def _thread_diameter(thread, fallback):
    if not thread:
        return fallback
    digits = "".join(ch for ch in str(thread.get("spec", "")) if ch.isdigit() or ch == ".")
    try:
        return float(digits)
    except ValueError:
        return fallback


def _machine_adjust(params: dict, machine_profile: dict) -> dict:
    if not machine_profile:
        return {"status": "not_checked", "note": "未提供机床档案，以下为理论推荐值"}
    adjusted = {}
    max_rpm = machine_profile.get("max_spindle_rpm")
    max_feed = machine_profile.get("max_feed_mm_min")
    for strategy, item in params.items():
        rpm = item.spindle_rpm
        reasons = []
        if max_rpm is not None and rpm > float(max_rpm):
            rpm = int(float(max_rpm)); reasons.append("主轴转速受机床上限限制")
        feed = round(rpm * item.feed_per_rev_mm, 1)
        if max_feed is not None and feed > float(max_feed):
            feed = float(max_feed); reasons.append("每分钟进给受机床上限限制")
        adjusted[strategy] = {"spindle_rpm": rpm, "feed_rate_mm_min": feed, "adjustments": reasons}
    return {"status": "adjusted" if any(v["adjustments"] for v in adjusted.values()) else "within_limits",
            "strategies": adjusted}


def run(payload: dict, conn) -> dict:
    """执行孔评估。payload 为请求体 dict；conn 为 SQLite 连接。非法输入抛 ValueError。"""
    feature = payload.get("feature") or {}
    hole = HoleSpec.from_dict(feature)
    material_profile = resolve_material(conn, payload.get("material_code") or payload.get("material"))
    if not material_profile.planning_enabled:
        raise ValueError(
            f"材料 {material_profile.canonical_name} 已收录，但孔加工规则尚未验证；"
            f"planning_status={material_profile.planning_status}"
        )
    material = material_profile.family
    tolerance_it = validate_tolerance_it(payload.get("tolerance_it"))
    roughness_ra = payload.get("roughness_ra")
    if roughness_ra is not None:
        roughness_ra = float(roughness_ra)

    strategy = payload.get("strategy", "both")
    if strategy not in {"stable", "aggressive", "both"}:
        raise ValueError("strategy 须为 stable/aggressive/both")
    machine_profile = payload.get("machine_profile") or {}
    if not isinstance(machine_profile, dict):
        raise ValueError("machine_profile 须为对象")

    result = machinability.evaluate(hole, material, tolerance_it)
    evidence = material_evidence(conn, material_profile.material_code)
    case_refs = retrieve_process_cases(
        conn, material_code=material_profile.material_code, material_family=material,
        diameter_mm=hole.diameter_mm, depth_mm=hole.depth_mm, hole_type=hole.hole_type,
        tolerance_it=tolerance_it, roughness_ra=roughness_ra,
        thread_spec=(hole.thread or {}).get("spec"),
    )

    # 四级（不建议加工）：前置风控拦截，不生成工艺链
    if result.level >= 4:
        return {
            "machinability": result.to_dict(),
            "material_profile": material_profile.to_dict(),
            "tool_chain": [],
            "case_references": case_refs,
            "evidence": evidence,
            "match_status": "不适用（四级：不建议加工，报废率极高）",
        }

    chain = process_chain.generate_chain(hole, material, tolerance_it, roughness_ra)
    has_finishing = any(
        step["process"] in tool_attrs.FINISH_PROCESSES or step["process"] in _NO_TOOL_PROCESSES
        for step in chain
    )

    tool_steps = []
    missing = []
    last_cut_d = None
    for idx, step in enumerate(chain, start=1):
        proc = step["process"]
        entry = {"step": idx, "process": proc, "cycle": step["cycle"]}

        if proc in _NO_TOOL_PROCESSES:
            entry.update(
                tool_attrs=None,
                sku_candidates=[],
                match_status="unsupported",
                note="磨削阶段（Ra≤0.4 放弃切削）：需砂轮与磨削夹具，超出本期刀具库/参数库范围",
                params=None,
            )
            tool_steps.append(entry)
            continue

        selection_d = _thread_diameter(hole.thread, hole.diameter_mm) if proc in {"tap", "thread_mill"} else hole.diameter_mm
        requirement = tool_attrs.derive_requirement(
            proc, selection_d, hole.depth_mm / selection_d, material, tolerance_it, has_finishing
        )
        attrs = requirement.preferred_attrs
        candidates = sku_match.match_candidates(
            conn, requirement, tool_attrs.is_relaxed(proc),
            thread_spec=(hole.thread or {}).get("spec") if proc in {"tap", "thread_mill"} else None,
        )
        sku_candidates = [c["candidate_id"] for c in candidates if c["candidate_type"] == "sku"]
        if sku_candidates:
            status = "matched"
            match_tier = candidates[0]["tier"]
            detail = None
        elif candidates:
            status = "missing"  # 保持 v1 旧字段语义；新层级见 match_tier/candidates
            match_tier = "catalog_only"
            detail = "仅找到标准目录规格，缺少已确认的库存 SKU"
            missing.append(f"step{idx} {proc}: {detail}")
        else:
            status = "missing"  # 保持 v1 兼容
            match_tier = "custom_required"
            detail = (
                f"无满足约束的刀具：{attrs.category} D范围="
                f"{requirement.diameter_min_mm}~{requirement.diameter_max_mm}mm，需定制或调整工艺"
            )
            missing.append(f"step{idx} {proc}: {detail}")
            candidates = [{"candidate_type": "custom", "candidate_id": None, "tier": "custom_required",
                           "verification_required": True, "differences": [detail], "in_stock": False,
                           "is_mock": False, "source": None}]

        deep = hole.h_over_d > load_rules("hole/process_chain.yaml")["deep_hole"]["g83_min_hd"]
        selected = candidates[0]
        selected_attrs = selected.get("tool_attrs", attrs.to_dict())
        params_d = selected_attrs.get("nominal_diameter_mm") or selection_d
        params = params_calc.calc_params(proc, material, selected_attrs.get("base_material", attrs.base_material), params_d, deep=deep)
        if params and proc in tool_attrs.FINISH_PROCESSES and last_cut_d is not None and params_d >= last_cut_d:
            radial_ap = round((params_d - last_cut_d) / 2.0, 3)
            for value in params.values():
                value.cutting_depth = f"{radial_ap:.3f} (单边，按相邻工序刀径计算)"
        if params and strategy != "both":
            params = {strategy: params[strategy]}

        step_warnings = []
        if selected.get("is_mock"):
            step_warnings.append("当前候选为模拟 SKU，仅用于开发/演示，不代表真实库存")
        if params and any("高压内冷" in value.coolant for value in params.values()):
            if machine_profile:
                pressure = machine_profile.get("coolant_pressure_bar")
                through = machine_profile.get("through_spindle_coolant")
                if through is False or (pressure is not None and float(pressure) < 30):
                    step_warnings.append("机床内冷能力不足：该工序要求高压内冷≥30 bar")
            else:
                step_warnings.append("高压内冷要求尚未经过机床能力校核")

        entry.update(
            tool_attrs=attrs.to_dict(),
            requirement=requirement.to_dict(),
            candidates=candidates,
            selected_candidate=selected,
            sku_candidates=sku_candidates,
            match_status=status,
            match_tier=match_tier,
            params={k: v.to_dict() for k, v in params.items()} if params else None,
            machine_adjusted=_machine_adjust(params, machine_profile) if params else None,
            parameter_basis={"authority": "verified_rule", "source": "4-加工参数知识库（RAG优化版）.docx"}
            if params else None,
            warnings=step_warnings,
        )
        if status != "matched":
            entry["note"] = detail
        if params is None:
            entry["note"] = entry.get("note") or "参数库未覆盖该工序（文档4范围外），待知识库补充"
        tool_steps.append(entry)
        if proc in tool_attrs.ROUGH_PROCESSES | tool_attrs.FINISH_PROCESSES:
            last_cut_d = params_d

    top_warnings = [] if machine_profile else ["未提供机床档案，参数未经过设备能力校核"]
    if any(step.get("selected_candidate", {}).get("is_mock") for step in tool_steps):
        top_warnings.append("方案包含模拟 SKU，投产前必须替换为已确认的真实库存")
    return {
        "machinability": result.to_dict(),
        "material_profile": material_profile.to_dict(),
        "tool_chain": tool_steps,
        "case_references": case_refs,
        "evidence": evidence,
        "warnings": top_warnings,
        "match_status": "全匹配成功" if not missing else "部分匹配失败：" + "；".join(missing),
    }
