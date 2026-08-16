"""Geometry feature service: run registered plugins and merge features."""
from . import FEATURE_SCHEMA, SERVICE_NAME
from .plugins import HOLE_PLUGIN_VERSION, PLUGINS, list_plugins


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
            "询价闭环走 geometry service（in-process），不再直接调用 parse_step",
            "Ø8 / ZN-010 hole-v3 不得回退",
            "槽/面只留插件位，本轮不验收",
        ],
    }


def parse_step_file(path: str) -> dict:
    """STEP in, features out. hole-v3 plus empty slot/face stubs."""
    features = []
    warnings = []
    geometry = None
    engine = None
    engine_version = None
    plugin_runs = []

    for plugin in PLUGINS:
        raw = plugin["recognize"](path)
        if isinstance(raw, dict):
            extra = list(raw.get("features") or [])
            warnings.extend(raw.get("warnings") or [])
            if raw.get("geometry") is not None and geometry is None:
                geometry = raw["geometry"]
            engine = raw.get("parser") or engine
            engine_version = raw.get("parser_version") or engine_version
        else:
            extra = list(raw or [])
        features.extend(extra)
        plugin_runs.append({
            "id": plugin["id"],
            "name": plugin["name"],
            "status": plugin["status"],
            "accepted": plugin["accepted"],
            "version": plugin["version"],
            "feature_count": len(extra),
        })

    return {
        "service": SERVICE_NAME,
        "parser": "geometry-service",
        "parser_version": HOLE_PLUGIN_VERSION,
        "feature_schema": FEATURE_SCHEMA,
        "engine": engine,
        "engine_version": engine_version,
        "geometry": geometry,
        "features": features,
        "warnings": warnings,
        "plugins": plugin_runs,
    }
