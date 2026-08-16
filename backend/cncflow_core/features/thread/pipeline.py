"""螺纹特征：难度 + 手册工序链 + TK 丝锥/螺纹铣。"""
from ..generic import evaluate_difficulty


def _handbook_chain(nominal_d, pitch, thread_length, material):
    tap = nominal_d <= 16 and (thread_length / max(nominal_d, 1e-6)) < 5
    if material in {"不锈钢"}:
        tap = False
    steps = [{
        "process": "drill", "op": "drill", "name": "钻孔", "cycle": "G83",
        "tool_attrs": {
            "category": "钻头",
            "nominal_diameter_mm": max(1.0, float(nominal_d) - float(pitch or 1.25)),
        },
    }]
    if tap:
        steps.append({
            "process": "tap", "op": "tap", "name": "攻牙", "cycle": None,
            "tool_attrs": {"category": "丝锥", "nominal_diameter_mm": float(nominal_d)},
        })
    else:
        steps.append({
            "process": "thread_mill", "op": "thread_mill", "name": "螺纹铣", "cycle": None,
            "tool_attrs": {"category": "螺纹铣刀", "nominal_diameter_mm": 6.0},
        })
    return steps


def run(payload: dict, conn) -> dict:
    feature = payload.get("feature") or {}
    try:
        nominal_d = float(feature.get("nominal_d") or feature.get("diameter_mm"))
        thread_length = float(feature.get("thread_length") or feature.get("depth_mm") or feature.get("length"))
    except (TypeError, ValueError, KeyError):
        raise ValueError("feature.nominal_d / feature.thread_length 必填且须为数值")
    if nominal_d <= 0 or thread_length <= 0:
        raise ValueError("螺纹直径和长度必须为正数")
    pitch = feature.get("pitch")
    pitch = float(pitch) if pitch not in (None, "") else None
    if pitch is None:
        from cncflow_core.geometry.thread import infer_pitch
        pitch = infer_pitch(nominal_d) or 1.25
    material = payload.get("material") or payload.get("material_code") or "铝合金"
    metrics = {
        "nominal_d": nominal_d,
        "l_over_d": thread_length / nominal_d,
        "pitch": pitch,
    }
    difficulty = evaluate_difficulty("thread/difficulty.yaml", metrics)
    chain = _handbook_chain(nominal_d, pitch, thread_length, material)
    tags = ["螺纹超边界"] if difficulty["na"] else []
    if not tap_ok(nominal_d, thread_length, material):
        tags.append("走螺纹铣")
    return {
        "feature_type": "thread",
        "difficulty": difficulty,
        "process_chain": chain,
        "metrics": metrics,
        "risk_tags": tags,
        "diameter_mm": nominal_d,
        "pitch": pitch,
        "thread_length": thread_length,
    }


def tap_ok(nominal_d, thread_length, material):
    if material in {"不锈钢"}:
        return False
    return nominal_d <= 16 and (thread_length / max(nominal_d, 1e-6)) < 5
