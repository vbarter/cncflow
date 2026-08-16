"""STEP B-Rep metrics and hole recognition (CadQuery/OCP)."""
import math

POSITION_TYPES = ("垂直", "倾斜", "曲面", "侧向", "深腔")
SURFACE_FROM_POSITION = {
    "垂直": "top",
    "倾斜": "inclined",
    "曲面": "curved",
    "侧向": "side",
    "深腔": "top",
}
ALIGN_COS = math.cos(math.radians(15))
THROUGH_SPAN = 0.88
RECESS_MM = 2.0


def _point(value):
    return {"x": round(value.x, 4), "y": round(value.y, 4), "z": round(value.z, 4)}


def _bbox(box):
    return {"x": round(box.xlen, 4), "y": round(box.ylen, 4), "z": round(box.zlen, 4)}


def _face_radius(face):
    try:
        return float(face._geomAdaptor().Cylinder().Radius())
    except Exception:
        try:
            return float(face.radius())
        except Exception:
            return None


def _norm(vec):
    mag = math.sqrt(vec[0] ** 2 + vec[1] ** 2 + vec[2] ** 2)
    if mag < 1e-9:
        return (0.0, 0.0, 0.0), 0.0
    return (vec[0] / mag, vec[1] / mag, vec[2] / mag), mag


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def classify_cylinder_side(normal, radial):
    """Outward normal toward axis -> inner hole; away -> outer cylinder."""
    n, nm = _norm(normal)
    r, rm = _norm(radial)
    if nm < 1e-9 or rm < 1e-9:
        return None
    score = _dot(n, r)
    if score < -0.15:
        return "inner"
    if score > 0.15:
        return "outer"
    return None


def classify_position(axis, extents, entry_curved=False, entry_recessed=False):
    if entry_curved:
        return "曲面"
    if entry_recessed:
        return "深腔"
    ax = (abs(axis[0]), abs(axis[1]), abs(axis[2]))
    dom = max(range(3), key=lambda i: ax[i])
    if ax[dom] < ALIGN_COS:
        return "倾斜"
    shortest = min(range(3), key=lambda i: extents[i])
    if dom == shortest:
        return "垂直"
    return "侧向"


def classify_through_blind(cyl_min, cyl_max, solid_min, solid_max):
    solid_span = solid_max - solid_min
    if solid_span <= 1e-6:
        return "blind"
    span = (cyl_max - cyl_min) / solid_span
    inset_lo = cyl_min - solid_min
    inset_hi = solid_max - cyl_max
    if span >= THROUGH_SPAN and min(inset_lo, inset_hi) <= RECESS_MM:
        return "through"
    return "blind"


def is_recessed(cyl_min, cyl_max, solid_min, solid_max):
    return (cyl_min - solid_min) > RECESS_MM and (solid_max - cyl_max) > RECESS_MM


def through_cut_depth(diameter_mm, depth_mm, hole_type):
    extra = 0.3 * float(diameter_mm) if hole_type == "through" else 0.0
    return round(float(depth_mm) + extra, 4)


def classify_by_containment(toward_axis_inside, away_inside):
    """轴心侧是空腔、外侧是实体 → 内孔。"""
    if toward_axis_inside is None or away_inside is None:
        return None
    if (not toward_axis_inside) and away_inside:
        return "inner"
    if toward_axis_inside and (not away_inside):
        return "outer"
    return None


def likely_plate_hole(diameter, cyl_min, cyl_max, solid_min, solid_max, extents):
    """圆柱接近最薄边厚度、直径明显更小 → 当孔。"""
    shortest = min(extents)
    depth = cyl_max - cyl_min
    return diameter < shortest * 0.95 and depth >= shortest * 0.7


def _axis_from_face(face):
    cylinder = face._geomAdaptor().Cylinder()
    direction = cylinder.Axis().Direction()
    origin = cylinder.Axis().Location()
    axis = (float(direction.X()), float(direction.Y()), float(direction.Z()))
    loc = (float(origin.X()), float(origin.Y()), float(origin.Z()))
    return axis, loc


def _project(point, axis):
    return point[0] * axis[0] + point[1] * axis[1] + point[2] * axis[2]


def _cylinder_axis_and_span(face):
    axis, origin = _axis_from_face(face)
    axis, mag = _norm(axis)
    if mag < 1e-9:
        return None, origin, None, None
    projections = []
    for vertex in face.Vertices():
        pt = vertex.Center()
        projections.append(_project((pt.x, pt.y, pt.z), axis))
    try:
        fb = face.BoundingBox()
        for dx in (fb.xmin, fb.xmax):
            for dy in (fb.ymin, fb.ymax):
                for dz in (fb.zmin, fb.zmax):
                    projections.append(_project((dx, dy, dz), axis))
    except Exception:
        pass
    if len(projections) < 2:
        return axis, origin, None, None
    return axis, origin, min(projections), max(projections)


