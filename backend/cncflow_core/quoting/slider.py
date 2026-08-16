"""滑轴矩阵：钳位 → 切削倍率 + 时间倍率。"""

LEVELS = ["保守", "偏保守", "标准", "偏激进", "激进"]
ALIASES = {
    "conservative": "保守", "lean_conservative": "偏保守", "standard": "标准",
    "lean_aggressive": "偏激进", "aggressive": "激进",
    "保守": "保守", "偏保守": "偏保守", "标准": "标准", "偏激进": "偏激进", "激进": "激进",
}
EASY = {"铝合金", "铜合金", "塑料", "铸铁"}
HARD = {"不锈钢", "钛合金", "钢", "普通碳钢"}
EXTREME = {"淬硬钢"}

CUT = {
    ("保守", "易切"): (0.85, 0.9, 0.8, 0.03),
    ("偏保守", "易切"): (0.95, 0.95, 0.9, 0.04),
    ("标准", "易切"): (1.1, 1.0, 1.0, 0.05),
    ("偏激进", "易切"): (1.25, 1.05, 1.2, 0.08),
    ("激进", "易切"): (1.4, 1.1, 1.3, 0.12),
    ("保守", "难切"): (0.8, 0.85, 0.75, 0.05),
    ("偏保守", "难切"): (0.9, 0.9, 0.85, 0.06),
    ("标准", "难切"): (1.0, 0.95, 0.9, 0.07),
    ("偏激进", "难切"): (1.1, 1.0, 1.05, 0.10),
    ("激进", "难切"): (1.2, 1.05, 1.1, 0.14),
    ("保守", "极难"): (0.7, 0.8, 0.7, 0.08),
    ("偏保守", "极难"): (0.8, 0.85, 0.75, 0.10),
    ("标准", "极难"): (0.9, 0.9, 0.8, 0.12),
    ("偏激进", "极难"): (1.0, 0.95, 0.85, 0.15),
    ("激进", "极难"): (1.0, 1.0, 0.9, 0.18),
}
TIME = {
    "保守": (1.5, 1.5, 1.5, 1.3),
    "偏保守": (1.2, 1.2, 1.2, 1.25),
    "标准": (1.0, 1.0, 1.0, 1.2),
    "偏激进": (0.85, 0.85, 0.85, 1.1),
    "激进": (0.7, 0.7, 0.7, 1.0),
}


def _group(material: str) -> str:
    if material in EXTREME:
        return "极难"
    if material in HARD:
        return "难切"
    return "易切"


def _clamp(slider: str, material: str, features: list) -> str:
    idx = LEVELS.index(slider)
    if material == "淬硬钢":
        idx = min(idx, LEVELS.index("偏激进"))
    for feat in features or []:
        ftype = (feat.get("type") or feat.get("feature_type") or "")
        if ftype == "hole":
            d = float(feat.get("diameter_mm") or 99)
            depth = float(feat.get("depth_mm") or 0)
            if d < 1:
                idx = min(idx, LEVELS.index("偏保守"))
            if d > 0 and depth / d > 10:
                idx = min(idx, LEVELS.index("偏保守"))
        if ftype == "surface" and float(feat.get("roughness_ra") or feat.get("Ra") or 99) <= 0.4:
            idx = min(idx, LEVELS.index("偏保守"))
    return LEVELS[idx]


def resolve(slider, material: str, features: list) -> dict:
    level = ALIASES.get(str(slider or "标准"), "标准")
    effective = _clamp(level, material, features)
    group = _group(material)
    vc, fz, ap, scrap = CUT[(effective, group)]
    if material == "淬硬钢":
        vc = min(vc, 1.0)
    setup, toolchg, rapid, slow = TIME[effective]
    return {
        "slider": level,
        "effective_level": effective,
        "material_group": group,
        "vc": vc, "fz": fz, "ap": ap, "scrap_rate": scrap,
        "setup": setup, "toolchg": toolchg, "rapid": rapid, "slowdown": slow,
    }
