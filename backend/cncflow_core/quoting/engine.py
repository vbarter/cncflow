"""报价引擎：跑特征管道 + 夹具 + 体积 + 滑轴 → 始终出报价。"""
import math

from ..factory.store import get_config
from ..features.face import pipeline as face_pipeline
from ..features.fixture import pipeline as fixture_pipeline
from ..features.hole import pipeline as hole_pipeline
from ..features.pocket import pipeline as pocket_pipeline
from ..features.step import pipeline as step_pipeline
from ..features.surface import pipeline as surface_pipeline
from ..features.thread import pipeline as thread_pipeline
from . import (
    confidence, dedup, equipment, hole_time, mill_time, process_edits, programming,
    risk_dimensions, sequence, slider, volume,
)

PIPELINES = {
    "hole": hole_pipeline.run,
    "face": face_pipeline.run,
    "pocket": pocket_pipeline.run,
    "slot": pocket_pipeline.run,
    "thread": thread_pipeline.run,
    "surface": surface_pipeline.run,
    "step": step_pipeline.run,
}

DIFF_MIN = {"D1": 2.0, "D2": 6.0, "D3": 15.0, "D4": 25.0, "NA": 20.0, 1: 2.0, 2: 6.0, 3: 15.0, 4: 25.0}
DIFF_FACTOR = {"D3": 1.3, "D4": 1.8, 3: 1.3, 4: 1.8}
STEP_PARAMS = ("formula", "n", "f", "cut", "passes", "t_min", "t_max", "status")
DIAMETER_MISMATCH_RISK = "刀径非全等，需工艺确认"
FEATURE_NAME = {
    "hole": "孔",
    "face": "面",
    "pocket": "型腔",
    "slot": "槽",
    "thread": "螺纹",
    "surface": "曲面",
    "step": "台阶",
}


def suggested_lead_time_days(hours_total: float, setup_count: int, batch: int) -> int:
    """建议交期：8 小时工作日 + 每次装夹 1 天 + 批量级数，至少 1 天。"""
    batch = max(int(batch or 1), 1)
    batch_days = math.ceil(math.log10(batch)) if batch > 1 else 0
    days = math.ceil(float(hours_total or 0) * 60 / 480) + int(setup_count or 0) + batch_days
    return max(days, 1)


def _copy_step_params(dst: dict, src: dict | None) -> None:
    """把工步中间量提到 process_sequence 顶层；已有 n_act 只做 n 别名。"""
    src = dict(src or {})
    if src.get("n") is None and src.get("n_act") is not None:
        src["n"] = src["n_act"]
    for key in STEP_PARAMS:
        if key in src:
            dst[key] = src[key]
        else:
            dst.setdefault(key, "ok" if key == "status" else None)


def _dimension(payload: dict, *keys: str, default: float) -> float:
    """关键尺寸缺失仍出价；D9 使用原 payload 记录门禁。"""
    for key in keys:
        value = payload.get(key)
        if value in (None, ""):
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number > 0:
            return number
    return default


def _validation(seq: list) -> dict:
    """防错块：只收 t 对表结果，独立于 risk，不含九维 rule_id。"""
    items = []
    for step in seq:
        status = step.get("status") or "ok"
        if status == "ok":
            continue
        items.append({
            "order": step.get("order"),
            "process": step.get("process"),
            "status": status,
            "t_min": step.get("t_min"),
            "t_max": step.get("t_max"),
        })
    return {"ok": not items, "items": items}


