"""报价引擎：跑特征管道 + 夹具 + 体积 + 滑轴 → 始终出报价。"""
from ..factory.store import get_config
from ..features.face import pipeline as face_pipeline
from ..features.fixture import pipeline as fixture_pipeline
from ..features.hole import pipeline as hole_pipeline
from ..features.pocket import pipeline as pocket_pipeline
from ..features.surface import pipeline as surface_pipeline
from ..features.thread import pipeline as thread_pipeline
from . import confidence, slider, volume

PIPELINES = {
    "hole": hole_pipeline.run,
    "face": face_pipeline.run,
    "pocket": pocket_pipeline.run,
    "thread": thread_pipeline.run,
    "surface": surface_pipeline.run,
}

DIFF_MIN = {"D1": 2.0, "D2": 6.0, "D3": 15.0, "D4": 25.0, "NA": 20.0, 1: 2.0, 2: 6.0, 3: 15.0, 4: 25.0}
DIFF_FACTOR = {"D3": 1.3, "D4": 1.8, 3: 1.3, 4: 1.8}


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


def _density(material: str, factory: dict) -> float:
    from ..features.fixture.pipeline import _mat
    return float(_mat(material)["density"])


def _price(material: str, factory: dict, payload: dict):
    if payload.get("price_per_kg") is not None:
        return float(payload["price_per_kg"]), float(payload.get("scrap_price_per_kg") or 0)
    for row in factory.get("material_prices") or []:
        if row["material_code"] == payload.get("material_code") or row.get("material_code") == material:
            return float(row["price_per_kg"]), float(row.get("scrap_price_per_kg") or 0)
    defaults = {"铝合金": 25, "钢": 8, "普通碳钢": 8, "不锈钢": 30, "钛合金": 200, "淬硬钢": 15, "铸铁": 6, "铜合金": 50}
    return float(defaults.get(material, 25)), 0.0


def _rate(factory: dict, payload: dict) -> dict:
    eq = payload.get("equipment_type") or "3轴立式加工中心"
    for row in factory.get("rate_table") or []:
        if row["equipment_type"] == eq:
            return row
    return {"equipment_type": eq, "hourly_rate": 120, "setup_fee": 200, "programming_fee_new": 300}


def _feature_minutes(result: dict, ftype: str) -> tuple[float, object, bool]:
    if ftype == "surface":
        return float(result.get("manual_hours") or 0) * 60, "NA", True
    if ftype == "hole":
        level = (result.get("machinability") or {}).get("level", 1)
        na = int(level or 1) >= 4
        return DIFF_MIN.get(level, 6.0), level, na
    diff = result.get("difficulty") or {}
    level = diff.get("level", "D1")
    return DIFF_MIN.get(level, 6.0), level, bool(diff.get("na"))


