"""几何特征服务：询价 parse-job 进程内调用；孔字段与 hole-v3 现网一致。"""
from . import FEATURE_SCHEMA, FACE_FEATURE_FIELDS, FACE_SCHEMA, HOLE_FEATURE_FIELDS, SERVICE_NAME, SLOT_FEATURE_FIELDS, SLOT_SCHEMA, STEP_FEATURE_FIELDS, STEP_SCHEMA, THREAD_FEATURE_FIELDS, THREAD_SCHEMA
from .plugins import list_plugins, plugin_names, run_face, run_slot, run_step, run_thread


def contract():
    hole_fields = list(HOLE_FEATURE_FIELDS)
    slot_fields = list(SLOT_FEATURE_FIELDS)
    face_fields = list(FACE_FEATURE_FIELDS)
    thread_fields = list(THREAD_FEATURE_FIELDS)
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
                "face": {
                    "status": "active",
                    "accepted": True,
                    "version": FACE_SCHEMA,
                    "fields": face_fields,
                },
                "thread": {
                    "status": "active",
                    "accepted": True,
                    "version": THREAD_SCHEMA,
                    "fields": thread_fields,
                },
                "step": {
                    "status": "active",
                    "accepted": True,
                    "version": STEP_SCHEMA,
                    "fields": list(STEP_FEATURE_FIELDS),
                },
            },
            "plugins": "hole+slot+face+thread+step active",
        },
        "plugins": list_plugins(),
        "notes": [
            "询价 parse-job 进程内调用 geometry service，Ø8/ZN-010 仍走现网 parse-jobs",
            "Ø8 / ZN-010 hole-v3 不得回退",
            "台阶本轮验收；孔五字段、槽腔、平面、螺纹不回退",
            "台阶最小集 profile_type/L/H 本轮验收；孔/槽/面/螺纹不回退；曲面仍留桩",
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



def _drop_threaded_holes(features):
    """已认成螺纹的孔不再当光孔报价。Ø8/ZN-010 无螺旋，不会被摘。"""
    threads = [f for f in features if f.get("subtype") == "recognized_thread"]
    if not threads:
        return features
    kept = []
    for feat in features:
        if feat.get("subtype") == "recognized_hole":
            d = feat.get("diameter_mm") or 0
            loc = feat.get("location") or {}
            hx, hy, hz = loc.get("x") or 0, loc.get("y") or 0, loc.get("z") or 0
            skip = False
            for th in threads:
                major = th.get("diameter_mm") or 0
                pitch = th.get("pitch") or 0
                minor = major - pitch if pitch else major
                if min(abs(major - d), abs(minor - d)) > 0.8:
                    continue
                tl = th.get("location") or {}
                dx = hx - (tl.get("x") or 0)
                dy = hy - (tl.get("y") or 0)
                dz = hz - (tl.get("z") or 0)
                if dx * dx + dy * dy + dz * dz <= 36:
                    skip = True
                    break
            if skip:
                continue
        kept.append(feat)
    return kept


def _drop_slot_as_steps(features):
    """槽底不当台阶。开口槽回退不得出 recognized_step。"""
    slots = [f for f in features if f.get("subtype") == "recognized_slot"]
    if not slots:
        return features
    kept = []
    for feat in features:
        if feat.get("subtype") == "recognized_step":
            loc = feat.get("location") or {}
            sx, sy, sz = loc.get("x") or 0, loc.get("y") or 0, loc.get("z") or 0
            skip = False
            for slot in slots:
                sl = slot.get("location") or {}
                dx = sx - (sl.get("x") or 0)
                dy = sy - (sl.get("y") or 0)
                dz = sz - (sl.get("z") or 0)
                reach = max(slot.get("length") or 0, slot.get("width") or 0, 20) * 0.7 + 8
                if dx * dx + dy * dy + dz * dz <= reach * reach:
                    skip = True
                    break
            if skip:
                continue
        kept.append(feat)
    return kept


def parse_step_file(path):
    """STEP → features。hole/slot/face/thread/step。"""
    from cncflow_core.ingestion.step_parser import parse_step

    result = parse_step(path)
    features = list(result.get("features") or [])
    features.extend(run_slot(path))
    features.extend(run_face(path))
    features.extend(run_thread(path))
    features.extend(run_step(path))
    features = _drop_slot_fillet_holes(features)
    features = _drop_slot_as_steps(features)
    features = _drop_threaded_holes(features)
    result["service"] = SERVICE_NAME
    result["parser"] = "geometry-service"
    result["parser_version"] = FEATURE_SCHEMA
    result["feature_schema"] = FEATURE_SCHEMA
    result["plugins"] = list_plugins()
    result["plugin_names"] = plugin_names()
    result["features"] = features
    return result
