"""螺纹特征：难度 + 工序链。NA 仍返回。"""
from ..generic import evaluate_difficulty, process_chain


def run(payload: dict, conn) -> dict:
    feature = payload.get("feature") or {}
    try:
        nominal_d = float(feature.get("nominal_d") or feature.get("diameter_mm"))
        thread_length = float(feature.get("thread_length") or feature.get("depth_mm"))
    except (TypeError, ValueError, KeyError):
        raise ValueError("feature.nominal_d / feature.thread_length 必填且须为数值")
    if nominal_d <= 0 or thread_length <= 0:
        raise ValueError("螺纹直径和长度必须为正数")
    metrics = {
        "nominal_d": nominal_d,
        "l_over_d": thread_length / nominal_d,
        "pitch": float(feature.get("pitch") or 0),
    }
    difficulty = evaluate_difficulty("thread/difficulty.yaml", metrics)
    chain = process_chain("thread/process_chain.yaml", difficulty["level"])
    return {
        "feature_type": "thread",
        "difficulty": difficulty,
        "process_chain": chain,
        "metrics": metrics,
        "risk_tags": ["螺纹超边界"] if difficulty["na"] else [],
    }