def _radial_at_center(face, axis, origin):
    c = face.Center()
    vec = (c.x - origin[0], c.y - origin[1], c.z - origin[2])
    t = _dot(vec, axis)
    closest = (origin[0] + t * axis[0], origin[1] + t * axis[1], origin[2] + t * axis[2])
    return (c.x - closest[0], c.y - closest[1], c.z - closest[2])


def _face_normal(face):
    try:
        n = face.normalAt()
        vec = (float(n.x), float(n.y), float(n.z))
    except Exception:
        try:
            n = face.normalAt(None)
            vec = (float(n.x), float(n.y), float(n.z))
        except Exception:
            return None
    try:
        if int(face.wrapped.Orientation()) == 1:
            vec = (-vec[0], -vec[1], -vec[2])
    except Exception:
        pass
    return vec


def _point_inside(solid, xyz):
    try:
        import cadquery as cq
        return bool(solid.isInside(cq.Vector(xyz[0], xyz[1], xyz[2])))
    except Exception:
        try:
            return bool(solid.isInside(xyz))
        except Exception:
            return None


def classify_side(solids, center, axis, origin, radius, normal=None):
    vec = (center[0] - origin[0], center[1] - origin[1], center[2] - origin[2])
    t = _dot(vec, axis)
    radial, mag = _norm((vec[0] - t * axis[0], vec[1] - t * axis[1], vec[2] - t * axis[2]))
    if mag < 1e-9:
        radial, mag = _norm(vec)
    offset = max(radius * 0.35, 0.25)
    toward = (center[0] - offset * radial[0], center[1] - offset * radial[1], center[2] - offset * radial[2])
    away = (center[0] + offset * radial[0], center[1] + offset * radial[1], center[2] + offset * radial[2])
    for solid in solids:
        side = classify_by_containment(_point_inside(solid, toward), _point_inside(solid, away))
        if side:
            return side
    if normal:
        return classify_cylinder_side(normal, radial)
    return None


def _solid_span_on_axis(bbox, axis):
    corners = []
    xmin, ymin, zmin = bbox.xmin, bbox.ymin, bbox.zmin
    for dx in (0, bbox.xlen):
        for dy in (0, bbox.ylen):
            for dz in (0, bbox.zlen):
                corners.append(_project((xmin + dx, ymin + dy, zmin + dz), axis))
    return min(corners), max(corners)


def _entry_is_curved(faces, axis, cyl_min, cyl_max, radius):
    for face in faces:
        kind = face.geomType()
        if kind in ("PLANE", "CYLINDER"):
            continue
        if kind not in ("SPHERE", "TORUS", "CONE", "BSPLINE", "BEZIER"):
            continue
        c = face.Center()
        t = _project((c.x, c.y, c.z), axis)
        if min(abs(t - cyl_min), abs(t - cyl_max)) < max(1.5, radius * 0.4):
            return True
    return False


def _has_helix(face):
    try:
        for edge in face.Edges():
            if "HELIX" in str(edge.geomType()).upper():
                return True
    except Exception:
        return False
    return False


def _coaxial(a, b, tol_axis=0.05, tol_dir=0.02):
    if abs(a["diameter_mm"] - b["diameter_mm"]) > 0.08:
        return False
    if abs(_dot(a["axis_t"], b["axis_t"])) < 1 - tol_dir:
        return False
    w = (b["origin"][0] - a["origin"][0], b["origin"][1] - a["origin"][1], b["origin"][2] - a["origin"][2])
    cross = (
        w[1] * a["axis_t"][2] - w[2] * a["axis_t"][1],
        w[2] * a["axis_t"][0] - w[0] * a["axis_t"][2],
        w[0] * a["axis_t"][1] - w[1] * a["axis_t"][0],
    )
    dist = math.sqrt(cross[0] ** 2 + cross[1] ** 2 + cross[2] ** 2)
    return dist <= tol_axis


def _merge_inner(items):
    used = [False] * len(items)
    groups = []
    for i, item in enumerate(items):
        if used[i]:
            continue
        group = [item]
        used[i] = True
        for j in range(i + 1, len(items)):
            if used[j]:
                continue
            if _coaxial(item, items[j]):
                group.append(items[j])
                used[j] = True
        groups.append(group)
    return groups


