"""几何特征服务：询价 parse-job 进程内调用；孔字段与 hole-v3 现网一致。"""
from . import FEATURE_SCHEMA, FACE_FEATURE_FIELDS, FACE_SCHEMA, HOLE_FEATURE_FIELDS, SERVICE_NAME, SLOT_FEATURE_FIELDS, SLOT_SCHEMA, STEP_FEATURE_FIELDS, STEP_SCHEMA, SURFACE_FEATURE_FIELDS, SURFACE_SCHEMA, THREAD_FEATURE_FIELDS, THREAD_SCHEMA
from .plugins import list_plugins, plugin_names, run_face, run_slot, run_step, run_surface, run_thread


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
                "surface": {
                    "status": "active",
                    "accepted": True,
                    "version": SURFACE_SCHEMA,
                    "fields": list(SURFACE_FEATURE_FIELDS),
                },
            },
            "plugins": "hole+slot+face+thread+step+surface active",
        },
        "plugins": list_plugins(),
        "notes": [
            "询价 parse-job 进程内调用 geometry service，Ø8/ZN-010 仍走现网 parse-jobs",
            "Ø8 / ZN-010 hole-v3 不得回退",
            "台阶本轮验收；孔五字段、槽腔、平面、螺纹不回退",
            "曲面最小集 surface_type/R/position 本轮验收；孔/槽/面/螺纹/台阶不回退",
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



def _feat_num(feat, *keys):
    dim = feat.get("dimensions") or {}
    for key in keys:
        raw = feat.get(key)
        if raw is None:
            raw = dim.get(key)
        if raw is None or raw == "":
            continue
        try:
            return float(raw)
        except (TypeError, ValueError):
            continue
    return 0.0


def _covers_stock_lw(length, width, stock_l, stock_w, ratio=0.8):
    """整板顶面才默认面铣；台阶肩顶（半幅 80×25）盖不住毛坯 XY。"""
    if not stock_l or not stock_w or length <= 0 or width <= 0:
        return True
    face_l, face_w = max(length, width), min(length, width)
    sl, sw = max(float(stock_l), float(stock_w)), min(float(stock_l), float(stock_w))
    return face_l + 1e-6 >= ratio * sl and face_w + 1e-6 >= ratio * sw


def _is_horizontal_face(feat):
    if feat.get("type") != "face" and feat.get("subtype") != "recognized_face":
        return False
    pos = feat.get("face_position") or (feat.get("dimensions") or {}).get("face_position") or "水平"
    return pos == "水平"


def _unselect_step_shoulder_tops(features):
    """台阶肩顶不当默认面铣。Ø8 整板顶面无台阶，勾选不动。特征仍保留供手勾。"""
    steps = [f for f in features if f.get("type") == "step" or f.get("subtype") == "recognized_step"]
    if not steps:
        return features
    for feat in features:
        if not _is_horizontal_face(feat):
            continue
        if feat.get("selected") is False:
            continue
        length = _feat_num(feat, "length")
        width = _feat_num(feat, "width")
        if length <= 0 or width <= 0:
            continue
        face_area = length * width
        for step in steps:
            step_l = _feat_num(step, "length")
            step_w = _feat_num(step, "width")
            same_footprint = (
                step_l > 0 and step_w > 0
                and abs(length - step_l) <= 3 and abs(width - step_w) <= 3
            )
            step_area = step_l * step_w if step_l > 0 and step_w > 0 else 0.0
            partial = step_area > 0 and face_area < 0.8 * (face_area + step_area)
            if same_footprint or partial:
                feat["selected"] = False
                break
    return features


def _unselect_partial_stock_tops(features, stock_l, stock_w):
    """盖不住毛坯 XY 的水平顶面不默认勾。无毛坯尺寸则不动。"""
    if not stock_l or not stock_w:
        return features
    for feat in features:
        if not _is_horizontal_face(feat):
            continue
        if feat.get("selected") is False:
            continue
        length = _feat_num(feat, "length")
        width = _feat_num(feat, "width")
        if not _covers_stock_lw(length, width, stock_l, stock_w):
            feat["selected"] = False
    return features


def apply_quote_default_selection(features, stock_l=0, stock_w=0):
    """报价默认勾选：与 parse 同一套肩顶 / 整板 XY 规则。手勾不走这里。"""
    features = _unselect_step_shoulder_tops(features)
    return _unselect_partial_stock_tops(features, stock_l, stock_w)


def _drop_hole_as_surfaces(features):
    """孔壁/倒圆不当曲面。Ø8 / ZN-010 回退不得出 recognized_surface。"""
    holes = [f for f in features if f.get("subtype") == "recognized_hole"]
    if not holes:
        return features
    kept = []
    for feat in features:
        if feat.get("subtype") == "recognized_surface":
            r = feat.get("curvature_radius") or 0
            loc = feat.get("location") or {}
            sx, sy, sz = loc.get("x") or 0, loc.get("y") or 0, loc.get("z") or 0
            skip = False
            for hole in holes:
                d = hole.get("diameter_mm") or 0
                if r and abs(2 * r - d) > 0.8:
                    continue
                hl = hole.get("location") or {}
                dx = sx - (hl.get("x") or 0)
                dy = sy - (hl.get("y") or 0)
                dz = sz - (hl.get("z") or 0)
                if dx * dx + dy * dy + dz * dz <= 64:
                    skip = True
                    break
            if skip:
                continue
        kept.append(feat)
    return kept


def parse_step_file(path):
    """STEP → features。hole/slot/face/thread/step/surface。"""
    from cncflow_core.ingestion.step_parser import parse_step

    result = parse_step(path)
    features = list(result.get("features") or [])
    features.extend(run_slot(path))
    features.extend(run_face(path))
    features.extend(run_thread(path))
    features.extend(run_step(path))
    features.extend(run_surface(path))
    features = _drop_slot_fillet_holes(features)
    features = _drop_slot_as_steps(features)
    features = _drop_threaded_holes(features)
    features = _drop_hole_as_surfaces(features)
    features = _unselect_step_shoulder_tops(features)
    result["service"] = SERVICE_NAME
    result["parser"] = "geometry-service"
    result["parser_version"] = FEATURE_SCHEMA
    result["feature_schema"] = FEATURE_SCHEMA
    result["plugins"] = list_plugins()
    result["plugin_names"] = plugin_names()
    result["features"] = features
    return result