def quote(payload: dict, conn, rules_version: str = "") -> dict:
    material = payload.get("material") or payload.get("material_code") or "铝合金"
    factory = get_config(conn)
    settings = factory["settings"]
    features = list(payload.get("features") or [])
    slide = slider.resolve(payload.get("slider") or "标准", material, features)
    stock = payload.get("blank_type") or payload.get("stock_type") or settings.get("blank_type") or "板料"
    L = float(payload.get("length") or payload.get("L") or 0)
    D = float(payload.get("diameter") or payload.get("D") or payload.get("width") or payload.get("W") or 0)
    H = float(payload.get("height") or payload.get("H") or 0)
    if L <= 0 or D <= 0:
        raise ValueError("length 与 diameter/width 必填且须为正数")
    dens = _density(material, factory)
    vol = volume.compute(stock, L, D, H, density=dens, v_part_cad=payload.get("v_part_cad"))
    price, scrap_price = _price(material, factory, payload)
    mat_cost = vol["blank_weight_kg"] * price - vol["scrap_weight_kg"] * scrap_price

    rate = _rate(factory, payload)
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
        mins, level, na = _feature_minutes(result, ftype)
        mins = mins / max(slide["vc"], 0.4) * slide["slowdown"]
        cut_min += mins
        n_tools += max(len(result.get("process_chain") or result.get("tool_chain") or [1]), 1)
        ops.append({"op": ftype, "minutes": mins, "na": na})
        plans.append({"feature_id": feat.get("id") or f"{ftype}-{i}", "type": ftype, "plan": result})
        steps = result.get("tool_chain") or result.get("process_chain") or []
        fid = feat.get("id") or feat.get("feature_id") or f"{ftype}-{i}"
        for step in steps:
            sel = step.get("selected_candidate") or {}
            sku = sel.get("candidate_id") or ((step.get("sku_candidates") or [None])[0])
            if not sku:
                sku = _nearest_sku(conn, step)
            seq.append({
                "order": len(seq) + 1,
                "feature_id": fid,
                "process": step.get("process"),
                "cycle": step.get("cycle"),
                "sku": sku,
                "side": step.get("side"),
                "match_status": step.get("match_status") if sel.get("candidate_id") else ("nearest" if sku else step.get("match_status")),
                "tool": sku or step.get("cycle") or step.get("process") or "—",
            })
            if step.get("name"):
                seq[-1]["name"] = step["name"]
        tags.extend(result.get("risk_tags") or [])
        if order.get(level, 1) > order.get(worst, 1):
            worst = level

    fixture_feat = {
        "type": "fixture", "length": L,
        "width": payload.get("width") or D, "depth": H or D,
        "features": features,
    }
    fixture = fixture_pipeline.run({
        **payload, "feature": fixture_feat, "material": material,
        "batch_size": batch, "is_repeat_order": repeat, "hourly_rate": hourly,
        "ignore_available_machines": settings.get("ignore_available_machines"),
    }, conn)
    if not fixture.get("is_machinable"):
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
    prog = 0 if repeat else float(rate.get("programming_fee_new") or 300)
    cut_fee = cut_hours * hourly * factor
    toolchg_fee = (toolchg_min / 60) * hourly
    setup_fee_time = (setup_min / 60) * hourly
    rapid_fee = (rapid_min / 60) * hourly
    fix_fee = 0 if repeat else float(fixture.get("fixture_cost_per_piece") or 0)
    toolwear = cut_hours * 15
    machining_sub = cut_fee + toolchg_fee + rapid_fee
    setup_ui = setup_fee_time + setup_amort + fix_fee
    base = mat_cost + machining_sub + setup_ui + prog + inspect + toolwear
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
    conf = confidence.score(ops)
    tags.extend(conf["tags"])
    if any(op["na"] for op in ops):
        conf["level"] = "high" if conf["confidence"] >= 30 else conf["level"]
        tags.append("超出常规边界")
    if any("深孔" in str(t) for t in tags) and conf.get("level") in {None, "low", "medium_low", "medium"}:
        conf["level"] = "high"

    STEP_NAME = {
        "spot_drill": "点钻", "drill": "钻孔", "gun_drill": "枪钻", "u_drill": "U钻",
        "ream": "铰孔", "bore": "镗孔", "semi_bore": "半精镗", "fine_bore": "精镗",
        "tap": "攻丝", "chamfer": "倒角", "face": "铣面", "mill": "铣削",
        "flat_bottom_mill": "修底", "grind": "磨削",
    }
    if seq:
        per_min = cut_min / len(seq)
        per_amt = cut_fee / len(seq)
        for s in seq:
            proc = s.get("process") or s.get("op")
            s.setdefault("name", STEP_NAME.get(proc, proc or "工序"))
            s.setdefault("tool", s.get("sku") or s.get("tool") or s.get("cycle") or proc or "—")
            s.setdefault("minutes", round(per_min, 2))
            s.setdefault("amount", round(per_amt, 2))

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
            "floor_applied": floor_applied,
        },
        "confidence": conf["confidence"],
        "risk": {
            "level": conf["level"] if conf["confidence"] >= 30 else "critical",
            "tags": list(dict.fromkeys(tags)),
            "customer_forbidden": conf["confidence"] < 30,
        },
        "cost_items": items,
        "ui_cost": {
            "material": round(mat_cost, 2),
            "machining": round(machining_sub, 2),
            "setup": round(setup_ui, 2),
            "programming": round(prog, 2),
            "inspect": round(inspect, 2),
            "toolwear": round(toolwear, 2),
            "scrap": round(scrap_fee, 2),
        },
        "volume": vol,
        "features": plans,
        "process_sequence": seq,
        "fixture": {
            "type": fixture.get("fixture_type"),
            "method": fixture.get("fixture_method"),
            "setup_count": fixture.get("setup_count"),
            "is_machinable": fixture.get("is_machinable"),
        },
        "slider": slide,
        "rules_version": rules_version,
    }