def _hole_feature(group, bbox, all_faces, index):
    item = group[0]
    cyl_min = min(g["cyl_min"] for g in group)
    cyl_max = max(g["cyl_max"] for g in group)
    depth = cyl_max - cyl_min
    diameter = item["diameter_mm"]
    axis = item["axis_t"]
    solid_min, solid_max = item["solid_min"], item["solid_max"]
    hole_type = classify_through_blind(cyl_min, cyl_max, solid_min, solid_max)
    recessed = is_recessed(cyl_min, cyl_max, solid_min, solid_max)
    curved = any(
        _entry_is_curved(all_faces, g["axis_t"], g["cyl_min"], g["cyl_max"], diameter / 2)
        for g in group
    )
    position = classify_position(
        axis, (bbox.xlen, bbox.ylen, bbox.zlen),
        entry_curved=curved, entry_recessed=recessed,
    )
    thread = {"spec": "unknown"} if any(g.get("helix") for g in group) else None
    cut = through_cut_depth(diameter, depth, hole_type)
    evidence = [
        "inner-cylinder x%d" % len(group),
        "D=%.3f" % diameter,
        "H=%.3f" % depth,
        hole_type,
        position,
    ]
    if thread:
        evidence.append("helix-thread")
    return {
        "feature_id": "hole-%d" % index,
        "type": "hole",
        "subtype": "recognized_hole",
        "diameter_mm": round(diameter, 4),
        "depth_mm": round(depth, 4),
        "cut_depth_mm": cut,
        "h_over_d": round(depth / diameter, 4) if diameter else None,
        "hole_type": hole_type,
        "position_type": position,
        "surface": SURFACE_FROM_POSITION[position],
        "bottom_shape": "cone",
        "thread": thread,
        "dimensions": {"diameter_mm": round(diameter, 4), "depth_mm": round(depth, 4)},
        "location": item["location"],
        "axis": {"x": round(axis[0], 6), "y": round(axis[1], 6), "z": round(axis[2], 6)},
        "occurrences": len(group),
        "confidence": 0.86,
        "selected": True,
        "evidence": evidence,
        "warnings": [],
    }


def _candidate(index, radius, depth, location, axis=None, hole_type=None, position_type=None):
    d = round(radius * 2, 4)
    h = round(depth, 4)
    pos = position_type
    surface = SURFACE_FROM_POSITION.get(pos) if pos else None
    cut = through_cut_depth(d, h, hole_type) if hole_type else None
    return {
        "feature_id": "cylinder-%d" % index,
        "type": "hole",
        "subtype": "cylindrical_candidate",
        "diameter_mm": d,
        "depth_mm": h,
        "cut_depth_mm": cut,
        "h_over_d": round(h / d, 4) if d else None,
        "hole_type": hole_type,
        "position_type": pos,
        "surface": surface,
        "bottom_shape": "cone",
        "dimensions": {"diameter_mm": d, "depth_mm": h},
        "location": location,
        "axis": axis,
        "occurrences": 1,
        "confidence": 0.45,
        "selected": False,
        "evidence": ["B-Rep cylinder #%d" % index],
        "warnings": ["内外圆分不清，请工程师勾选"],
    }


