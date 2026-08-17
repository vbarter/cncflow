"""台阶轮廓：难度 + 手册工序链 + TK 立铣/倒角。"""
from ..generic import evaluate_difficulty


def _handbook_chain(length, height, it, ra):
    mill_d = max(4.0, min(float(length) * 0.25, 16.0))
    attrs = {"category": "平底立铣刀", "nominal_diameter_mm": mill_d}
    steps = [{
        "process": "rough_step", "op": "rough_step", "name": "粗铣", "cycle": None,
        "tool_attrs": dict(attrs),
    }]
    if it <= 8 or ra <= 1.6:
        steps.append({
            "process": "semi_step", "op": "semi_step", "name": "半精铣", "cycle": None,
            "tool_attrs": dict(attrs),
        })
    if it <= 7 or ra <= 0.8:
        steps.append({
            "process": "finish_step", "op": "finish_step", "name": "精铣", "cycle": None,
            "tool_attrs": dict(attrs),
        })
    if ra <= 0.4 or it <= 5:
        steps.append({
            "process": "grind", "op": "grind", "name": "磨削", "cycle": None,
            "tool_attrs": None, "sku_candidates": [], "match_status": "unsupported",
            "note": "磨削超出本期刀具库",
        })
    steps.append({
        "process": "chamfer", "op": "chamfer", "name": "倒角", "cycle": None,
        "tool_attrs": {"category": "倒角刀", "nominal_diameter_mm": 6.0},
    })
    return steps


def run(payload: dict, conn) -> dict:
    feature = payload.get("feature") or {}
    try:
        length = float(feature["length"])
        height = float(feature.get("height") or feature.get("depth") or feature.get("depth_mm"))
    except (KeyError, TypeError, ValueError):
        raise ValueError("feature.length / feature.height 必填且须为数值")
    if length <= 0 or height <= 0:
        raise ValueError("台阶长高必须为正数")
    it = payload.get("tolerance_it")
    if it is None:
        it = feature.get("tolerance_it") or 10
    it = int(it)
    ra = payload.get("roughness_ra")
    if ra is None:
        ra = feature.get("roughness_ra") or 3.2
    ra = float(ra)
    profile_type = feature.get("profile_type") or "台阶"
    metrics = {"height": height, "length": length}
    difficulty = evaluate_difficulty("step/difficulty.yaml", metrics)
    if profile_type in {"外轮廓", "侧壁"} and difficulty["level"] == "D1":
        difficulty["level"] = "D2"
    chain = _handbook_chain(length, height, it, ra)
    tags = ["超边界"] if difficulty["na"] else []
    if height > 30:
        tags.append("高台阶长悬伸")
    return {
        "feature_type": "step",
        "difficulty": difficulty,
        "process_chain": chain,
        "metrics": metrics,
        "risk_tags": tags,
        "profile_type": profile_type,
        "length": length,
        "height": height,
    }