def _labor_trace(
    plans: list,
    seq: list,
    picked: dict,
    hourly: float,
    machining_sub: float,
    setup_min: float,
    setup_fee_time: float,
    setup_amort: float,
    setup_ui: float,
) -> dict:
    """只组织展示所需的工时来源；不参与任何报价计算。"""
    groups = []
    groups_by_type = {}
    feature_types = {}
    for plan in plans:
        feature_id = plan["feature_id"]
        feature_type = plan["type"]
        feature_types[feature_id] = feature_type
        group = groups_by_type.get(feature_type)
        if group is None:
            group = {
                "feature_type": feature_type,
                "name": FEATURE_NAME.get(feature_type, feature_type or "特征"),
                "quantity": 0,
                "feature_ids": [],
                "operations": [],
            }
            groups_by_type[feature_type] = group
            groups.append(group)
        group["quantity"] += 1
        group["feature_ids"].append(feature_id)

    for step in seq:
        feature_type = feature_types.get(step.get("feature_id"))
        group = groups_by_type.get(feature_type)
        if group is None:
            continue
        group["operations"].append({
            "name": step.get("name") or step.get("process") or "工序",
            "equipment_name": picked.get("model") or picked.get("type") or "—",
            "tool_sku": step.get("sku"),
            "minutes": round(float(step.get("minutes") or 0), 4),
            "hourly_rate": round(hourly, 2),
            "cost": round(float(step.get("amount") or 0), 2),
        })

    operation_cost = round(sum(
        operation["cost"]
        for group in groups
        for operation in group["operations"]
    ), 2)
    return {
        "groups": groups,
        "operation_cost": operation_cost,
        # 现有 machining 还含 TOOLCHG/RAPID；按冻结 UI 不虚构额外工序。
        "air_cut_and_tool_change_cost": round(round(machining_sub, 2) - operation_cost, 2),
        "machining_total": round(machining_sub, 2),
        "changeover": {
            "minutes": round(setup_min, 2),
            "equipment_name": picked.get("model") or picked.get("type") or "—",
            "hourly_rate": round(hourly, 2),
            "labor_cost": round(setup_fee_time, 2),
            "machine_setup_cost": round(setup_amort, 2),
            "cost": round(setup_ui, 2),
        },
        "total": round(round(machining_sub, 2) + round(setup_ui, 2), 2),
    }


def _nearest_sku(conn, step: dict):
    """非标孔径库存无全等时，同大类就近选一把在库 SKU。"""
    attrs = step.get("tool_attrs") or {}
    cat = attrs.get("category")
    if not cat:
        return None
    d = attrs.get("nominal_diameter_mm")
    if d is None:
        row = conn.execute(
            "SELECT sku FROM tools WHERE category=? AND in_stock=1 ORDER BY sku LIMIT 1", (cat,),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT sku FROM tools WHERE category=? AND in_stock=1 "
            "ORDER BY ABS(diameter_mm-?) ASC, sku LIMIT 1", (cat, float(d)),
        ).fetchone()
    return row["sku"] if row else None


def _diameter_selection(conn, step: dict) -> dict | None:
    """按目标刀径全等优先，否则返回同大类最近的在库 SKU。"""
    attrs = step.get("tool_attrs") or {}
    category = attrs.get("category")
    target = attrs.get("nominal_diameter_mm")
    if not category or target is None:
        return None
    target = float(target)
    rows = conn.execute(
        "SELECT sku,diameter_mm,structure,base_material,coating,precision_grade,is_mock,source "
        "FROM tools WHERE category=? AND in_stock=1 "
        "ORDER BY ABS(diameter_mm-?) ASC, sku",
        (category, target),
    ).fetchall()
    if not rows:
        return None

    row = rows[0]
    preferred = step.get("selected_candidate") or {}
    preferred_sku = preferred.get("candidate_id") if preferred.get("candidate_type") == "sku" else None
    best_distance = abs(float(row["diameter_mm"]) - target)
    row = next(
        (
            candidate
            for candidate in rows
            if candidate["sku"] == preferred_sku
            and abs(abs(float(candidate["diameter_mm"]) - target) - best_distance) < 0.001
        ),
        row,
    )
    actual = float(row["diameter_mm"])
    match_status = "exact" if abs(actual - target) < 0.001 else "nearest"
    if match_status == "exact":
        reason = f"库存刀径全等：目标 Ø{target:g}mm，选用 {row['sku']} Ø{actual:g}mm"
        differences = []
    else:
        reason = (
            f"库存无 Ø{target:g}mm 全等刀具；选用最近在库 "
            f"{row['sku']} Ø{actual:g}mm，需工艺确认"
        )
        differences = [f"刀径 {actual:g}mm（目标 {target:g}mm）"]

    selected_attrs = {
        **attrs,
        "nominal_diameter_mm": actual,
        "structure": row["structure"],
        "base_material": row["base_material"],
        "coating": row["coating"],
        "precision_grade": row["precision_grade"],
    }
    return {
        "sku": row["sku"],
        "target_diameter_mm": target,
        "tool_diameter_mm": actual,
        "match_status": match_status,
        "match_reason": reason,
        "candidate": {
            "candidate_type": "sku",
            "candidate_id": row["sku"],
            "tier": match_status,
            "match_status": match_status,
            "match_reason": reason,
            "is_mock": bool(row["is_mock"]),
            "in_stock": True,
            "differences": differences,
            "verification_required": bool(row["is_mock"]) or match_status == "nearest",
            "source": row["source"],
            "tool_attrs": selected_attrs,
        },
    }


