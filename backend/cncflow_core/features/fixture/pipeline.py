"""夹具 F1–F5：first-match，不可装夹仍返回结果（内部模式不 blocked）。"""
import math

from ...common.rule_loader import load_rules

TIMES = {
    ("F1", "平口钳"): (0, 3, 8),
    ("F1", "压板垫铁"): (0, 8, 12),
    ("F2", "软爪"): (15, 5, 12),
    ("F3", "专用夹具"): (45, 3, 5),
    ("F3", "专用刚性"): (45, 3, 5),
    ("F3", "专用+支撑"): (45, 3, 5),
    ("F4", "真空吸盘"): (5, 2, 4),
    ("F4", "磁力吸盘"): (5, 2, 4),
    ("F5", "三爪卡盘"): (2, 3, 8),
}


def _mat(name: str) -> dict:
    table = load_rules("fixture/materials.yaml")
    mats = table["materials"]
    return mats.get(name) or mats[table["fallback"]]


def _dims(feature: dict):
    try:
        vals = sorted(float(feature[k]) for k in ("length", "width", "depth"))
    except (KeyError, TypeError, ValueError):
        raise ValueError("feature.length / width / depth 必填且须为数值")
    if min(vals) <= 0:
        raise ValueError("外形尺寸必须为正数")
    return vals  # d1 <= d2 <= d3


def _shape(feature, d1, d2, d3) -> str:
    features = feature.get("features") or []
    has_rev = any((f.get("surface_type") == "回转面") for f in features)
    has_free = any((f.get("surface_type") == "自由曲面") for f in features)
    if has_rev and d1 > 0 and d2 / d1 <= 1.5 and d3 / d1 >= 3:
        return "轴类"
    if has_rev and d3 > 0 and d1 / d3 <= 0.33:
        return "盘类"
    if has_free:
        return "异形"
    return "方形"


def _directions(feature) -> tuple[set, bool, bool]:
    dset, a_flag, overhang = set(), False, False
    for item in feature.get("features") or []:
        pos = item.get("position_type") or item.get("face_position") or ""
        if item.get("position_type") == "曲面" or item.get("surface_type") == "自由曲面":
            overhang = True
        if "倾斜" in str(pos) or item.get("surface_type") in {"自由曲面", "回转面"} and item.get("position_type") in {"倾斜", "曲面"}:
            a_flag = True
            continue
        if pos in {"垂直", "深腔"} or "垂直" in str(pos):
            dset.add(item.get("axis") or "+Z")
        elif pos == "侧向":
            dset.add(item.get("axis") or "+X")
        elif "倾斜" in str(pos) or pos == "曲面":
            a_flag = True
    return dset, a_flag, overhang


def _fixture_type(shape, material, d1, d2, wall, it) -> tuple[str, str]:
    if shape == "异形":
        return "F3", "专用夹具"
    if material == "淬硬钢":
        return "F3", "专用刚性"
    if shape in {"轴类", "盘类"}:
        return "F5", "三爪卡盘"
    # 方形
    thin = wall < 2 * _mat(material)["thin_wall"]
    if d1 <= 5:
        method = "磁力吸盘" if material in {"钢", "普通碳钢", "铸铁", "淬硬钢"} else "真空吸盘"
        return "F4", method
    if thin and d2 <= 200:
        return "F2", "软爪"
    if thin and d2 > 200:
        return "F3", "专用+支撑"
    if it <= 6:
        return "F3", "专用刚性"
    if d2 > 200:
        return "F1", "压板垫铁"
    return "F1", "平口钳"


def _setup_count(shape, axes, d1, d3, dset, a_flag) -> int:
    if shape == "轴类":
        return 2 if (d1 and d3 / d1 > 10) else 1
    if shape == "盘类":
        return 2 if any(d.endswith("Z") and d.startswith("-") or d == "-Z" for d in dset) else 1
    if shape == "异形":
        return 1
    if axes >= 5:
        return 2 if len(dset) >= 6 else 1
    if axes == 4:
        return 1
    return max(1, len(dset) + (1 if a_flag else 0)) or 1


