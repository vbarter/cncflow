"""曲面 B-Rep 识别：凸/凹/球/自由曲面 + 曲率 R；倒圆不当曲面。"""
from cncflow_core.ingestion.step_parser import _face_normal, _norm, _point, _xyz


def _cyl_info(face):
    try:
        cyl = face._geomAdaptor().Cylinder()
        radius = float(cyl.Radius())
        axis = cyl.Axis()
        loc = axis.Location()
        direction = axis.Direction()
        origin = (float(loc.X()), float(loc.Y()), float(loc.Z()))
        axis_dir = (float(direction.X()), float(direction.Y()), float(direction.Z()))
        return radius, origin, axis_dir
    except Exception:
        return None, None, None


def _sphere_radius(face):
    try:
        return float(face._geomAdaptor().Sphere().Radius())
    except Exception:
        try:
            return float(face.radius())
        except Exception:
            return None


def _is_convex_cyl(face, origin, axis):
    normal = _face_normal(face)
    if not normal:
        return None
    nvec, mag = _norm(normal)
    if mag < 1e-9:
        return None
    ax, amag = _norm(axis)
    if amag < 1e-9:
        return None
    center = _xyz(face.Center())
    rel = (center[0] - origin[0], center[1] - origin[1], center[2] - origin[2])
    along = rel[0] * ax[0] + rel[1] * ax[1] + rel[2] * ax[2]
    radial = (rel[0] - along * ax[0], rel[1] - along * ax[1], rel[2] - along * ax[2])
    return radial[0] * nvec[0] + radial[1] * nvec[1] + radial[2] * nvec[2] > 0


def _position(center, bbox, thick_axis):
    lo = (bbox.xmin, bbox.ymin, bbox.zmin)[thick_axis]
    hi = (bbox.xmax, bbox.ymax, bbox.zmax)[thick_axis]
    mid = center[thick_axis]
    span = max(hi - lo, 1e-6)
    if abs(mid - hi) <= abs(mid - lo) and abs(mid - hi) < 0.4 * span:
        return "顶面"
    if abs(mid - lo) < 0.4 * span:
        return "底面"
    return "侧面"


def _emit(index, surface_type, radius, face, bbox, thick_axis, extra=None):
    fb = face.BoundingBox()
    dims = sorted((fb.xlen, fb.ylen, fb.zlen), reverse=True)
    center = _xyz(face.Center())
    item = {
        "feature_id": "surface-%d" % index,
        "type": "surface",
        "subtype": "recognized_surface",
        "selected": True,
        "surface_type": surface_type,
        "curvature_radius": None if radius is None else round(float(radius), 4),
        "position": _position(center, bbox, thick_axis),
        "length": round(dims[0], 4),
        "width": round(dims[1], 4),
        "dimensions": {
            "surface_type": surface_type,
            "curvature_radius": None if radius is None else round(float(radius), 4),
            "position": _position(center, bbox, thick_axis),
        },
        "location": _point(center),
        "occurrences": 1,
        "confidence": 0.74,
        "evidence": [
            "surface_type=%s" % surface_type,
            "R=%.3f" % radius if radius is not None else "R=?",
        ],
        "warnings": [],
        "area": float(face.Area()),
    }
    if extra:
        item["evidence"].extend(extra)
    return item


def detect_surfaces(path: str) -> list:
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
    stock = max(extents)
    found = []
    for face in compound.Faces():
        kind = str(face.geomType() or "").upper()
        area = float(face.Area())
        if kind == "TORUS":
            continue
        if kind == "PLANE":
            continue
        if kind == "CYLINDER":
            radius, origin, axis = _cyl_info(face)
            if radius is None or radius < 3.0:
                continue
            # 倒圆/孔壁：面积小或内凹细圆柱
            if area < max(180.0, 8.0 * radius):
                continue
            convex = _is_convex_cyl(face, origin, axis) if origin and axis else None
            if convex is False and radius < 16:
                continue
            surface_type = "凸面" if convex else "凹面"
            found.append(_emit(len(found), surface_type, radius, face, bbox, thick_axis))
            continue
        if kind == "SPHERE":
            radius = _sphere_radius(face)
            if radius is None or radius < 3.0 or area < 180:
                continue
            found.append(_emit(len(found), "球面", radius, face, bbox, thick_axis))
            continue
        if kind in {"CONE", "CIRCLE"}:
            continue
        # 自由曲面：只要够大，排除倒圆过渡
        if area < max(400.0, 0.04 * stock * stock):
            continue
        found.append(_emit(len(found), "自由曲面", None, face, bbox, thick_axis, extra=["freeform"]))

    if not found:
        return []
    found.sort(key=lambda item: item.get("area") or 0, reverse=True)
    for i, item in enumerate(found):
        item["feature_id"] = "surface-%d" % i
        item["selected"] = i == 0
        item.pop("area", None)
    return found[:4]
