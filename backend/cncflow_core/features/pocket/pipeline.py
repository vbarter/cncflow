"""槽腔特征：难度 + 手册工序链 + TK 立铣/倒角属性。"""
from ..generic import evaluate_difficulty

_LEVEL_ORDER = {"D1": 1, "D2": 2, "D3": 3, "D4": 4, "NA": 5}
_TYPE_LEVEL = {"开放": "D1", "封闭": "D2", "键槽": "D2", "T型": "D3", "T型槽": "D3"}
_TYPE_RISK_TAGS = {
    "封闭": ["封闭型腔排屑差，需螺旋下刀"],
    "键槽": ["键槽需键槽刀；刀具目录无专用 SKU，沿用现有铣刀并人工确认"],
    "T型": ["T型槽高风险，需T型刀/燕尾刀；刀具目录无专用 SKU，沿用现有铣刀并人工确认"],
    "T型槽": ["T型槽高风险，需T型刀/燕尾刀；刀具目录无专用 SKU，沿用现有铣刀并人工确认"],
}


def _worse(a, b):
    return a if _LEVEL_ORDER.get(a, 1) >= _LEVEL_ORDER.get(b, 1) else b


def _handbook_chain(length, width, depth, corner, it, ra):
    mill_d = max(1.0, min(float(width) * 0.7, 12.0))
    steps = [{
        "process": "rough_pocket", "op": "rough_pocket", "name": "粗铣", "cycle": None,
        "tool_attrs": {"category": "平底立铣刀", "nominal_diameter_mm": mill_d},
    }]
    if it <= 8 or ra <= 1.6:
        steps.append({
            "process": "semi_finish_pocket", "op": "semi_finish_pocket", "name": "半精铣", "cycle": None,
            "tool_attrs": {"category": "平底立铣刀", "nominal_diameter_mm": mill_d},
        })
    if it <= 7 or ra <= 0.8:
        steps.append({
            "process": "finish_pocket", "op": "finish_pocket", "name": "精铣", "cycle": None,
            "tool_attrs": {"category": "平底立铣刀", "nominal_diameter_mm": mill_d},
        })
    if corner < 2:
        clear_d = max(1.0, min(2.0 * corner, float(width) * 0.4))
        steps.append({
            "process": "rest_mill", "op": "rest_mill", "name": "清角", "cycle": None,
            "tool_attrs": {"category": "平底立铣刀", "nominal_diameter_mm": clear_d},
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
        width = float(feature["width"])
        depth = float(feature["depth"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("feature.length / width / depth 必填且须为数值")
    if min(length, width, depth) <= 0:
        raise ValueError("槽腔尺寸必须为正数")
    corner = float(feature.get("corner_radius") or 1)
    pocket_type = feature.get("pocket_type") or "封闭"
    it = payload.get("tolerance_it")
    if it is None:
        it = feature.get("tolerance_it") or 10
    it = int(it)
    ra = payload.get("roughness_ra")
    if ra is None:
        ra = feature.get("roughness_ra") or 3.2
    ra = float(ra)
    metrics = {
        "h_over_w": depth / width,
        "corner_radius": corner,
        "length": length,
    }
    difficulty = evaluate_difficulty("pocket/difficulty.yaml", metrics)
    difficulty["level"] = _worse(difficulty["level"], _TYPE_LEVEL.get(str(pocket_type), "D1"))
    chain = _handbook_chain(length, width, depth, corner, it, ra)
    tags = ["槽腔超边界，需人工确认"] if difficulty["na"] else []
    tags.extend(_TYPE_RISK_TAGS.get(str(pocket_type), []))
    if depth / width > 2:
        tags.append("深槽排屑困难")
    if corner < 2:
        tags.append("小内角需清角")
    return {
        "feature_type": "pocket",
        "difficulty": difficulty,
        "process_chain": chain,
        "metrics": metrics,
        "risk_tags": tags,
        "pocket_type": pocket_type,
    }