def _uses_exact_diameter_policy(feature_type: str, step: dict) -> bool:
    """冻结 MVP：只接孔钻、槽铣刀、螺纹底孔钻和丝锥；面铣保持原规则。"""
    process = step.get("process")
    if feature_type == "hole":
        return process == "drill"
    if feature_type in {"pocket", "slot"}:
        return process in {
            "rough_pocket", "semi_finish_pocket", "finish_pocket", "rest_mill",
        }
    if feature_type == "thread":
        return process in {"drill", "tap"}
    return False


def _material_row(material: str, factory: dict, payload: dict):
    from ..factory.store import resolve_material_code
    codes = []
    for raw in (payload.get("material_code"), material):
        if not raw:
            continue
        codes.append(raw)
        resolved = resolve_material_code(raw)
        if resolved and resolved not in codes:
            codes.append(resolved)
    for row in factory.get("material_prices") or []:
        if row.get("material_code") in codes:
            return row
    return None


def _density(material: str, factory: dict, payload: dict | None = None) -> float:
    row = _material_row(material, factory, payload or {})
    if row and row.get("density_g_cm3"):
        return float(row["density_g_cm3"])
    from ..features.fixture.pipeline import _mat
    from ..factory.store import resolve_material_code
    return float(_mat(resolve_material_code(material) or material)["density"])


def _price(material: str, factory: dict, payload: dict):
    if payload.get("price_per_kg") is not None:
        return float(payload["price_per_kg"]), float(payload.get("scrap_price_per_kg") or 0)
    row = _material_row(material, factory, payload)
    if row:
        return float(row["price_per_kg"]), float(row.get("scrap_price_per_kg") or 0)
    defaults = {"铝合金": 25, "钢": 8, "普通碳钢": 8, "不锈钢": 30, "钛合金": 200, "淬硬钢": 15, "铸铁": 6, "铜合金": 50}
    return float(defaults.get(material, 25)), 0.0


def _feature_minutes(result: dict, ftype: str) -> tuple[float, object, bool]:
    if ftype == "surface":
        level = (result.get("difficulty") or {}).get("level") or "D1"
        return float(result.get("manual_hours") or 0) * 60, level, False
    if ftype == "hole":
        level = (result.get("machinability") or {}).get("level", 1)
        na = int(level or 1) >= 4
        timed = result.get("time") or {}
        if timed.get("total_min") is not None:
            return float(timed["total_min"]), level, na
        return DIFF_MIN.get(level, 6.0), level, na
    diff = result.get("difficulty") or {}
    level = diff.get("level", "D1")
    timed = result.get("time") or {}
    if timed.get("total_min") is not None:
        return float(timed["total_min"]), level, bool(diff.get("na"))
    return DIFF_MIN.get(level, 6.0), level, bool(diff.get("na"))


