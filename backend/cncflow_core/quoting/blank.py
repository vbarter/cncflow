"""一期毛坯决策：只给建议，不进入冻结的 quoting.volume 体积链。"""
import math

from ..common.models import BlankDecision


ROUND_STOCK = {"棒料", "棒", "bar", "round", "round_bar", "圆棒", "圆钢"}
PLATE_STOCK = {"板料", "板材", "plate"}
SQUARE_STOCK = {"方料", "方棒", "square", "square_bar"}
STANDARD_DIAMETERS = (
    6, 8, 10, 12, 16, 20, 25, 30, 32, 35, 40, 45, 50, 55, 60, 65, 70, 75,
    80, 90, 100, 110, 120, 130, 140, 150, 160, 180, 200, 220, 250, 280, 300,
)
STANDARD_PLATE_THICKNESSES = (
    1, 1.5, 2, 3, 4, 5, 6, 8, 10, 12, 15, 16, 18, 20, 25, 30, 35, 40, 45,
    50, 60, 70, 80, 100, 120, 150, 180, 200,
)


def _positive(payload: dict, *keys: str) -> float | None:
    for key in keys:
        value = payload.get(key)
        if value in (None, ""):
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number) and number > 0:
            return number
    return None


def _ceil_step(value: float, step: float = 5) -> float:
    return round(math.ceil(value / step) * step, 3)


def _next_standard(value: float, standards: tuple[float, ...], step: float = 10) -> float:
    return float(next((size for size in standards if size >= value), _ceil_step(value, step)))


def _allowance(max_dimension: float) -> float:
    if max_dimension <= 100:
        return 2.0
    if max_dimension <= 300:
        return 3.0
    return 5.0


def decide(payload: dict) -> dict:
    """按显式 stock_type 优先，其次按包络比例选择板/方/圆棒。"""
    length = _positive(payload, "length", "L")
    width = _positive(payload, "width", "W")
    height = _positive(payload, "height", "H")
    diameter = _positive(payload, "diameter", "D")
    if not length:
        raise ValueError("毛坯决策缺少 length")

    raw_stock = str(payload.get("stock_type") or payload.get("blank_type") or "").strip()
    if raw_stock in ROUND_STOCK:
        blank_type = "round_bar"
    elif raw_stock in SQUARE_STOCK:
        blank_type = "square_bar"
    elif raw_stock in PLATE_STOCK:
        blank_type = "plate"
    elif diameter and not width:
        blank_type = "round_bar"
    else:
        dimensions = sorted(
            [number for number in (length, width, height) if number],
            reverse=True,
        )
        if len(dimensions) < 3:
            raise ValueError("毛坯决策缺少完整包络尺寸")
        length, width, height = dimensions
        near_round = width / height <= 1.1 and length / width >= 2.5
        blank_type = "round_bar" if near_round else (
            "plate" if height / width <= 0.25 else "square_bar"
        )

    if blank_type == "round_bar":
        diameter = diameter or max(width or 0, height or 0)
        if not diameter:
            raise ValueError("圆棒毛坯决策缺少 diameter/width/height")
        side = _allowance(max(length, diameter))
        suggested_diameter = _next_standard(
            diameter + 2 * side,
            STANDARD_DIAMETERS,
        )
        suggested_length = _ceil_step(length + 2 * side)
        decision = BlankDecision(
            blank_type="round_bar",
            label="圆棒",
            envelope_mm={"length": length, "diameter": diameter},
            allowance_mm={"radial_each_side": side, "end_each_side": side},
            suggested_stock_size={
                "diameter": suggested_diameter,
                "length": suggested_length,
                "display": f"Ø{suggested_diameter:g} × {suggested_length:g} mm",
            },
            rule="显式圆棒" if raw_stock in ROUND_STOCK else "长径比≥2.5且截面近圆",
        )
        return decision.to_dict()

    if not width or not height:
        raise ValueError("板料/方料毛坯决策缺少 width/height")
    side = _allowance(max(length, width, height))
    suggested_length = _ceil_step(length + 2 * side)
    suggested_width = _ceil_step(width + 2 * side)
    raw_height = height + 2 * side
    suggested_height = (
        _next_standard(raw_height, STANDARD_PLATE_THICKNESSES, step=10)
        if blank_type == "plate"
        else _ceil_step(raw_height)
    )
    label = "板料" if blank_type == "plate" else "方料"
    decision = BlankDecision(
        blank_type=blank_type,
        label=label,
        envelope_mm={"length": length, "width": width, "height": height},
        allowance_mm={
            "length_each_side": side,
            "width_each_side": side,
            "height_each_side": side,
        },
        suggested_stock_size={
            "length": suggested_length,
            "width": suggested_width,
            "height": suggested_height,
            "display": f"{suggested_length:g} × {suggested_width:g} × {suggested_height:g} mm",
        },
        rule=(
            f"显式{label}"
            if raw_stock in PLATE_STOCK | SQUARE_STOCK
            else ("厚宽比≤0.25" if blank_type == "plate" else "非薄板棱柱包络")
        ),
    )
    return decision.to_dict()
