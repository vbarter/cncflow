"""Word v3 单机编程工时与编程成本。"""
import math


T_BASE_MINUTES = {
    "hole": 5.0,
    "thread": 5.0,
    "plane": 8.0,
    "step": 10.0,
    "pocket": 15.0,
    "surface": 25.0,
}
TYPE_MAP = {
    "hole": "hole",
    "thread": "thread",
    "face": "plane",
    "plane": "plane",
    "step": "step",
    "slot": "pocket",
    "pocket": "pocket",
    "surface": "surface",
}
DIFFICULTY_FACTORS = {"D2": 1.3, "D3": 1.8, "D4": 2.5}
AXES_FACTORS = {4: 1.3, 5: 1.6}
DEFAULT_HOURLY_RATES = {3: 40.0, 4: 60.0, 5: 100.0}
T_FIXED = 30.0
T_POST = 20.0
T_DEBUG = 30.0


def _number_text(value: float) -> str:
    return f"{value:g}"


def _machine_axes(value) -> int:
    try:
        axes = int(value)
    except (TypeError, ValueError):
        return 3
    return axes if axes in {4, 5} else 3


def _difficulty_level(feature: dict) -> str:
    if feature.get("type") == "hole":
        return "D1"
    value = feature.get("difficulty_level")
    if value is None:
        value = feature.get("difficulty")
    if isinstance(value, dict):
        value = value.get("level")
    return value if value in {"D1", "D2", "D3", "D4"} else "D1"


def calculate_time(features: list, setup_count, machine_axes=None) -> dict:
    selected = [
        feature
        for feature in features or []
        if isinstance(feature, dict) and feature.get("selected") is not False
    ]
    axes = _machine_axes(machine_axes)
    axes_factor = AXES_FACTORS.get(axes, 1.0)
    if not selected:
        return {
            "programming_time": 0.0,
            "t_programming": 0.0,
            "program_count": 0,
            "programming_time_detail": [],
            "formula_trace": "0",
        }

    try:
        programs = int(setup_count)
    except (TypeError, ValueError) as exc:
        raise ValueError("INPUT_INVALID: setup_count must be greater than 0") from exc
    if programs <= 0:
        raise ValueError("INPUT_INVALID: setup_count must be greater than 0")

    details = []
    feature_minutes = 0.0
    for index, feature in enumerate(selected):
        source_type = feature.get("type")
        mapped_type = TYPE_MAP.get(source_type)
        base = T_BASE_MINUTES.get(mapped_type)
        if base is None:
            continue
        difficulty_level = _difficulty_level(feature)
        difficulty_factor = DIFFICULTY_FACTORS.get(difficulty_level, 1.0)
        freeform_factor = (
            1.5
            if source_type == "surface" and feature.get("surface_type") == "自由曲面"
            else 1.0
        )
        minutes = base * difficulty_factor * freeform_factor
        feature_minutes += minutes
        details.append({
            "feature_id": feature.get("feature_id") or feature.get("id") or f"{source_type}-{index}",
            "type": source_type,
            "mapped_type": mapped_type,
            "t_base": base,
            "difficulty_level": difficulty_level,
            "difficulty_factor": difficulty_factor,
            "freeform_factor": freeform_factor,
            "minutes": round(minutes, 4),
        })

    programming_time = (
        T_FIXED + feature_minutes + programs * (T_POST + T_DEBUG)
    ) * axes_factor
    programming_time = round(programming_time, 4)
    formula_trace = (
        f"{_number_text(T_FIXED)} + {_number_text(feature_minutes)} + "
        f"{programs}×({_number_text(T_POST)}+{_number_text(T_DEBUG)}) × "
        f"{axes_factor:.1f} = {_number_text(programming_time)}"
    )
    return {
        "programming_time": programming_time,
        "t_programming": programming_time,
        "program_count": programs,
        "programming_time_detail": details,
        "formula_trace": formula_trace,
    }


def _default_hourly_rate(machine_axes) -> float:
    return DEFAULT_HOURLY_RATES[_machine_axes(machine_axes)]


def _hourly_rate(rate_row: dict | None, machine_axes) -> float:
    value = (rate_row or {}).get("programming_hourly_rate")
    try:
        value = float(value)
    except (TypeError, ValueError):
        return _default_hourly_rate(machine_axes)
    if not math.isfinite(value) or value <= 0:
        return _default_hourly_rate(machine_axes)
    return value


def calculate_cost(
    programming_time: float,
    machine_axes=None,
    rate_row: dict | None = None,
    batch_size=1,
    is_repeat_order=False,
) -> dict:
    rate = _hourly_rate(rate_row, machine_axes)
    try:
        batch = int(batch_size)
    except (TypeError, ValueError):
        batch = 1
    batch = max(batch, 1)
    gross_cost = float(programming_time or 0) * rate / 60.0
    programming_cost = 0.0 if is_repeat_order else gross_cost
    per_piece = programming_cost / batch
    programming_cost = round(programming_cost, 2)
    per_piece = round(per_piece, 2)
    result_text = _number_text(programming_cost)
    formula_trace = (
        f"{_number_text(float(programming_time or 0))} × {_number_text(rate)} / 60"
        f" = {result_text}"
    )
    if is_repeat_order:
        formula_trace += " (repeat order)"
    return {
        "programming_cost": programming_cost,
        "programming_cost_per_piece": per_piece,
        "programming_cost_detail": [{
            "programming_time": float(programming_time or 0),
            "machine_axes": _machine_axes(machine_axes),
            "hourly_rate": rate,
            "batch_size": batch,
            "is_repeat_order": bool(is_repeat_order),
            "cost_before_batch": programming_cost,
            "cost_per_piece": per_piece,
        }],
        "formula_trace": formula_trace,
    }
