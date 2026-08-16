"""平面特征：难度 + 工序链。超边界仍返回。"""
from ..generic import evaluate_difficulty, process_chain


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
    ra = payload.get("roughness_ra")
    metrics = {
        "area": length * width,
        "tolerance_it": float(it) if it is not None else 11,
        "roughness_ra": float(ra) if ra is not None else 3.2,
        "depth": depth,
    }
    difficulty = evaluate_difficulty("face/difficulty.yaml", metrics)
    chain = process_chain("face/process_chain.yaml", difficulty["level"])
    return {
        "feature_type": "face",
        "difficulty": difficulty,
        "process_chain": chain,
        "metrics": metrics,
        "risk_tags": ["超边界"] if difficulty["na"] else [],
    }
