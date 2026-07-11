"""单刀 5 项硬性属性推算（文档2）。

- 公称直径：粗加工刀具 = 成品孔径 - 精加工余量（有精加工工序时）；精加工刀具 = 成品孔径
- 结构类型：按 H/D（标准/内冷/枪钻）
- 基材/涂层：按工件材料
- 精度等级：粗加工刀具一律"普通"，精加工刀具按 IT
- 倒角刀/中心钻：直径不限定（None），SKU 匹配走 relaxed 模式
"""
from ...common.models import ToolAttrs, ToolRequirement
from ...common.rule_loader import load_rules

ROUGH_PROCESSES = {"drill", "u_drill", "gun_drill", "rough_bore"}
FINISH_PROCESSES = {"ream", "semi_bore", "fine_bore"}


def _allowance(d: float, rules: dict) -> float:
    for band in rules["finishing_allowance"]:
        max_d = band.get("max_d")
        min_d = band.get("min_d")
        if max_d is not None:
            if (d <= max_d) if band.get("inclusive_max") else (d < max_d):
                return float(band["allowance_mm"])
        elif min_d is not None and d > min_d:
            return float(band["allowance_mm"])
    raise ValueError(f"精加工余量表未覆盖 D={d}")


def _structure(hd: float, process: str, rules: dict) -> str:
    if process == "gun_drill":
        return "枪钻"
    for band in rules["structure_by_hd"]:
        max_hd = band.get("max_hd")
        min_hd = band.get("min_hd")
        if min_hd is not None and hd <= min_hd:
            continue
        if max_hd is not None:
            if (hd > max_hd) if band.get("inclusive_max") else (hd >= max_hd):
                continue
        structure = band["structure"]
        # 非钻削工序不存在"枪钻"结构，深孔时用内冷
        if structure == "枪钻" and process not in ROUGH_PROCESSES:
            return "内冷"
        return structure
    raise ValueError(f"结构类型表未覆盖 H/D={hd}")


def _precision(process: str, tolerance_it: int, rules: dict) -> str:
    if process not in FINISH_PROCESSES:
        return "普通"
    for band in rules["precision_by_it"]:
        max_it = band.get("max_it")
        min_it = band.get("min_it")
        if min_it is not None and tolerance_it < min_it:
            continue
        if max_it is not None:
            if (tolerance_it > max_it) if band.get("inclusive_max") else (tolerance_it >= max_it):
                continue
        return band["grade"]
    raise ValueError(f"精度等级表未覆盖 IT{tolerance_it}")


def derive(process: str, hole_d: float, hd: float, material: str, tolerance_it: int, has_finishing: bool) -> ToolAttrs:
    rules = load_rules("hole/tool_attrs.yaml")
    category = rules["process_category"].get(process)
    if category is None:
        raise ValueError(f"工序 {process} 无刀具大类映射")

    if process in rules["relaxed_match_processes"]:
        diameter = None                                   # 不限定，按孔口规格选型
    elif process in ROUGH_PROCESSES and has_finishing:
        diameter = round(hole_d - _allowance(hole_d, rules), 2)
    else:
        diameter = hole_d                                 # 精加工刀具 = 成品孔径；无精加工时粗刀直接成孔

    return ToolAttrs(
        category=category,
        nominal_diameter_mm=diameter,
        structure=_structure(hd, process, rules),
        base_material=rules["base_material_by_material"][material],
        coating=rules["coating_by_material"][material],
        precision_grade=_precision(process, tolerance_it, rules),
    )


def is_relaxed(process: str) -> bool:
    rules = load_rules("hole/tool_attrs.yaml")
    return process in rules["relaxed_match_processes"]


def derive_requirement(process: str, hole_d: float, hd: float, material: str,
                       tolerance_it: int, has_finishing: bool) -> ToolRequirement:
    """生成刀具首选属性和可兼容范围，避免把余量区间过早收敛为单值。"""
    attrs = derive(process, hole_d, hd, material, tolerance_it, has_finishing)
    if attrs.nominal_diameter_mm is None:
        diameter_min = diameter_max = None
    elif process in ROUGH_PROCESSES and has_finishing:
        if hole_d <= 30:
            # 文档2直径余量0.3~0.5，与文档4铰孔单边ap 0.05~0.20求交后为0.3~0.4。
            diameter_min, diameter_max = round(hole_d - 0.4, 3), round(hole_d - 0.3, 3)
        else:
            diameter_min, diameter_max = round(hole_d - 1.0, 3), round(hole_d - 0.5, 3)
    else:
        diameter_min = diameter_max = attrs.nominal_diameter_mm

    material_options = {
        "铝合金": ["硬质合金", "PCD"], "铜合金": ["硬质合金", "PCD"],
        "普通碳钢": ["高速钢", "硬质合金"], "不锈钢": ["硬质合金"],
        "钛合金": ["硬质合金"], "铸铁": ["硬质合金"],
    }
    coating_options = {
        "铝合金": ["无涂层", "DLC"], "铜合金": ["无涂层", "DLC"],
        "普通碳钢": ["TiN"], "不锈钢": ["TiAlN", "AlTiN"],
        "钛合金": ["TiAlN", "AlTiN"], "铸铁": ["TiN"],
    }
    notes = []
    if diameter_min != diameter_max:
        notes.append("优先选择余量区间内的标准刀径；首选值仍用于稳定排序")
    return ToolRequirement(
        preferred_attrs=attrs, diameter_min_mm=diameter_min, diameter_max_mm=diameter_max,
        allowed_base_materials=material_options[material], allowed_coatings=coating_options[material],
        hard_constraints=["刀具大类", "尺寸覆盖", "结构/深度能力", "最低精度", "材料兼容性"],
        selection_notes=notes,
    )