def quote(payload: dict, conn, rules_version: str = "") -> dict:
    material = payload.get("material") or payload.get("material_code") or "铝合金"
    factory = get_config(conn)
    settings = factory["settings"]
    raw_features = payload.get("features")
    features = list(raw_features) if isinstance(raw_features, list) else []
    slide = slider.resolve(payload.get("slider") or "标准", material, features)
    stock = payload.get("blank_type") or payload.get("stock_type") or settings.get("blank_type") or "板料"
    is_bar = stock in {"棒料", "棒", "bar"}
    L = _dimension(payload, "length", "L", default=1.0)
    D = _dimension(payload, "diameter", "D", "width", "W", default=1.0)
    H = _dimension(payload, "height", "H", default=0.0 if is_bar else 1.0)
    dens = _density(material, factory, payload)
    vol = volume.compute(stock, L, D, H, density=dens, v_part_cad=payload.get("v_part_cad"))
    price, scrap_price = _price(material, factory, payload)
    mat_cost = vol["blank_weight_kg"] * price - vol["scrap_weight_kg"] * scrap_price
    material_cost_breakdown = {
        "density_g_cm3": dens,
        "blank_price_per_kg": price,
        "scrap_price_per_kg": scrap_price,
        "blank_volume_mm3": vol["v_blank_mm3"],
        "blank_weight_kg": vol["blank_weight_kg"],
        "part_volume_mm3": vol["v_part_mm3"],
        "part_weight_kg": round(vol["v_part_mm3"] * dens / 1_000_000, 5),
        "scrap_volume_mm3": vol["v_removed_mm3"],
        "scrap_weight_kg": vol["scrap_weight_kg"],
        "blank_cost": round(vol["blank_weight_kg"] * price, 2),
        "scrap_recycle_cost": round(vol["scrap_weight_kg"] * scrap_price, 2),
        "net_material_cost": round(mat_cost, 2),
    }

    features = dedup.absorb_holes(features)
    picked = equipment.select(factory, payload, features, L, D, H)
    rate = picked["rate"]
    hourly = float(payload.get("hourly_rate") or rate["hourly_rate"])
    batch = int(payload.get("batch_size") or settings.get("batch_size") or 1)
    repeat = bool(payload.get("is_repeat_order"))
    profit_pct = float(payload.get("profit_pct") if payload.get("profit_pct") is not None else settings.get("profit_pct") or 15)
    floor = float(payload.get("floor_charge") if payload.get("floor_charge") is not None else settings.get("floor_charge") or 0)
    inspect = float(settings.get("inspect_fee") or 60)

    ops, plans, seq, tags = [], [], [], []
    worst = "D1"
    order = {"D1": 1, "D2": 2, "D3": 3, "D4": 4, "NA": 5, 1: 1, 2: 2, 3: 3, 4: 4}
    cut_min = 0.0
    n_tools = 0
    for i, feat in enumerate(features, 1):
        ftype = feat.get("type")
        fn = PIPELINES.get(ftype)
        if fn is None:
            continue
        plan_payload = dict(payload)
        plan_payload["feature"] = feat
        plan_payload["material"] = material
        try:
            result = fn(plan_payload, conn)
        except ValueError as exc:
            result = {"error": str(exc), "difficulty": {"level": "NA", "na": True}, "risk_tags": [str(exc)]}
        if ftype == "hole" and not result.get("error"):
            result["time"] = hole_time.compute(result, factory, material, slide)
            result.setdefault("risk_tags", []).extend(result["time"].get("tags") or [])
        elif ftype in {"face", "pocket", "slot", "thread", "step"} and not result.get("error"):
            result["time"] = mill_time.compute(ftype, feat, result, factory, material, slide)
            result.setdefault("risk_tags", []).extend(result["time"].get("tags") or [])
        mins, level, na = _feature_minutes(result, ftype)
        cut_min += mins
        steps_n = max(len(result.get("process_chain") or result.get("tool_chain") or [1]), 1)
        if ftype not in {"hole", "face", "pocket", "slot", "thread", "step"}:
            n_tools += steps_n
        ops.append({"op": ftype, "minutes": mins, "na": na})
        fid = feat.get("id") or feat.get("feature_id") or f"{ftype}-{i}"
        plans.append({"feature_id": fid, "type": ftype, "plan": result})
        steps = result.get("tool_chain") or result.get("process_chain") or []
        timed_steps = (result.get("time") or {}).get("steps") or []
        for si, step in enumerate(steps):
            selection = _diameter_selection(conn, step) if _uses_exact_diameter_policy(ftype, step) else None
            if selection:
                sku = selection["sku"]
                match_status = selection["match_status"]
                step["selected_candidate"] = selection["candidate"]
                step["match_status"] = match_status
                step["match_tier"] = match_status
                step["match_reason"] = selection["match_reason"]
                step["tool_diameter_mm"] = selection["tool_diameter_mm"]
                step["selection_target_diameter_mm"] = selection["target_diameter_mm"]
                if match_status == "nearest":
                    step["risk_tags"] = list(dict.fromkeys([
                        *(step.get("risk_tags") or []),
                        DIAMETER_MISMATCH_RISK,
                    ]))
                    result.setdefault("risk_tags", []).extend([
                        DIAMETER_MISMATCH_RISK,
                        selection["match_reason"],
                    ])
            else:
                sel = step.get("selected_candidate") or {}
                sku = sel.get("candidate_id") if sel.get("candidate_type") == "sku" else None
                if not sku:
                    sku = next((c for c in (step.get("sku_candidates") or []) if c), None)
                if not sku:
                    sku = _nearest_sku(conn, step)
                match_status = (
                    step.get("match_status")
                    if sel.get("candidate_type") == "sku"
                    else ("nearest" if sku else step.get("match_status"))
                )
            seq.append({
                "order": len(seq) + 1,
                "feature_id": fid,
                "process": step.get("process"),
                "cycle": step.get("cycle"),
                "sku": sku,
                "side": step.get("side"),
                "match_status": match_status,
                "tool": sku or step.get("cycle") or step.get("process") or "—",
            })
            for key in (
                "match_reason", "tool_diameter_mm", "selection_target_diameter_mm", "risk_tags",
            ):
                if step.get(key) is not None:
                    seq[-1][key] = step[key]
            if step.get("name"):
                seq[-1]["name"] = step["name"]
            if si < len(timed_steps):
                ts = timed_steps[si]
                seq[-1]["minutes"] = round(float(ts["t_step"]), 4)
                seq[-1]["time"] = ts
                _copy_step_params(seq[-1], ts)
            else:
                _copy_step_params(seq[-1], None)
        tags.extend(result.get("risk_tags") or [])
        if order.get(level, 1) > order.get(worst, 1):
            worst = level

    feat_types = {p["feature_id"]: p["type"] for p in plans}
    seq = sequence.sort_steps(seq, feat_types)
    seq = dedup.merge_chamfers(seq)
    seq, process_overrides, sequence_inversions = process_edits.apply(
        seq, payload.get("process_overrides"),
    )
    if seq:
        cut_min = sum(float(step.get("minutes") or 0) for step in seq)
    # 人工路线偏离系统推荐顺序时计入最小切换/复核工时；原路线保持零调整。
    sequence_adjustment_min = sequence_inversions * 0.5
    cut_min += sequence_adjustment_min

    fixture_feat = {
        "type": "fixture", "length": L,
        "width": payload.get("width") or D, "depth": H or D,
        "features": features,
    }
    fixture_payload = {
        **payload, "feature": fixture_feat, "material": material,
        "batch_size": batch, "is_repeat_order": repeat,
        "ignore_available_machines": settings.get("ignore_available_machines"),
    }
    fixture_payload.pop("hourly_rate", None)
    fixture = fixture_pipeline.run(fixture_payload, conn)
    if not fixture.get("is_machinable"):
        tags.append("设备不匹配")
    if not picked["matched"]:
        tags.append("设备不匹配")

    factor = DIFF_FACTOR.get(worst, 1.0)
    cut_hours = cut_min / 60
    toolchg_min = n_tools * (5 / 60) * slide["toolchg"]  # 5s → min? 5 seconds = 5/60 min
    toolchg_min = n_tools * (5 / 60.0) * slide["toolchg"]
    rapid_min = max(n_tools, 1) * (5 / 60.0) * slide["rapid"]
    setup_min = float(fixture.get("setup_time_total") or 0) * slide["setup"]
    setups = int(fixture.get("setup_count") or 1)
    setup_fee = float(rate.get("setup_fee") or 0) * setups
    if batch == 1:
        setup_amort = setup_fee
    elif batch <= 5:
        setup_amort = setup_fee / batch
    elif batch <= 20:
        setup_amort = setup_fee / batch * 1.2
    else:
        setup_amort = setup_fee / batch * 1.5
    programming_time = programming.calculate_time(
        features,
        fixture.get("setup_count"),
        picked.get("axes"),
    )
    programming_cost = programming.calculate_cost(
        programming_time["programming_time"],
        machine_axes=picked.get("axes"),
        rate_row=rate,
        batch_size=batch,
        is_repeat_order=repeat,
    )
    prog = programming_cost["programming_cost_per_piece"]
    cut_fee = cut_hours * hourly * factor
    toolchg_fee = (toolchg_min / 60) * hourly
    setup_fee_time = (setup_min / 60) * hourly
    rapid_fee = (rapid_min / 60) * hourly
    if not fixture.get("is_fixture_needed") or not fixture.get("fixture_count"):
        fix_fee = 0
    else:
        fix_fee = (
            float(fixture.get("fixture_material_cost") or 0)
            + float(fixture.get("fixture_processing_cost") or 0)
        )
    toolwear = cut_hours * 15
    machining_sub = cut_fee + toolchg_fee + rapid_fee
    setup_ui = setup_fee_time + setup_amort
    base = mat_cost + machining_sub + setup_ui + fix_fee + prog + inspect + toolwear
    scrap_fee = base * float(slide["scrap_rate"])
    cost = base + scrap_fee
    amount = max(cost * (1 + profit_pct / 100), floor)
    floor_applied = amount > cost * (1 + profit_pct / 100) - 1e-9 and amount == floor or amount >= floor and floor > cost * (1 + profit_pct / 100)
    if floor > cost * (1 + profit_pct / 100):
        amount = floor
        floor_applied = True
    else:
        amount = cost * (1 + profit_pct / 100)
        floor_applied = False
    profit = amount - cost
    hours_min = cut_min + toolchg_min + setup_min + rapid_min
    hours_total = round(hours_min / 60.0, 1)
    hours = {
        "cut": round(cut_min / 60.0, 4),
        "toolchg": round(toolchg_min / 60.0, 4),
        "setup": round(setup_min / 60.0, 4),
        "rapid": round(rapid_min / 60.0, 4),
        "total": hours_total,
    }
    suggested_days = suggested_lead_time_days(hours["total"], setups, batch)
    legacy_conf = confidence.score(ops)
    tags.extend(tag for tag in legacy_conf["tags"] if tag != "禁止给客户")
    tags = [tag for tag in tags if tag not in {"低于下限", "需人工复核"}]
    tags.extend(
        step["status"]
        for step in seq
        if step.get("status") in {"低于下限", "需人工复核"}
    )
    if any(op["na"] for op in ops):
        tags.append("超出常规边界")

    STEP_NAME = {
        "spot_drill": "点钻", "drill": "钻孔", "gun_drill": "枪钻", "u_drill": "U钻",
        "ream": "铰孔", "bore": "镗孔", "semi_bore": "半精镗", "fine_bore": "精镗",
        "tap": "攻丝", "chamfer": "倒角", "face": "铣面", "mill": "铣削",
        "flat_bottom_mill": "修底", "grind": "磨削",
        "rough_pocket": "粗铣", "semi_finish_pocket": "半精铣", "finish_pocket": "精铣",
        "rest_mill": "清角", "pocket_mill": "铣槽",
    }
    if seq:
        per_min = cut_min / len(seq)
        per_amt = cut_fee / len(seq)
        priced_minutes = sum(float(s.get("minutes") or 0) for s in seq)
        for s in seq:
            proc = s.get("process") or s.get("op")
            s.setdefault("name", STEP_NAME.get(proc, proc or "工序"))
            s.setdefault("tool", s.get("sku") or s.get("tool") or s.get("cycle") or proc or "—")
            s.setdefault("minutes", round(per_min, 2))
            if priced_minutes > 0:
                s["amount"] = round(cut_fee * float(s.get("minutes") or 0) / priced_minutes, 2)
            else:
                s["amount"] = round(per_amt, 2)
            _copy_step_params(s, s.get("time"))

    labor_trace = _labor_trace(
        plans,
        seq,
        picked,
        hourly,
        machining_sub,
        setup_min,
        setup_fee_time,
        setup_amort,
        setup_ui,
    )

    equipment_info = {
        "model": picked.get("model"),
        "type": picked.get("type"),
        "axes": picked.get("axes"),
        "hourly_rate": picked.get("hourly_rate"),
    }
    deductions = risk_dimensions.collect(
        payload,
        seq,
        volume=vol,
        cut_minutes=cut_min,
        quote_amount=amount,
        ui_cost={
            "material": mat_cost,
            "machining": machining_sub,
            "fixture": fix_fee,
        },
        risk_tags=tags,
        equipment=equipment_info,
        hours_cut=cut_hours,
    )
    confidence_value = risk_dimensions.confidence_from(deductions)
    risk_level, customer_forbidden = confidence.classify(confidence_value)
    has_d9 = any(item["dimension"] == "D9" for item in deductions)
    if has_d9:
        tags.append("D9关键字段缺失")
        customer_forbidden = True
        if risk_level not in {"critical"}:
            risk_level = "high"
    if any(op["na"] for op in ops) and risk_level not in {"critical"}:
        risk_level = "high"
    if any("深孔" in str(tag) for tag in tags) and risk_level in {"low", "medium_low", "medium"}:
        risk_level = "high"

    items = [
        {"code": "MAT", "amount": round(mat_cost, 2)},
        {"code": "CUT", "amount": round(cut_fee, 2)},
        {"code": "TOOLCHG", "amount": round(toolchg_fee, 2)},
        {"code": "SETUP", "amount": round(setup_fee_time, 2)},
        {"code": "MACHINE_SETUP", "amount": round(setup_amort, 2)},
        {"code": "PROG", "amount": round(prog, 2)},
        {"code": "RAPID", "amount": round(rapid_fee, 2)},
        {"code": "FIX", "amount": round(fix_fee, 2)},
        {"code": "INSPECT", "amount": round(inspect, 2)},
        {"code": "TOOLWEAR", "amount": round(toolwear, 2)},
        {"code": "SCRAP", "amount": round(scrap_fee, 2)},
        {"code": "PROFIT", "amount": round(profit, 2)},
        {"code": "FLOOR", "amount": round(amount - cost - profit if floor_applied else 0, 2)},
    ]
    return {
        "status": "quoted",
        "quote": {
            "amount": round(amount, 2),
            "cost": round(cost, 2),
            "margin": round((amount - cost) / amount * 100 if amount else 0, 2),
            "hours": hours_total,
            "floor_applied": floor_applied,
        },
        "hours": hours,
        "programming_time": programming_time["programming_time"],
        "t_programming": programming_time["t_programming"],
        "program_count": programming_time["program_count"],
        "programming_time_detail": programming_time["programming_time_detail"],
        "programming_cost": programming_cost["programming_cost"],
        "programming_cost_per_piece": programming_cost["programming_cost_per_piece"],
        "programming_cost_detail": programming_cost["programming_cost_detail"],
        "formula_trace": {
            "programming_time": programming_time["formula_trace"],
            "programming_cost": programming_cost["formula_trace"],
        },
        "suggested_days": suggested_days,
        "confidence": confidence_value,
        "deductions": deductions,
        "risk": {
            "level": risk_level,
            "tags": list(dict.fromkeys(tags)),
            "customer_forbidden": customer_forbidden,
            "deductions": deductions,
            "total_deduction": sum(item["deduction"] for item in deductions),
        },
        "cost_items": items,
        "ui_cost": {
            "material": round(mat_cost, 2),
            "machining": round(machining_sub, 2),
            "setup": round(setup_ui, 2),
            "fixture": round(fix_fee, 2),
            "programming": round(prog, 2),
            "inspect": round(inspect, 2),
            "toolwear": round(toolwear, 2),
            "scrap": round(scrap_fee, 2),
        },
        "scrap_cost_breakdown": {
            "slider": slide["slider"],
            "material_group": slide["material_group"],
            "scrap_rate": float(slide["scrap_rate"]),
            "base": round(base, 2),
            "scrap_fee": round(scrap_fee, 2),
        },
        "labor_cost_breakdown": {
            "machining": round(machining_sub, 2),
            "setup": round(setup_ui, 2),
            "total": round(round(machining_sub, 2) + round(setup_ui, 2), 2),
            **labor_trace,
        },
        "material_cost_breakdown": material_cost_breakdown,
        "validation": _validation(seq),
        "volume": vol,
        "features": plans,
        "process_sequence": seq,
        "process_overrides": process_overrides,
        "sequence_adjustment_minutes": round(sequence_adjustment_min, 4),
        "equipment": equipment_info,
        "fixture": {
            "type": fixture.get("fixture_type"),
            "method": fixture.get("fixture_method"),
            "setup_count": fixture.get("setup_count"),
            "is_machinable": fixture.get("is_machinable"),
            "is_fixture_needed": fixture.get("is_fixture_needed"),
            "fixture_material": fixture.get("fixture_material"),
            "fixture_count": fixture.get("fixture_count"),
            "fixture_block_L": fixture.get("fixture_block_L"),
            "fixture_block_W": fixture.get("fixture_block_W"),
            "fixture_block_H": fixture.get("fixture_block_H"),
            "datum_face": fixture.get("datum_face"),
            "clamp_hole_count": fixture.get("clamp_hole_count"),
            "thread_count": fixture.get("thread_count"),
            "profile_mill": fixture.get("profile_mill"),
            "angled_feature_count": fixture.get("angled_feature_count"),
            "surface_type": fixture.get("surface_type"),
            "orientation_count": fixture.get("orientation_count"),
            "fixture_orientation_count": fixture.get("fixture_orientation_count"),
            "fixture_material_cost": fixture.get("fixture_material_cost"),
            "fixture_processing_cost": fixture.get("fixture_processing_cost"),
        },
        "slider": slide,
        "rules_version": rules_version,
    }
