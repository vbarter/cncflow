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


def _is_slot_fillet_hole(hole, slots):
    """槽腔内角圆柱（D≈2R）不当孔，Ø8/ZN-010 真孔不在槽角上。"""
    d = hole.get("diameter_mm") or 0
    loc = hole.get("location") or {}
    hx = loc.get("x") or 0
    hy = loc.get("y") or 0
    hz = loc.get("z") or 0
    for slot in slots:
        r = slot.get("corner_radius") or 0
        if r < 0.05 or abs(d - 2 * r) > 0.6:
            continue
        sl = slot.get("location") or {}
        dx = hx - (sl.get("x") or 0)
        dy = hy - (sl.get("y") or 0)
        dz = hz - (sl.get("z") or 0)
        reach = max(slot.get("length") or 0, slot.get("width") or 0, slot.get("depth") or 0, 12) * 0.8 + 6
        if dx * dx + dy * dy + dz * dz <= reach * reach:
            return True
    return False


def _drop_slot_fillet_holes(features):
    slots = [f for f in features if f.get("subtype") == "recognized_slot"]
    if not slots:
        return features
    kept = []
    for feat in features:
        if feat.get("subtype") == "recognized_hole" and _is_slot_fillet_hole(feat, slots):
            continue
        kept.append(feat)
    return kept


def parse_step_file(path):
    """STEP → features。hole 走现网 parse_step 一次；slot 识别凹腔；face 空桩。"""
    from cncflow_core.ingestion.step_parser import parse_step

    result = parse_step(path)
    features = list(result.get("features") or [])
    features.extend(run_slot(path))
    features.extend(run_face(path))
    features = _drop_slot_fillet_holes(features)
    result["service"] = SERVICE_NAME
    result["parser"] = "geometry-service"
    result["parser_version"] = FEATURE_SCHEMA
    result["feature_schema"] = FEATURE_SCHEMA
    result["plugins"] = list_plugins()
    result["plugin_names"] = plugin_names()
    result["features"] = features
    return result
