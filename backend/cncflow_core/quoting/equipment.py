"""设备选定：包络 R1–R25 ∩ 0815，经济优先立加。费率走工时费率表。"""

TYPE_PRI = {
    "3轴立式加工中心": 1,
    "4轴立式加工中心": 2,
    "卧式加工中心": 3,
    "龙门加工中心": 4,
    "5轴联动加工中心": 5,
}

MILL_TYPES = set(TYPE_PRI)
EDM_TYPES = {"电火花成型机EDM", "电火花线切割WEDM"}
MAG_MIN = {
    "spot_drill": 2, "drill": 2, "peck_drill": 3, "gun_drill": 3,
    "ream": 3, "bore": 4, "semi_bore": 4, "fine_bore": 4,
    "rough_face": 3, "semi_face": 3, "finish_face": 3,
    "rough_pocket": 3, "semi_finish_pocket": 3, "finish_pocket": 3,
    "rough_step": 3, "tap": 3, "thread_mill": 3, "chamfer": 1,
    "grind": 1,
}


def _num(*vals) -> float:
    best = 0.0
    for v in vals:
        if v in (None, ""):
            continue
        try:
            best = max(best, float(v))
        except (TypeError, ValueError):
            pass
    return best


def _feat_d(feat: dict) -> float:
    return _num(feat.get("diameter_mm"), feat.get("diameter"), feat.get("nominal_d"),
                (feat.get("dimensions") or {}).get("diameter_mm"),
                (feat.get("dimensions") or {}).get("nominal_d"))


def envelope(payload: dict, features: list, L: float, W: float, H: float) -> dict:
    material = payload.get("material") or payload.get("material_code") or ""
    procs = []
    depths = [H]
    widths = [W]
    diams = []
    has_surface = False
    has_edm = False
    for f in features:
        ftype = f.get("type")
        if ftype == "surface":
            has_surface = True
            procs.append("精铣曲面")
        elif ftype == "hole":
            procs.append("钻孔")
        elif ftype in {"face", "pocket", "slot", "step"}:
            procs.append("粗铣")
        elif ftype == "thread":
            procs.append("螺纹")
        d = _feat_d(f)
        if d:
            diams.append(d)
        depths.append(_num(f.get("depth_mm"), f.get("depth"), f.get("thread_length"), f.get("height")))
        widths.append(_num(f.get("width"), f.get("length")))
    D = min(diams) if diams else 0.0
    Dmax = max(diams) if diams else 0.0
    cut_L = max(depths) if depths else H
    cut_W = max(widths) if widths else W
    stock_L = max(L, W)

    if has_edm:
        types, axes_min, pri = set(EDM_TYPES), 0, "edm"
    elif has_surface:
        types, axes_min, pri = {"4轴立式加工中心", "5轴联动加工中心"}, 4, "surface"
    elif cut_W > 300 or stock_L > 600:
        types, axes_min, pri = {"龙门加工中心", "卧式加工中心", "3轴立式加工中心"}, 3, "large"
    elif D and cut_L / D > 20:
        types, axes_min, pri = {"龙门加工中心", "3轴立式加工中心", "卧式加工中心"}, 3, "deep"
    else:
        types, axes_min, pri = set(MILL_TYPES), 3, "normal"

    if D and D < 0.5:
        rpm = 30000
    elif D and D < 1:
        rpm = 20000
    elif D and D < 3:
        rpm = 12000
    elif D:
        rpm = 6000
    else:
        rpm = 0

    heavy = "淬硬钢" in str(material) or Dmax > 20 or (cut_W > 200 and "粗铣" in procs)
    mag = max((MAG_MIN.get(p, 3) for p in procs), default=3)
    return {
        "equip_types": types,
        "priority": pri,
        "axes_min": axes_min,
        "travel_X_min": cut_W if procs else W,
        "travel_Z_min": cut_L + 100 if cut_L else 0,
        "max_rpm_min": rpm,
        "power_min": 15.0 if heavy else 7.5,
        "torque_min": 40.0 if heavy else 25.0,
        "spindle_taper": {"BT40", "HSK63", "BT50"} if (heavy or Dmax > 20) else {"BT30", "BT40"},
        "magazine_min": mag,
        "D": D,
        "Dmax": Dmax,
    }


