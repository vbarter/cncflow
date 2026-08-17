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

SLOT_SCHEMA = "slot-v1"
SLOT_FEATURE_FIELDS = (
    "pocket_type",
    "length",
    "width",
    "depth",
    "corner_radius",
)

FACE_SCHEMA = "face-v1"
FACE_FEATURE_FIELDS = (
    "length",
    "width",
    "face_position",
)

THREAD_SCHEMA = "thread-v1"
THREAD_FEATURE_FIELDS = (
    "diameter_mm",
    "pitch",
    "thread_length",
)


STEP_SCHEMA = "step-v1"
STEP_FEATURE_FIELDS = (
    "profile_type",
    "length",
    "height",
)