def _costs(ftype, method, setup_count, length, width, depth, it, dset, hourly, batch, repeat):
    t_prep, t_clamp, t_change = TIMES.get((ftype, method), (45, 3, 5))
    if it <= 6:
        t_align = 10
    elif it <= 8:
        t_align = 5
    else:
        t_align = 0
    if ftype == "F1":
        mat_cost, mach_min = 0, 0
    elif ftype == "F2":
        mat_cost, mach_min = 50, 15 + (setup_count - 1) * 10
    elif ftype == "F5":
        mat_cost, mach_min = 50, 15
    elif ftype == "F4":
        mat_cost, mach_min = 0, 0
    else:
        block_l, block_w = length + 40, width + 40
        block_h = max(50, depth * 0.5 + 30)
        frame = 0.3 if block_l > 500 or block_w > 500 else 1.0
        vol = block_l * block_w * block_h * frame
        steel_w = vol * 7.85 * 1e-6
        use_al = it > 6 and steel_w > 25
        dens, price = (2.70, 25) if use_al else (7.85, 8)
        mat_cost = vol * dens * 1e-6 * price
        c1 = 1.0 if len(dset) <= 2 else 1.5 if len(dset) == 3 else 2.0
        c2 = 1.5 if it <= 6 else 1.0
        n = max(2, math.ceil(len(dset) * 0.5))
        mach_min = 120 * c1 * c2 + n * 10
    fixture_cost = mat_cost + mach_min * hourly / 60
    per = 0 if repeat or ftype in {"F1", "F4"} else fixture_cost / max(batch, 1)
    if ftype == "F5" and repeat:
        per = 0
    elif ftype == "F5":
        per = fixture_cost / max(batch, 1)
    return t_prep, t_clamp, t_change, t_align, mat_cost, mach_min, per


def run(payload: dict, conn) -> dict:
    feature = payload.get("feature") or payload
    d1, d2, d3 = _dims(feature)
    length, width, depth = float(feature["length"]), float(feature["width"]), float(feature["depth"])
    material = payload.get("material") or payload.get("material_code") or "钢"
    it = int(payload.get("tolerance_it") or feature.get("tolerance_grade") or 11)
    wall = float(feature.get("wall_thickness") or payload.get("wall_thickness") or 999)
    axes = int((payload.get("machine_profile") or {}).get("axes") or payload.get("machine_axes") or 3)
    max_z = (payload.get("machine_profile") or {}).get("max_z") or payload.get("machine_max_z")
    batch = int(payload.get("batch_size") or 1)
    repeat = bool(payload.get("is_repeat_order"))
    blank = payload.get("blank_type") or "板料"
    hourly = float(payload.get("hourly_rate") or 120)
    ignore = bool(payload.get("ignore_available_machines"))

    mat = _mat(material)
    shape = _shape(feature, d1, d2, d3)
    dset, a_flag, overhang = _directions(feature)
    weight = length * width * depth * mat["density"] * 1e-6

    machinable = True
    risks = []
    if axes <= 3 and overhang:
        machinable = False
        risks.append("三轴不可达悬伸/曲面孔")
    if max_z is not None and depth > float(max_z):
        machinable = False
        risks.append("超Z行程")
    if ignore:
        machinable = True  # 外发忽略设备仍出价

    ftype, method = _fixture_type(shape, material, d1, d2, wall, it)
    setup = _setup_count(shape, axes, d1, d3, dset, a_flag)
    t_prep, t_clamp, t_change, t_align, mat_cost, mach_min, per = _costs(
        ftype, method, setup, length, width, depth, it, dset, hourly, batch, repeat
    )
    w_factor = 1.5 if weight > 25 else 1.0
    setup_time = (t_clamp + (setup - 1) * (t_change + t_align) + 2) * mat["material_factor"] * w_factor
    if blank in {"铸件", "锻件", "焊接件"}:
        setup_time += 5
    prep = 0 if repeat else t_prep / max(batch, 1)

    return {
        "feature_type": "fixture",
        "fixture_type": ftype,
        "fixture_method": method,
        "shape_type": shape,
        "setup_count": setup,
        "change_count": max(setup - 1, 0),
        "setup_time_total": round(setup_time, 3),
        "prep_per_piece": round(prep, 3),
        "fixture_material_cost": round(mat_cost, 2),
        "fixture_machining_time": round(mach_min, 3),
        "fixture_cost_per_piece": round(per, 2),
        "is_machinable": machinable,
        "weight_kg": round(weight, 3),
        "risk_tags": risks if machinable else risks + ["不可装夹仍出价，标高风险"],
        "machinability": {
            "level": 1 if machinable else 4,
            "fired_rules": [{"id": "FIXTURE-TYPE", "level": ftype, "method": method}],
        },
    }
