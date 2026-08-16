"""槽腔特征：难度 + 工序链。NA 仍返回。"""
from ..generic import evaluate_difficulty, process_chain


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
    metrics = {
        "h_over_w": depth / width,
        "corner_radius": corner,
        "length": length,
    }
    difficulty = evaluate_difficulty("pocket/difficulty.yaml", metrics)
    chain = process_chain("pocket/process_chain.yaml", difficulty["level"])
    tags = ["槽腔超边界，需人工确认"] if difficulty["na"] else []
    return {
        "feature_type": "pocket",
        "difficulty": difficulty,
        "process_chain": chain,
        "metrics": metrics,
        "risk_tags": tags,
    }
