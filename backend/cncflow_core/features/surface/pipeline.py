"""曲面 MVP：只出风险 + 人工补工时，不算五轴精铣。"""


def run(payload: dict, conn) -> dict:
    feature = payload.get("feature") or {}
    manual = feature.get("manual_hours")
    if manual is None:
        manual = payload.get("manual_hours", 0)
    try:
        manual_hours = float(manual or 0)
    except (TypeError, ValueError):
        raise ValueError("manual_hours 须为数值")
    return {
        "feature_type": "surface",
        "difficulty": {"level": "NA", "fired_rules": [], "na": True},
        "process_chain": [],
        "manual_hours": manual_hours,
        "risk_tags": ["需补五轴工时"],
    }
