"""切削参数计算（文档4）：Vc 查表 → n=1000·Vc/(π·D) → fr 查表×材料修正 → ap/冷却。

文档公式表写 π 取 3.14，但全部算例数值按真实 π 舍入（D10/Vc150 → 4775rpm），
因此这里使用 math.pi 以对齐文档算例。
"""
import math

from .models import CuttingParams
from .rule_loader import load_rules

STRATEGIES = ("stable", "aggressive")

# 使用钻头 fr 表的工序 / 镗刀 fr 表的工序
_DRILL_FR = {"drill", "u_drill", "gun_drill"}
_BORE_FR = {"rough_bore", "semi_bore", "fine_bore"}
# 参数库未覆盖的工序（文档4 无 fr 数据），params 返回 None
UNSUPPORTED = {"spot_drill", "tap", "thread_mill", "flat_bottom_mill", "chamfer", "grind"}


def lookup_vc(base_material: str, material: str, strategy: str) -> float:
    """线速度基准表查询，查不到直接抛错（fail fast，如 高速钢×钛合金 原文未提供）。"""
    rules = load_rules("common/cutting_params.yaml")
    try:
        return float(rules["vc"][base_material][material][strategy])
    except KeyError:
        raise ValueError(f"线速度基准表未覆盖: 基材={base_material} 材料={material} 策略={strategy}")


def spindle_rpm(vc: float, diameter_mm: float) -> int:
    return round(1000 * vc / (math.pi * diameter_mm))


def lookup_fr(table_name: str, diameter_mm: float, strategy: str) -> float:
    """进给量分档查询。区间语义：min_d 不含、max_d 含（对齐原文 "3<D≤6"）。"""
    rules = load_rules("common/cutting_params.yaml")
    for band in rules["feed_per_rev"][table_name]:
        min_d = band.get("min_d")
        max_d = band.get("max_d")
        if min_d is not None and diameter_mm <= min_d:
            continue
        if max_d is not None and diameter_mm > max_d:
            continue
        return float(band[strategy])
    raise ValueError(f"进给量表 {table_name} 未覆盖直径 D={diameter_mm}mm")


def _cutting_depth(process: str, material: str) -> str:
    depth = load_rules("common/cutting_params.yaml")["cutting_depth"][process]
    if isinstance(depth, dict):
        return depth.get(material, depth["default"])
    return str(depth)


def _coolant(process: str, deep: bool) -> str:
    coolant = load_rules("common/cutting_params.yaml")["coolant"]
    if process == "drill" and deep:
        return coolant["drill_deep"]
    return coolant[process]


def calc_params(process: str, material: str, base_material: str, diameter_mm: float, deep: bool = False):
    """计算某工序在两种策略下的切削参数。

    返回 {"stable": CuttingParams, "aggressive": CuttingParams}；
    参数库未覆盖的工序（UNSUPPORTED）返回 None。
    """
    if process in UNSUPPORTED:
        return None

    rules = load_rules("common/cutting_params.yaml")
    result = {}
    for strategy in STRATEGIES:
        vc = lookup_vc(base_material, material, strategy)
        if process == "ream":
            vc = vc * rules["vc_factor"]["ream"][strategy]
            fr = lookup_fr("ream", diameter_mm, strategy)
        elif process in _BORE_FR:
            fr = lookup_fr("bore", diameter_mm, strategy)
        elif process in _DRILL_FR:
            fr = lookup_fr("drill", diameter_mm, strategy)
        else:
            raise ValueError(f"未知工序: {process}")
        fr = round(fr * rules["material_feed_factor"][material], 4)
        result[strategy] = CuttingParams(
            vc_m_min=round(vc, 1),
            spindle_rpm=spindle_rpm(vc, diameter_mm),
            feed_per_rev_mm=fr,
            cutting_depth=_cutting_depth(process, material),
            coolant=_coolant(process, deep),
            feed_rate_mm_min=round(spindle_rpm(vc, diameter_mm) * fr, 1),
        )
    return result
