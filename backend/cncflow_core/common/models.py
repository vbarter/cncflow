"""跨特征共享的数据模型。"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ToolAttrs:
    """单刀 5 项硬性属性（文档2）。nominal_diameter_mm 为 None 表示不限定（倒角刀/中心钻）。"""

    category: str
    nominal_diameter_mm: Optional[float]
    structure: str
    base_material: str
    coating: str
    precision_grade: str

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "nominal_diameter_mm": self.nominal_diameter_mm,
            "structure": self.structure,
            "base_material": self.base_material,
            "coating": self.coating,
            "precision_grade": self.precision_grade,
        }


@dataclass
class ToolRequirement:
    """工序对刀具的可接受范围；preferred_attrs 用于保持旧接口和首选排序。"""

    preferred_attrs: ToolAttrs
    diameter_min_mm: Optional[float]
    diameter_max_mm: Optional[float]
    allowed_base_materials: list
    allowed_coatings: list
    hard_constraints: list = field(default_factory=list)
    selection_notes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "preferred": self.preferred_attrs.to_dict(),
            "diameter_min_mm": self.diameter_min_mm,
            "diameter_max_mm": self.diameter_max_mm,
            "allowed_base_materials": self.allowed_base_materials,
            "allowed_coatings": self.allowed_coatings,
            "hard_constraints": self.hard_constraints,
            "selection_notes": self.selection_notes,
        }


@dataclass
class CuttingParams:
    vc_m_min: float
    spindle_rpm: int
    feed_per_rev_mm: float
    cutting_depth: str
    coolant: str
    feed_rate_mm_min: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "vc_m_min": self.vc_m_min,
            "spindle_rpm": self.spindle_rpm,
            "feed_per_rev_mm": self.feed_per_rev_mm,
            "cutting_depth": self.cutting_depth,
            "coolant": self.coolant,
            "feed_rate_mm_min": self.feed_rate_mm_min,
        }


@dataclass
class MachinabilityResult:
    level: int
    label: str
    risk_notes: list = field(default_factory=list)
    fired_rules: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "label": self.label,
            "risk_notes": self.risk_notes,
            "fired_rules": self.fired_rules,
        }
