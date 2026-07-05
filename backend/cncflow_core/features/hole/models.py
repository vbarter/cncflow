"""孔特征输入模型与校验。"""
from dataclasses import dataclass
from typing import Optional

VALID_MATERIALS = ("铝合金", "普通碳钢", "不锈钢", "钛合金", "铸铁", "铜合金")
VALID_HOLE_TYPES = ("through", "blind")
VALID_BOTTOM_SHAPES = ("cone", "flat")
VALID_SURFACES = ("top", "side", "inclined", "curved")

DEFAULT_TOLERANCE_IT = 11  # 钻孔粗加工级（文档1：基础钻孔精度 IT11~IT13）


@dataclass
class HoleSpec:
    diameter_mm: float
    depth_mm: float
    hole_type: str = "through"
    bottom_shape: str = "cone"
    surface: str = "top"
    thread: Optional[dict] = None

    @property
    def h_over_d(self) -> float:
        return self.depth_mm / self.diameter_mm

    @classmethod
    def from_dict(cls, feature: dict) -> "HoleSpec":
        """从请求体 feature 构造并校验，非法输入抛 ValueError（fail fast，含上下文）。"""
        try:
            diameter = float(feature["diameter_mm"])
            depth = float(feature["depth_mm"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("feature.diameter_mm / feature.depth_mm 必填且须为数值")
        if diameter <= 0:
            raise ValueError(f"孔径必须为正数，收到 {diameter}")
        if depth <= 0:
            raise ValueError(f"孔深必须为正数，收到 {depth}")

        hole_type = feature.get("hole_type", "through")
        if hole_type not in VALID_HOLE_TYPES:
            raise ValueError(f"hole_type 须为 {VALID_HOLE_TYPES}，收到 {hole_type!r}")
        bottom_shape = feature.get("bottom_shape", "cone")
        if bottom_shape not in VALID_BOTTOM_SHAPES:
            raise ValueError(f"bottom_shape 须为 {VALID_BOTTOM_SHAPES}，收到 {bottom_shape!r}")
        surface = feature.get("surface", "top")
        if surface not in VALID_SURFACES:
            raise ValueError(f"surface 须为 {VALID_SURFACES}，收到 {surface!r}")

        thread = feature.get("thread")
        if thread is not None and not isinstance(thread, dict):
            raise ValueError('thread 须为对象，如 {"spec": "M12", "depth_mm": 20}')

        return cls(
            diameter_mm=diameter,
            depth_mm=depth,
            hole_type=hole_type,
            bottom_shape=bottom_shape,
            surface=surface,
            thread=thread,
        )


def validate_material(material) -> str:
    if material not in VALID_MATERIALS:
        raise ValueError(f"material 须为 {VALID_MATERIALS}，收到 {material!r}")
    return material


def validate_tolerance_it(tolerance_it) -> int:
    if tolerance_it is None:
        return DEFAULT_TOLERANCE_IT
    it = int(tolerance_it)
    if not 1 <= it <= 18:
        raise ValueError(f"tolerance_it 须在 1~18（IT等级），收到 {tolerance_it}")
    return it
