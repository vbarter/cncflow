"""人工工步改序/改参：覆盖生成结果，但不另起一套报价引擎。"""
from __future__ import annotations

import math


EDITABLE_PARAMS = ("minutes", "n", "f", "cut", "passes")


def assign_step_ids(sequence: list[dict]) -> list[dict]:
    """为生成工步补稳定 ID；同一特征同一工艺用出现序号消歧。"""
    seen: dict[tuple[str, str], int] = {}
    for step in sequence:
        feature_id = str(step.get("feature_id") or "feature")
        process = str(step.get("process") or step.get("op") or "process")
        key = (feature_id, process)
        seen[key] = seen.get(key, 0) + 1
        step.setdefault("step_id", f"{feature_id}:{process}:{seen[key]}")
    return sequence


def _positive_number(value, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} 须为数字") from None
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{field} 须大于 0")
    if field == "passes" and not number.is_integer():
        raise ValueError("passes 须为正整数")
    return int(number) if field == "passes" else number


def normalize_overrides(raw) -> list[dict]:
    if raw in (None, []):
        return []
    if not isinstance(raw, list):
        raise ValueError("process_overrides 须为数组")
    normalized = []
    seen = set()
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("process_overrides 每项须为对象")
        step_id = str(item.get("step_id") or "").strip()
        if not step_id:
            raise ValueError("process_overrides.step_id 不能为空")
        if step_id in seen:
            raise ValueError(f"工步 {step_id} 重复")
        seen.add(step_id)
        override = {"step_id": step_id}
        if item.get("order") is not None:
            try:
                order = int(item["order"])
            except (TypeError, ValueError):
                raise ValueError("order 须为正整数") from None
            if order <= 0:
                raise ValueError("order 须为正整数")
            override["order"] = order
        for field in EDITABLE_PARAMS:
            if item.get(field) is not None:
                override[field] = _positive_number(item[field], field)
        if len(override) > 1:
            normalized.append(override)
    return normalized


def _status(t_cut: float, step: dict) -> str:
    t_min, t_max = step.get("t_min"), step.get("t_max")
    if t_min is not None and t_cut < float(t_min):
        return "低于下限"
    if t_max is not None and t_cut > float(t_max):
        return "需人工复核"
    return "ok"


def _recalculate_step(step: dict, override: dict) -> None:
    time = dict(step.get("time") or {})
    old_n = float(step.get("n") or time.get("n") or time.get("n_act") or 0)
    old_f = float(step.get("f") or time.get("f") or 0)
    old_cut = float(step.get("cut") or time.get("cut") or 0)
    old_passes = float(step.get("passes") or time.get("passes") or 1)
    old_t_cut = float(time.get("t_cut") or 0)
    t_tool = float(time.get("t_tool") or 0)

    for field in ("n", "f", "cut", "passes"):
        if field in override:
            step[field] = override[field]
            time[field] = override[field]
            if field == "n":
                time["n"] = override[field]
                time["n_act"] = override[field]

    if "n" in override and "f" not in override and old_n > 0 and old_f > 0:
        step["f"] = time["f"] = old_f * float(override["n"]) / old_n

    if "minutes" in override:
        t_step = float(override["minutes"])
        t_cut = max(0.0, t_step - t_tool)
    else:
        n = float(step.get("n") or time.get("n") or time.get("n_act") or old_n)
        f = float(step.get("f") or time.get("f") or old_f)
        cut = float(step.get("cut") or time.get("cut") or old_cut)
        passes = float(step.get("passes") or time.get("passes") or old_passes)
        formula = str(step.get("formula") or time.get("formula") or "")
        if "n*P" in formula:
            pitch = old_cut / (old_n * old_t_cut) if old_n > 0 and old_t_cut > 0 else 1.25
            t_cut = cut / (n * pitch) if n > 0 and pitch > 0 else 0.0
        else:
            compensation = old_t_cut * old_f / (old_cut * old_passes) if old_cut > 0 and old_passes > 0 else 1.0
            t_cut = cut * passes / f * compensation if f > 0 else 0.0
        t_step = t_cut + t_tool

    step["minutes"] = round(t_step, 4)
    time["t_cut"] = round(t_cut, 4)
    time["t_step"] = round(t_step, 4)
    status = _status(t_cut, step)
    step["status"] = time["status"] = status
    time["tags"] = [] if status == "ok" else [status]
    step["time"] = time


def apply(sequence: list[dict], raw_overrides) -> tuple[list[dict], list[dict], int]:
    """应用覆盖并返回（工步、规范覆盖、相对生成顺序的逆序数）。"""
    steps = assign_step_ids([dict(step) for step in sequence])
    overrides = normalize_overrides(raw_overrides)
    if not overrides:
        return steps, [], 0

    by_id = {step["step_id"]: step for step in steps}
    unknown = [item["step_id"] for item in overrides if item["step_id"] not in by_id]
    if unknown:
        raise ValueError(f"工步不存在或工艺已变化：{', '.join(unknown)}")

    base_index = {step["step_id"]: index for index, step in enumerate(steps)}
    override_by_id = {item["step_id"]: item for item in overrides}
    for step_id, override in override_by_id.items():
        if any(field in override for field in EDITABLE_PARAMS):
            _recalculate_step(by_id[step_id], override)

    ordered = sorted(
        steps,
        key=lambda step: (
            override_by_id.get(step["step_id"], {}).get("order", step.get("order") or 0),
            base_index[step["step_id"]],
        ),
    )
    positions = [base_index[step["step_id"]] for step in ordered]
    inversions = sum(
        positions[i] > positions[j]
        for i in range(len(positions))
        for j in range(i + 1, len(positions))
    )
    for order, step in enumerate(ordered, 1):
        step["order"] = order
    return ordered, overrides, inversions
