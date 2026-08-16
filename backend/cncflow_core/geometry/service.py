"""几何特征服务：询价 parse-job 进程内调用；孔字段与 hole-v3 现网一致。"""
from . import FEATURE_SCHEMA, HOLE_FEATURE_FIELDS, SERVICE_NAME, SLOT_FEATURE_FIELDS, SLOT_SCHEMA
from .plugins import list_plugins, plugin_names, run_face, run_slot


def contract():
    hole_fields = list(HOLE_FEATURE_FIELDS)
    slot_fields = list(SLOT_FEATURE_FIELDS)
    return {
        "service": SERVICE_NAME,
        "endpoint": "POST /api/v1/geometry/parse",
        "input": {"multipart": ["step_file"], "formats": ["step", "stp"]},
        "output": {
            "feature_schema": FEATURE_SCHEMA,
            "feature_fields": hole_fields,
            "features": {
                "hole": {
                    "status": "active",
                    "version": FEATURE_SCHEMA,
                    "fields": hole_fields,
                },
                "slot": {
                    "status": "active",
                    "accepted": True,
                    "version": SLOT_SCHEMA,
                    "fields": slot_fields,
                },
                "face": {"status": "stub", "accepted": False},
            },
            "plugins": "hole+slot active; face stub",
        },
        "plugins": list_plugins(),
        "notes": [
            "询价 parse-job 进程内调用 geometry service，Ø8/ZN-010 仍走现网 parse-jobs",
            "Ø8 / ZN-010 hole-v3 不得回退",
            "槽本轮验收；孔五字段不回退",
            "槽腔最小集 pocket_type/L/W/H/R 本轮验收；平面仍留桩",
        ],
    }


def parse_step_file(path):
    """STEP → features。hole 走现网 parse_step 一次；slot 识别凹腔；face 空桩。"""
    from cncflow_core.ingestion.step_parser import parse_step

    result = parse_step(path)
    features = list(result.get("features") or [])
    features.extend(run_slot(path))
    features.extend(run_face(path))
    result["service"] = SERVICE_NAME
    result["parser"] = "geometry-service"
    result["parser_version"] = FEATURE_SCHEMA
    result["feature_schema"] = FEATURE_SCHEMA
    result["plugins"] = list_plugins()
    result["plugin_names"] = plugin_names()
    result["features"] = features
    return result
