"""平面 B-Rep 识别：外轮廓平面，产出 L / W / face_position。"""
from cncflow_core.ingestion.step_parser import _face_normal, _norm, _point, _xyz
from cncflow_core.geometry.slot import _face_on_bbox, _is_hole_bottom


def _face_position(normal, _center, _bbox, thick_axis):
    if abs(normal[thick_axis]) >= 0.85:
        return "水平"
    if max(abs(normal[0]), abs(normal[1]), abs(normal[2])) >= 0.85:
        return "垂直"
    return "倾斜"


def _is_top_face(normal, center, bbox, thick_axis):
    lo = (bbox.xmin, bbox.ymin, bbox.zmin)[thick_axis]
    hi = (bbox.xmax, bbox.ymax, bbox.zmax)[thick_axis]
    if abs(normal[thick_axis]) < 0.85:
        return False
    return abs(center[thick_axis] - hi) <= abs(center[thick_axis] - lo)


def _bbox_spans(bbox):
    x = getattr(bbox, "xlen", None)
    y = getattr(bbox, "ylen", None)
    z = getattr(bbox, "zlen", None)
    if x is None or y is None or z is None:
        x = bbox.xmax - bbox.xmin
        y = bbox.ymax - bbox.ymin
        z = bbox.zmax - bbox.zmin
    return (x, y, z)


def _covers_stock_xy(length, width, bbox, thick_axis, ratio=0.8):
    """整板顶面才默认面铣；台阶肩顶（半幅 80×25）盖不住毛坯 XY。"""
    spans = list(_bbox_spans(bbox))
    spans.pop(thick_axis)
    stock_l, stock_w = max(spans), min(spans)
    return float(length) + 1e-6 >= ratio * stock_l and float(width) + 1e-6 >= ratio * stock_w


def _measure_lw(fb):
    dims = sorted((fb.xlen, fb.ylen, fb.zlen), reverse=True)
    return dims[0], dims[1]


def detect_faces(path: str) -> list:
    try:
        import cadquery as cq
    except ImportError:
        return []

    try:
        imported = cq.importers.importStep(path)
        values = imported.vals()
        if not values:
            return []
        compound = cq.Compound.makeCompound(values) if len(values) > 1 else values[0]
        if not compound.Solids():
            return []
    except Exception:
        return []

    bbox = compound.BoundingBox()
    extents = (bbox.xlen, bbox.ylen, bbox.zlen)
    thick_axis = min(range(3), key=lambda i: extents[i])
    candidates = []
    for index, face in enumerate(compound.Faces()):
        if face.geomType() != "PLANE":
            continue
        if _is_hole_bottom(face):
            continue
        fb = face.BoundingBox()
        if not _face_on_bbox(fb, bbox):
            continue
        normal = _face_normal(face)
        if not normal:
            continue
        n, mag = _norm(normal)
        if mag < 1e-9:
            continue
        length, width = _measure_lw(fb)
        area = float(face.Area())
        if width < 2 or area < 50:
            continue
        candidates.append({
            "index": index,
            "fb": fb,
            "c": _xyz(face.Center()),
            "n": n,
            "area": area,
            "length": length,
            "width": width,
        })

    if not candidates:
        return []
    max_area = max(item["area"] for item in candidates)
    floor = max(80.0, 0.2 * max_area)
    found = []
    for item in candidates:
        if item["area"] < floor:
            continue
        pos = _face_position(item["n"], item["c"], bbox, thick_axis)
        length = round(item["length"], 4)
        width = round(item["width"], 4)
        area = round(item["area"], 4)
        found.append({
            "feature_id": "face-%d" % len(found),
            "type": "face",
            "subtype": "recognized_face",
            "selected": False,
            "length": length,
            "width": width,
            "area": area,
            "face_position": pos,
            "dimensions": {
                "length": length,
                "width": width,
                "area": area,
                "face_position": pos,
            },
            "location": _point(item["c"]),
            "axis": {
                "x": round(item["n"][0], 6),
                "y": round(item["n"][1], 6),
                "z": round(item["n"][2], 6),
            },
            "occurrences": 1,
            "confidence": 0.8,
            "evidence": [
                "outer-plane",
                "L=%.3f" % length,
                "W=%.3f" % width,
                pos,
            ],
            "warnings": [],
        })
    tops = [f for f in found if f["face_position"] == "水平" and _is_top_face(
        (f["axis"]["x"], f["axis"]["y"], f["axis"]["z"]),
        (f["location"]["x"], f["location"]["y"], f["location"]["z"]),
        bbox, thick_axis,
    ) and _covers_stock_xy(f["length"], f["width"], bbox, thick_axis)]
    if tops:
        max(tops, key=lambda f: f["length"] * f["width"])["selected"] = True
    return found
