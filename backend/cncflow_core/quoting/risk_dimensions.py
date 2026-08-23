"""九维风险扣分：冻结 MVP D1–D9。"""

D1_DEDUCTION = 5
D2_DEDUCTION = 5
D3_DEDUCTION = 5
D4_DEDUCTION = 10
D5_DEDUCTION = 5
D6_DEDUCTION = 5
D7_DEDUCTION = 5
D8_DEDUCTION = 5
D9_DEDUCTION = 25
BELOW_MIN = "低于下限"

# D2 使用 mm³/s：volume.v_removed_mm3 / (cut_minutes * 60)。
MRR_MIN_MM3_S = 0.01
MRR_MAX_MM3_S = 200_000

# D3 只拦截明显不可能的高占比；零成本可由翻单/免夹具等正常业务产生。
D3_SHARE_MAX = {
    "material": 0.80,
    "machining": 0.80,
    "fixture": 0.50,
}


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


def _number(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def collect_d2(volume: dict | None, cut_minutes) -> list[dict]:
    """材料去除率超出冻结边界时扣分；信号缺失时不猜测。"""
    removed_mm3 = _number((volume or {}).get("v_removed_mm3"))
    cut_min = _number(cut_minutes)
    if removed_mm3 is None or cut_min is None or cut_min <= 0:
        return []

    mrr = removed_mm3 / (cut_min * 60)
    if MRR_MIN_MM3_S <= mrr <= MRR_MAX_MM3_S:
        return []
    return [_item(
        "D2-1",
        "D2",
        "MRR异常",
        D2_DEDUCTION,
        f"材料去除率 {mrr:.6g} mm³/s 超出 [{MRR_MIN_MM3_S}, {MRR_MAX_MM3_S}]",
        mrr_mm3_s=round(mrr, 6),
        removed_volume_mm3=removed_mm3,
        cut_minutes=cut_min,
    )]


def collect_d3(quote_amount, ui_cost: dict | None) -> list[dict]:
    """材料/加工/夹具占报价金额的高占比异常；阈值见 D3_SHARE_MAX。"""
    amount = _number(quote_amount)
    if amount is None or amount <= 0 or not isinstance(ui_cost, dict):
        return []

    deductions = []
    labels = {"material": "材料", "machining": "加工", "fixture": "夹具"}
    rule_ids = {"material": "D3-1", "machining": "D3-2", "fixture": "D3-3"}
    for key, upper in D3_SHARE_MAX.items():
        cost = _number(ui_cost.get(key))
        if cost is None or cost < 0:
            continue
        share = cost / amount
        if share <= upper:
            continue
        deductions.append(_item(
            rule_ids[key],
            "D3",
            "成本占比异常",
            D3_DEDUCTION,
            f"{labels[key]}成本占报价金额 {share:.1%}，高于上限 {upper:.0%}",
            cost_key=key,
            share=round(share, 6),
            upper=upper,
        ))
    return deductions


def collect_d4(risk_tags: list | None) -> list[dict]:
    """复用现有设备匹配信号，不重复推导设备能力。"""
    if "设备不匹配" not in (risk_tags or []):
        return []
    return [_item(
        "D4-1",
        "D4",
        "设备不匹配",
        D4_DEDUCTION,
        "报价设备或夹具能力与零件加工要求不匹配",
    )]


def collect_d5(process_sequence: list) -> list[dict]:
    """任一已提供的主轴转速 n 或进给 f 非正时，按规则一次扣分。"""
    invalid = []
    for step in process_sequence:
        fields = []
        for field in ("n", "f"):
            value = _number(step.get(field))
            if value is not None and value <= 0:
                fields.append(field)
        if fields:
            invalid.append({
                "order": step.get("order"),
                "process": step.get("process") or step.get("op"),
                "fields": fields,
            })
    if not invalid:
        return []
    summary = "；".join(
        f"工步 {item['order'] or '—'} {item['process'] or '—'}: {','.join(item['fields'])}"
        for item in invalid
    )
    return [_item(
        "D5-1",
        "D5",
        "切削参数异常",
        D5_DEDUCTION,
        f"主轴转速或进给必须大于 0（{summary}）",
        invalid_steps=invalid,
    )]


# TODO(D5-2): 当前 slider 只有倍率，没有可审计的 n/f 绝对上限带；补齐稳定上限前不扣分。


ROUGH_PROCESSES = {
    "drill", "peck_drill", "gun_drill", "u_drill", "spot_drill",
    "rough_face", "rough_pocket", "rough_step", "rough_bore", "mill",
}
FINISH_PROCESSES = {
    "semi_finish_pocket", "semi_bore", "semi_face", "semi_step",
    "finish_face", "finish_pocket", "finish_step", "ream", "bore",
    "fine_bore", "grind", "tap", "thread_mill", "flat_bottom_mill",
    "rest_mill",
}
AUX_PROCESSES = {"chamfer", "deburr"}
GROUP_FIELDS = ("setup_group", "fixture_group", "setup_id", "fixture_id")


def _process_group(step: dict) -> tuple:
    """优先使用显式装夹/夹具分组；旧路线无分组时视为同一装夹。"""
    values = tuple(
        (field, str(step[field]))
        for field in GROUP_FIELDS
        if step.get(field) not in (None, "")
    )
    return values or (("setup_group", "default"),)


def _is_rough(step: dict) -> bool:
    process = str(step.get("process") or step.get("op") or "")
    return step.get("stage") == "粗" or process in ROUGH_PROCESSES or process.startswith("rough_")


def _is_finish(step: dict) -> bool:
    process = str(step.get("process") or step.get("op") or "")
    if process in AUX_PROCESSES:
        return False
    return (
        step.get("stage") in {"半精", "精"}
        or process in FINISH_PROCESSES
        or process.startswith(("semi_", "finish_", "fine_"))
    )


def collect_d6(process_sequence: list) -> list[dict]:
    """同一装夹/夹具组内精加工不得早于粗加工，倒角必须最后。"""
    groups: dict[tuple, list[dict]] = {}
    for step in process_sequence:
        if isinstance(step, dict):
            groups.setdefault(_process_group(step), []).append(step)

    violations = []
    for group, steps in groups.items():
        ordered = sorted(
            enumerate(steps),
            key=lambda item: (_number(item[1].get("order")) or item[0] + 1, item[0]),
        )
        ordered_steps = [step for _, step in ordered]
        rough_indexes = [i for i, step in enumerate(ordered_steps) if _is_rough(step)]
        finish_indexes = [i for i, step in enumerate(ordered_steps) if _is_finish(step)]
        finish_before_rough = (
            bool(rough_indexes)
            and bool(finish_indexes)
            and min(finish_indexes) < max(rough_indexes)
        )
        chamfer_not_last = any(
            str(step.get("process") or step.get("op") or "") == "chamfer"
            for step in ordered_steps[:-1]
        )
        if finish_before_rough or chamfer_not_last:
            violations.append({
                "group": dict(group),
                "finish_before_rough": finish_before_rough,
                "chamfer_not_last": chamfer_not_last,
                "orders": [step.get("order") for step in ordered_steps],
            })

    if not violations:
        return []
    reasons = []
    if any(item["finish_before_rough"] for item in violations):
        reasons.append("精加工早于粗加工")
    if any(item["chamfer_not_last"] for item in violations):
        reasons.append("倒角不是组内最后工步")
    return [_item(
        "D6-1",
        "D6",
        "工序顺序异常",
        D6_DEDUCTION,
        "；".join(reasons),
        violations=violations,
    )]


def collect_d7(quote_amount, ui_cost: dict | None) -> list[dict]:
    """净材料成本须大于零且不得高于报价金额。"""
    amount = _number(quote_amount)
    material_cost = _number((ui_cost or {}).get("material"))
    if material_cost is None or amount is None:
        return []
    if material_cost > 0 and material_cost <= amount:
        return []
    reason = (
        f"净材料成本 {material_cost:.2f} 必须大于 0"
        if material_cost <= 0
        else f"材料成本 {material_cost:.2f} 高于报价金额 {amount:.2f}"
    )
    return [_item(
        "D7-1",
        "D7",
        "材料成本异常",
        D7_DEDUCTION,
        reason,
        material_cost=material_cost,
        quote_amount=amount,
    )]


def collect_d8(
    process_sequence: list,
    *,
    equipment: dict | None,
    hours_cut,
) -> list[dict]:
    """设备字段须完整，切削工时须与工艺路线分钟数一致。"""
    required_equipment = ("model", "type", "hourly_rate")
    missing_fields = [
        field
        for field in required_equipment
        if not isinstance(equipment, dict) or equipment.get(field) in (None, "")
    ]
    cut_hours = _number(hours_cut)
    sequence_minutes = sum(
        _number(step.get("minutes")) or 0
        for step in process_sequence
        if isinstance(step, dict)
    )
    mismatch_minutes = (
        None
        if cut_hours is None
        else abs(cut_hours * 60 - sequence_minutes)
    )
    if not missing_fields and (mismatch_minutes is None or mismatch_minutes <= 0.5):
        return []

    reasons = []
    if missing_fields:
        reasons.append(f"缺少设备字段：{','.join(missing_fields)}")
    if mismatch_minutes is not None and mismatch_minutes > 0.5:
        reasons.append(f"切削工时与工艺路线相差 {mismatch_minutes:.4f} 分钟")
    return [_item(
        "D8-1",
        "D8",
        "一致性异常",
        D8_DEDUCTION,
        "；".join(reasons),
        missing_equipment_fields=missing_fields,
        hours_cut=cut_hours,
        sequence_minutes=round(sequence_minutes, 6),
        mismatch_minutes=round(mismatch_minutes, 6) if mismatch_minutes is not None else None,
    )]


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


def collect(
    payload: dict,
    process_sequence: list,
    *,
    volume: dict | None = None,
    cut_minutes=None,
    quote_amount=None,
    ui_cost: dict | None = None,
    risk_tags: list | None = None,
    equipment: dict | None = None,
    hours_cut=None,
) -> list[dict]:
    deductions = collect_d1(process_sequence)

    if cut_minutes is None:
        cut_minutes = sum(_number(step.get("minutes")) or 0 for step in process_sequence)
    deductions.extend(collect_d2(volume, cut_minutes))
    deductions.extend(collect_d3(quote_amount, ui_cost))
    deductions.extend(collect_d4(risk_tags))
    deductions.extend(collect_d5(process_sequence))
    deductions.extend(collect_d6(process_sequence))
    deductions.extend(collect_d7(quote_amount, ui_cost))
    deductions.extend(collect_d8(
        process_sequence,
        equipment=equipment,
        hours_cut=hours_cut,
    ))
    deductions.extend(collect_d9(payload, process_sequence))
    return deductions


def confidence_from(deductions: list[dict]) -> int:
    points = sum(max(0, int(item.get("deduction") or 0)) for item in deductions)
    return max(0, 100 - points)
