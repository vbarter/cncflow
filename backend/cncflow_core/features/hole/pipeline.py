"""孔特征评估流水线：校验 → 可加工性判定 → 工艺链 → 刀具属性 → SKU 匹配 → 切削参数。

供 app.py 的特征注册表调用；不依赖 Flask。
"""
from ...common import params_calc, sku_match
from ...common.rule_loader import load_rules
from . import machinability, process_chain, tool_attrs
from .models import HoleSpec, validate_material, validate_tolerance_it

# 无刀具/参数映射的特殊阶段（磨削：文档4未提供砂轮参数库）
_NO_TOOL_PROCESSES = {"grind"}


def run(payload: dict, conn) -> dict:
    """执行孔评估。payload 为请求体 dict；conn 为 SQLite 连接。非法输入抛 ValueError。"""
    feature = payload.get("feature") or {}
    hole = HoleSpec.from_dict(feature)
    material = validate_material(payload.get("material"))
    tolerance_it = validate_tolerance_it(payload.get("tolerance_it"))
    roughness_ra = payload.get("roughness_ra")
    if roughness_ra is not None:
        roughness_ra = float(roughness_ra)

    result = machinability.evaluate(hole, material, tolerance_it)

    # 四级（不建议加工）：前置风控拦截，不生成工艺链
    if result.level >= 4:
        return {
            "machinability": result.to_dict(),
            "tool_chain": [],
            "match_status": "不适用（四级：不建议加工，报废率极高）",
        }

    chain = process_chain.generate_chain(hole, material, tolerance_it, roughness_ra)
    has_finishing = any(
        step["process"] in tool_attrs.FINISH_PROCESSES or step["process"] in _NO_TOOL_PROCESSES
        for step in chain
    )

    tool_steps = []
    missing = []
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

        attrs = tool_attrs.derive(proc, hole.diameter_mm, hole.h_over_d, material, tolerance_it, has_finishing)
        skus, status, detail = sku_match.match_with_status(conn, attrs, tool_attrs.is_relaxed(proc))
        if status == "missing":
            missing.append(f"step{idx} {proc}: {detail}")

        deep = hole.h_over_d > load_rules("hole/process_chain.yaml")["deep_hole"]["g83_min_hd"]
        params_d = attrs.nominal_diameter_mm or hole.diameter_mm
        params = params_calc.calc_params(proc, material, attrs.base_material, params_d, deep=deep)

        entry.update(
            tool_attrs=attrs.to_dict(),
            sku_candidates=skus,
            match_status=status,
            params={k: v.to_dict() for k, v in params.items()} if params else None,
        )
        if status == "missing":
            entry["note"] = detail
        if params is None:
            entry["note"] = entry.get("note") or "参数库未覆盖该工序（文档4范围外），待知识库补充"
        tool_steps.append(entry)

    return {
        "machinability": result.to_dict(),
        "tool_chain": tool_steps,
        "match_status": "全匹配成功" if not missing else "部分匹配失败：" + "；".join(missing),
    }
