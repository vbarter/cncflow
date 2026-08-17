"""曲面 MVP：只出风险 + 人工补工时，不算五轴精铣。"""


def run(payload: dict, conn) -> dict:
    feature = payload.get("feature") or {}
    surface_type = feature.get("surface_type") or "自由曲面"
    raw_r = feature.get("curvature_radius")
    if raw_r is None:
        raw_r = feature.get("radius")
    try:
        radius = float(raw_r) if raw_r is not None else None
    except (TypeError, ValueError):
        raise ValueError("feature.curvature_radius 须为数值")
    position = feature.get("position")
    manual = feature.get("manual_hours")
    if manual is None:
        manual = payload.get("manual_hours", 0)
    try:
        manual_hours = float(manual or 0)
    except (TypeError, ValueError):
        raise ValueError("manual_hours 须为数值")
    high = surface_type == "自由曲面" or (radius is not None and radius < 1)
    tags = ["需补五轴工时"] if high else []
    return {
        "feature_type": "surface",
        "surface_type": surface_type,
        "curvature_radius": radius,
        "position": position,
        "difficulty": {
            "level": "D3" if high else "D1",
            "fired_rules": ["freeform-or-R<1"] if high else [],
            "na": False,
        },
        "process_chain": [],
        "manual_hours": manual_hours,
        "risk_level": "高" if high else "低",
        "risk_tags": tags,
    }
