"""平面特征：难度 + 手册工序链 + TK 面铣。"""
from ..generic import evaluate_difficulty


def _face_mill_d(length, width):
    span = min(float(length), float(width))
    if span >= 80:
        return 80.0
    if span >= 50:
        return 50.0
    return max(6.0, min(12.0, span * 0.5))


def _handbook_chain(length, width, it, ra):
    mill_d = _face_mill_d(length, width)
    attrs = {"category": "平底立铣刀", "nominal_diameter_mm": mill_d}
    steps = [{
        "process": "rough_face", "op": "rough_face", "name": "粗铣", "cycle": None,
        "tool_attrs": dict(attrs),
    }]
    if it <= 8 or ra <= 1.6:
        steps.append({
            "process": "semi_face", "op": "semi_face", "name": "半精铣", "cycle": None,
            "tool_attrs": dict(attrs),
        })
    if it <= 7 or ra <= 0.8:
        steps.append({
            "process": "finish_face", "op": "finish_face", "name": "精铣", "cycle": None,
            "tool_attrs": dict(attrs),
        })
    if ra <= 0.4 or it <= 5:
        steps.append({
            "process": "grind", "op": "grind", "name": "磨削", "cycle": None,
            "tool_attrs": None, "sku_candidates": [], "match_status": "unsupported",
            "note": "磨削超出本期刀具库",
        })
    return steps


def run(payload: dict, conn) -> dict:
    feature = payload.get("feature") or {}
    try:
        length = float(feature["length"])
        width = float(feature["width"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("feature.length / feature.width 必填且须为数值")
    if length <= 0 or width <= 0:
        raise ValueError("平面长宽必须为正数")
    depth = float(feature.get("depth") or feature.get("allowance") or 1)
    it = payload.get("tolerance_it")
    if it is None:
        it = feature.get("tolerance_it") or 10
    it = int(it)
    ra = payload.get("roughness_ra")
    if ra is None:
        ra = feature.get("roughness_ra") or 3.2
    ra = float(ra)
    pos = feature.get("face_position") or "顶面"
    metrics = {
        "area": length * width,
        "tolerance_it": it,
        "roughness_ra": ra,
        "depth": depth,
    }
    difficulty = evaluate_difficulty("face/difficulty.yaml", metrics)
    chain = _handbook_chain(length, width, it, ra)
    tags = ["超边界"] if difficulty["na"] else []
    if pos == "侧面":
        tags.append("侧面需翻面或侧铣")
    return {
        "feature_type": "face",
        "difficulty": difficulty,
        "process_chain": chain,
        "metrics": metrics,
        "risk_tags": tags,
        "face_position": pos,
    }
