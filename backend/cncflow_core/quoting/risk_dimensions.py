"""九维风险扣分：MVP 落地 D1/D9，其余维度保留无副作用占位。"""

D1_DEDUCTION = 5
D9_DEDUCTION = 25
BELOW_MIN = "低于下限"


def _item(rule_id: str, dimension: str, status: str, deduction: int, reason: str, **context) -> dict:
    return {
        "rule_id": rule_id,
        "dimension": dimension,
        "status": status,
        "deduction": deduction,
        "reason": reason,
        **context,
    }


def collect_d1(process_sequence: list) -> list[dict]:
    """每个已对表且低于下限的工步扣 5 分；无表倒角不参与。"""
    deductions = []
    for step in process_sequence:
        status = str(step.get("status") or "ok")
        process = step.get("process") or step.get("op")
        if BELOW_MIN not in status or step.get("t_min") is None or process == "chamfer":
            continue
        order = step.get("order")
        deductions.append(_item(
            "D1-1",
            "D1",
            BELOW_MIN,
            D1_DEDUCTION,
            f"工步 {order or '—'} {process or '—'} 工时低于下限 {step.get('t_min')}",
            order=order,
            process=process,
            feature_id=step.get("feature_id"),
        ))
    return deductions


def _positive(payload: dict, *keys: str) -> bool:
    for key in keys:
        value = payload.get(key)
        if value in (None, ""):
            continue
        try:
            if float(value) > 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _selected_features(payload: dict) -> list[dict]:
    raw = payload.get("features")
    if not isinstance(raw, list):
        return []
    return [feature for feature in raw if isinstance(feature, dict) and feature.get("selected") is not False]


def collect_d9(payload: dict, process_sequence: list) -> list[dict]:
    """关键字段只做硬门禁扣分，不阻断报价。"""
    deductions = []

    material_present = payload.get("_d9_material_present")
    if material_present is None:
        material_present = bool(payload.get("material") or payload.get("material_code"))
    if not material_present:
        deductions.append(_item(
            "D9-1", "D9", "missing", D9_DEDUCTION,
            "缺少材料，报价使用默认材料参数",
        ))

    stock = payload.get("blank_type") or payload.get("stock_type") or "板料"
    is_bar = stock in {"棒料", "棒", "bar"}
    has_length = _positive(payload, "length", "L")
    has_width = _positive(payload, "diameter", "D", "width", "W")
    has_height = is_bar or _positive(payload, "height", "H")
    if not (has_length and has_width and has_height):
        deductions.append(_item(
            "D9-2", "D9", "missing", D9_DEDUCTION,
            "缺少完整外形尺寸，报价使用安全占位尺寸",
        ))

    selected = _selected_features(payload)
    selected_count = payload.get("_d9_selected_feature_count")
    if selected_count is None:
        selected_count = len(selected)
    try:
        has_selected = int(selected_count) > 0
    except (TypeError, ValueError):
        has_selected = bool(selected)
    if not has_selected:
        deductions.append(_item(
            "D9-3", "D9", "missing", D9_DEDUCTION,
            "未选择加工特征",
        ))

    if not process_sequence:
        deductions.append(_item(
            "D9-4", "D9", "missing", D9_DEDUCTION,
            "缺少可报价的工艺路线",
        ))

    return deductions


def collect(payload: dict, process_sequence: list) -> list[dict]:
    deductions = collect_d1(process_sequence)

    # TODO(D2-D8): 当前没有可无损映射的稳定信号；占位不扣分、不阻断报价。
    deductions.extend(collect_d9(payload, process_sequence))
    return deductions


def confidence_from(deductions: list[dict]) -> int:
    points = sum(max(0, int(item.get("deduction") or 0)) for item in deductions)
    return max(0, 100 - points)
