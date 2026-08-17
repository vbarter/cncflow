"""台阶轮廓 B-Rep：中间水平台面才出 profile_type / L / H。"""
from cncflow_core.ingestion.step_parser import _face_normal, _norm, _point, _xyz


def _is_horizontal(normal, thick_axis):
    return abs(normal[thick_axis]) >= 0.85


def detect_steps(path: str) -> list:
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
    lo = (bbox.xmin, bbox.ymin, bbox.zmin)[thick_axis]
    hi = (bbox.xmax, bbox.ymax, bbox.zmax)[thick_axis]
    stock = extents[thick_axis]
    if stock < 2:
        return []

    planes = []
    for face in compound.Faces():
        if str(face.geomType() or "").upper() != "PLANE":
            continue
        normal = _face_normal(face)
        if not normal:
            continue
        n, mag = _norm(normal)
        if mag < 1e-9 or not _is_horizontal(n, thick_axis):
            continue
        fb = face.BoundingBox()
        z = (fb.xmin + fb.xmax, fb.ymin + fb.ymax, fb.zmin + fb.zmax)[thick_axis] / 2
        xy = [fb.xlen, fb.ylen, fb.zlen]
        xy.pop(thick_axis)
        length, width = max(xy), min(xy)
        area = float(face.Area())
        if width < 8 or area < 80:
            continue
        planes.append({
            "z": z, "fb": fb, "c": _xyz(face.Center()),
            "length": length, "width": width, "area": area, "n": n,
        })
    if len(planes) < 3:
        return []

    zs = sorted({round(p["z"], 2) for p in planes})
    if len(zs) < 3:
        return []

    found = []
    for plane in planes:
        z = plane["z"]
        if z <= lo + 0.6 or z >= hi - 0.6:
            continue
        higher = [v for v in zs if v > z + 0.4]
        if not higher:
            continue
        height = min(higher) - z
        if height < 1.2 or height > stock + 0.2:
            continue
        # 窄台面留给槽插件，避免开口槽底被编成台阶
        if plane["width"] < max(15.0, 0.28 * max(extents[0], extents[1], extents[2])):
            continue
        found.append({
            "feature_id": "step-%d" % len(found),
            "type": "step",
            "subtype": "recognized_step",
            "selected": True,
            "profile_type": "台阶",
            "length": round(plane["length"], 4),
            "height": round(height, 4),
            "width": round(plane["width"], 4),
            "dimensions": {
                "profile_type": "台阶",
                "length": round(plane["length"], 4),
                "height": round(height, 4),
            },
            "location": _point(plane["c"]),
            "axis": {"x": 0, "y": 0, "z": 1} if thick_axis == 2 else (
                {"x": 1, "y": 0, "z": 0} if thick_axis == 0 else {"x": 0, "y": 1, "z": 0}
            ),
            "occurrences": 1,
            "confidence": 0.76,
            "evidence": [
                "shoulder-plane",
                "type=台阶",
                "L=%.3f" % plane["length"],
                "H=%.3f" % height,
            ],
            "warnings": [],
        })
    if not found:
        return []
    found.sort(key=lambda item: item["length"] * item.get("width", 1), reverse=True)
    for i, item in enumerate(found):
        item["feature_id"] = "step-%d" % i
        item["selected"] = i == 0
    return found[:3]