def _ok(machine: dict, env: dict) -> bool:
    if not machine.get("enabled", 1):
        return False
    mtype = machine.get("type") or machine.get("equipment_type")
    if mtype not in env["equip_types"]:
        return False
    axes = machine.get("axes")
    if axes is not None and int(axes) < env["axes_min"]:
        return False
    tx, tz = machine.get("travel_x"), machine.get("travel_z")
    if tx is not None and env["travel_X_min"] and float(tx) < env["travel_X_min"]:
        return False
    if tz is not None and env["travel_Z_min"] and float(tz) < env["travel_Z_min"]:
        return False
    rpm = machine.get("max_rpm")
    if rpm is not None and env["max_rpm_min"] and float(rpm) < env["max_rpm_min"]:
        return False
    pw = machine.get("power_kw")
    if pw is not None and env["power_min"] and float(pw) < env["power_min"]:
        return False
    tq = machine.get("torque_nm")
    if tq is not None and env["torque_min"] and float(tq) < env["torque_min"]:
        return False
    mag = machine.get("magazine")
    if mag is not None and env["magazine_min"] and int(mag) < env["magazine_min"]:
        return False
    taper = machine.get("taper")
    if taper and env["spindle_taper"] and taper not in env["spindle_taper"]:
        return False
    return True


def _rate_row(factory: dict, equipment_type: str) -> dict:
    for row in factory.get("rate_table") or []:
        if row.get("equipment_type") == equipment_type:
            return {
                "equipment_type": equipment_type,
                "hourly_rate": float(row["hourly_rate"]),
                "setup_fee": float(row.get("setup_fee") or 0),
                "programming_hourly_rate": row.get("programming_hourly_rate"),
            }
    return {
        "equipment_type": equipment_type,
        "hourly_rate": None,
        "setup_fee": 200,
        "programming_hourly_rate": None,
    }


def select(factory: dict, payload: dict, features: list, L: float, W: float, H: float) -> dict:
    env = envelope(payload, features, L, W, H)
    forced = payload.get("equipment_type")
    machines = list(factory.get("machines") or [])
    if forced:
        machines = [m for m in machines if (m.get("type") or m.get("equipment_type")) == forced] or machines
        env = dict(env)
        env["equip_types"] = {forced} if forced in TYPE_PRI or forced in EDM_TYPES else env["equip_types"]
    hits = [m for m in machines if _ok(m, env)]

    def key(m):
        t = m.get("type") or ""
        return (TYPE_PRI.get(t, 9), float(m.get("travel_x") or 9e9), str(m.get("id") or ""))

    hits.sort(key=key)
    if hits:
        m = hits[0]
        mtype = m.get("type")
        rate = _rate_row(factory, mtype)
        if rate["hourly_rate"] is None:
            rate["hourly_rate"] = float(m.get("hourly_rate") or 0)
        return {
            "matched": True,
            "model": m.get("id"),
            "type": mtype,
            "axes": m.get("axes"),
            "max_rpm": m.get("max_rpm"),
            "hourly_rate": rate["hourly_rate"],
            "rate": rate,
            "envelope": env,
        }
    fallback_type = forced or "3轴立式加工中心"
    rate = _rate_row(factory, fallback_type)
    if rate["hourly_rate"] is None:
        rate["hourly_rate"] = 120
    fallback_axes = payload.get("machine_axes")
    if fallback_axes is None:
        fallback_axes = 5 if "5轴" in fallback_type else 4 if "4轴" in fallback_type else 3
    return {
        "matched": False,
        "model": None,
        "type": fallback_type,
        "axes": fallback_axes,
        "max_rpm": payload.get("machine_max_rpm"),
        "hourly_rate": rate["hourly_rate"],
        "rate": rate,
        "envelope": env,
    }
