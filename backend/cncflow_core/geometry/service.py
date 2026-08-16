"""几何特征服务：询价 parse-job 进程内调用；孔字段与 hole-v3 现网一致。"""
from . import FEATURE_SCHEMA, HOLE_FEATURE_FIELDS, SERVICE_NAME
from .plugins import list_plugins, plugin_names, run_face, run_slot


def contract():
    fields = list(HOLE_FEATURE_FIELDS)
    return {
        "service": SERVICE_NAME,
        "endpoint": "POST /api/v1/geometry/parse",
        "input": {"multipart": ["step_file"], "formats": ["step", "stp"]},
        "output": {
            "feature_schema": FEATURE_SCHEMA,
            "feature_fields": fields,
            "features": {
                "hole": {
                    "status": "active",
                    "version": FEATURE_SCHEMA,
                    "fields": fields,
                },
                "slot": {"status": "stub", "accepted": False},
                "face": {"status": "stub", "accepted": False},
            },
            "plugins": "hole active; slot/face stub",
        },
        "plugins": list_plugins(),
        "notes": [
            "询价 parse-job 进程内调用 geometry service，Ø8/ZN-010 仍走现网 parse-jobs",
            "Ø8 / ZN-010 hole-v3 不得回退",
            "槽/面只留插件位，本轮不验收",
        ],
    }


def parse_step_file(path):
    """STEP → features。hole 走现网 parse_step 一次；slot/face 空桩。"""
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
