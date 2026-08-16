"""几何特征服务契约实现（本轮不改询价接线）。"""
from . import FEATURE_SCHEMA, SERVICE_NAME
from .plugins import list_plugins, run_face, run_slot


def contract():
    return {
        "service": SERVICE_NAME,
        "endpoint": "POST /api/v1/geometry/parse",
        "input": {"multipart": ["step_file"], "formats": ["step", "stp"]},
        "output": {
            "feature_schema": FEATURE_SCHEMA,
            "features": "recognized_hole / outer_cylinder / candidates",
            "plugins": "hole active; slot/face stub",
        },
        "plugins": list_plugins(),
        "notes": [
            "询价闭环本轮不改，仍走 parse-jobs",
            "Ø8 / ZN-010 hole-v3 不得回退",
            "槽/面只留插件位，本轮不验收",
        ],
    }


def parse_step_file(path):
    """STEP → features。hole 走现网 parse_step；slot/face 空。"""
    from cncflow_core.ingestion.step_parser import parse_step

    result = parse_step(path)
    features = list(result.get("features") or [])
    features.extend(run_slot(path))
    features.extend(run_face(path))
    result["service"] = SERVICE_NAME
    result["feature_schema"] = FEATURE_SCHEMA
    result["plugins"] = list_plugins()
    result["features"] = features
    return result
