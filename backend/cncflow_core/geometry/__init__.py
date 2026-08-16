"""几何特征服务：STEP 进、features 出。孔/槽/面为插件。"""

FEATURE_SCHEMA = "hole-v3"
SERVICE_NAME = "geometry"
HOLE_FEATURE_FIELDS = (
    "diameter_mm",
    "depth_mm",
    "hole_type",
    "position_type",
    "cut_depth_mm",
)
