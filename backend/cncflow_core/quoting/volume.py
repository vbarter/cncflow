"""材料体积：棒/板 + 余量 → V_blank；V_part 优先 CAD。"""
import math

PI = 3.14159


def classify(stock_type: str, L: float, D_or_W: float, H: float) -> str:
    if stock_type in {"棒料", "棒"}:
        return "轴类" if L / D_or_W >= 3 else "盘类"
    if L / D_or_W <= 2 and (H <= 0 or D_or_W / H <= 5):
        return "板类"
    return "箱体类"


def blank_dims(stock_type: str, L: float, D_or_W: float, H: float) -> dict:
    if stock_type in {"棒料", "棒"}:
        if D_or_W <= 50:
            a = 2
        elif D_or_W <= 120:
            a = 3
        else:
            a = 5
        return {"D_blank": D_or_W + 2 * a, "L_blank": L + 2 * a, "allowance": a, "stock_type": "棒料"}
    a = 2 if H <= 20 else 3
    return {
        "L_blank": L + 2 * a, "W_blank": D_or_W + 2 * a, "H_blank": H + 2 * a,
        "allowance": a, "stock_type": "板材",
    }


def v_blank(dims: dict) -> float:
    if dims["stock_type"] == "棒料":
        d = dims["D_blank"]
        return PI * d * d / 4 * dims["L_blank"]
    return dims["L_blank"] * dims["W_blank"] * dims["H_blank"]


def v_part_estimate(kind: str, L: float, D_or_W: float, H: float) -> float:
    if kind == "轴类":
        d_avg = D_or_W * 0.80
        return PI * d_avg * d_avg / 4 * L * 0.75
    if kind == "盘类":
        h = H or D_or_W
        return PI * D_or_W * D_or_W / 4 * h * 0.80
    if kind == "板类":
        return L * D_or_W * H * 0.70
    return L * D_or_W * H * 0.45


def compute(stock_type: str, L: float, D_or_W: float, H: float = 0, density=2.70, v_part_cad=None) -> dict:
    stock = "棒料" if stock_type in {"棒料", "棒", "bar"} else "板材"
    kind = classify(stock, L, D_or_W, H or 0)
    dims = blank_dims(stock, L, D_or_W, H or 0)
    vb = v_blank(dims)
    vp = float(v_part_cad) if v_part_cad else v_part_estimate(kind, L, D_or_W, H or D_or_W)
    removed = max(vb - vp, 0)
    return {
        "part_class": kind,
        "dims": dims,
        "v_blank_mm3": round(vb, 3),
        "v_part_mm3": round(vp, 3),
        "v_removed_mm3": round(removed, 3),
        "utilization_pct": round(vp / vb * 100, 1) if vb else 0,
        "blank_weight_kg": round(vb * density / 1_000_000, 4),
        "scrap_weight_kg": round(removed * density / 1_000_000, 4),
        "v_part_source": "cad" if v_part_cad else "estimate",
    }