def parse_step(path: str) -> dict:
    try:
        import cadquery as cq
    except ImportError as exc:
        raise RuntimeError("CadQuery/OCP加载失败：%s" % exc) from exc

    imported = cq.importers.importStep(path)
    values = imported.vals()
    if not values:
        raise ValueError("STEP中没有可解析的形状")
    compound = cq.Compound.makeCompound(values) if len(values) > 1 else values[0]
    solids = compound.Solids()
    if not solids:
        raise ValueError("STEP中没有封闭实体，无法计算可靠体积")

    bbox = compound.BoundingBox()
    center = compound.Center()
    faces = compound.Faces()
    edges = compound.Edges()
    volume = sum(s.Volume() for s in solids)
    area = sum(f.Area() for f in faces)
    geom_counts = {}
    for face in faces:
        kind = face.geomType()
        geom_counts[kind] = geom_counts.get(kind, 0) + 1

    inner, outer, unknown, other = [], [], [], []
    for index, face in enumerate(faces):
        kind = face.geomType()
        location = face.Center()
        fb = face.BoundingBox()
        if kind == "CYLINDER":
            radius = _face_radius(face)
            if not radius or radius <= 0:
                continue
            try:
                axis, origin, cyl_min, cyl_max = _cylinder_axis_and_span(face)
            except Exception:
                axis, origin, cyl_min, cyl_max = None, None, None, None
            if axis is None or cyl_min is None:
                unknown.append(_candidate(index, radius, max(fb.xlen, fb.ylen, fb.zlen), _point(location)))
                continue
            center = (location.x, location.y, location.z)
            side = classify_side(solids, center, axis, origin, radius, _face_normal(face))
            solid_min, solid_max = _solid_span_on_axis(bbox, axis)
            if side is None and likely_plate_hole(
                radius * 2, cyl_min, cyl_max, solid_min, solid_max,
                (bbox.xlen, bbox.ylen, bbox.zlen),
            ):
                side = "inner"
            rec = {
                "index": index,
                "diameter_mm": radius * 2,
                "axis_t": axis,
                "origin": origin,
                "cyl_min": cyl_min,
                "cyl_max": cyl_max,
                "solid_min": solid_min,
                "solid_max": solid_max,
                "location": _point(location),
                "helix": _has_helix(face),
            }
            if side == "inner":
                inner.append(rec)
            elif side == "outer":
                outer.append(rec)
            else:
                axis_d = {"x": round(axis[0], 6), "y": round(axis[1], 6), "z": round(axis[2], 6)}
                ht = classify_through_blind(cyl_min, cyl_max, solid_min, solid_max)
                pos = classify_position(axis, (bbox.xlen, bbox.ylen, bbox.zlen))
                unknown.append(_candidate(
                    index, radius, cyl_max - cyl_min, _point(location), axis_d,
                    hole_type=ht, position_type=pos,
                ))
        elif kind == "CONE":
            other.append({
                "feature_id": "cone-%d" % index, "type": "chamfer", "subtype": "conical_face",
                "dimensions": _bbox(fb), "location": _point(location), "axis": None, "occurrences": 1,
                "confidence": 0.55, "selected": False, "evidence": ["B-Rep cone #%d" % index],
                "warnings": ["可能是沉头孔、倒角或锥面，需人工分类"],
            })
        elif kind == "TORUS":
            other.append({
                "feature_id": "torus-%d" % index, "type": "fillet", "subtype": "toroidal_face",
                "dimensions": _bbox(fb), "location": _point(location), "axis": None, "occurrences": 1,
                "confidence": 0.55, "selected": False, "evidence": ["B-Rep torus #%d" % index],
                "warnings": ["可能是圆角或环形槽，需人工分类"],
            })

    features = []
    for i, group in enumerate(_merge_inner(inner)):
        features.append(_hole_feature(group, bbox, faces, i))
    for rec in outer:
        depth = rec["cyl_max"] - rec["cyl_min"]
        features.append({
            "feature_id": "od-%d" % rec["index"],
            "type": "outer_cylinder",
            "subtype": "boss_or_od",
            "diameter_mm": round(rec["diameter_mm"], 4),
            "depth_mm": round(depth, 4),
            "dimensions": {"diameter_mm": round(rec["diameter_mm"], 4), "depth_mm": round(depth, 4)},
            "location": rec["location"],
            "axis": {"x": round(rec["axis_t"][0], 6), "y": round(rec["axis_t"][1], 6), "z": round(rec["axis_t"][2], 6)},
            "occurrences": 1,
            "confidence": 0.8,
            "selected": False,
            "evidence": ["outer cylinder #%d" % rec["index"]],
            "warnings": ["外圆，不进孔工序链"],
        })
    features.extend(unknown)
    features.extend(other)

    planar = geom_counts.get("PLANE", 0)
    if planar >= 6:
        features.append({
            "feature_id": "prismatic-region-0", "type": "pocket_or_step", "subtype": "planar_region",
            "dimensions": _bbox(bbox), "location": _point(center), "axis": None, "occurrences": 1,
            "confidence": 0.35, "selected": False,
            "evidence": ["planar faces: %d" % planar],
            "warnings": ["MVP仅标识可能的槽/型腔/台阶区域，尚未自动生成非孔工艺"],
        })

    warnings = []
    if len(solids) > 1:
        warnings.append("检测到%d个实体，结果按组合体统计" % len(solids))
    recognized = any(f.get("subtype") == "recognized_hole" for f in features)
    if not recognized and any(f.get("type") == "hole" for f in features):
        warnings.append("圆柱面未能确认内孔，已标候选待工程师勾选")
    return {
        "parser": "cadquery-occ", "parser_version": getattr(cq, "__version__", "unknown"),
        "feature_schema": "hole-v2",
        "geometry": {
            "unit": "mm", "solid_count": len(solids), "volume_cm3": round(volume / 1000, 6),
            "surface_area_cm2": round(area / 100, 6), "bounding_box_mm": _bbox(bbox),
            "center_mm": _point(center), "face_count": len(faces), "edge_count": len(edges),
            "surface_types": geom_counts,
        },
        "features": features, "warnings": warnings,
    }

