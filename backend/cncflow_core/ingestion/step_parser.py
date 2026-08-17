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


def _xyz(value):
    """Accept CadQuery Vector, OCP gp_Pnt, tuple/list, or {x,y,z}."""
    if value is None:
        raise TypeError("xyz is None")
    if isinstance(value, dict):
        return (float(value["x"]), float(value["y"]), float(value["z"]))
    if isinstance(value, (tuple, list)) and len(value) >= 3:
        return (float(value[0]), float(value[1]), float(value[2]))
    if hasattr(value, "x"):
        return (float(value.x), float(value.y), float(value.z))
    if hasattr(value, "X"):
        x = value.X
        if callable(x):
            return (float(value.X()), float(value.Y()), float(value.Z()))
        return (float(value.X), float(value.Y), float(value.Z))
    raise TypeError("cannot read xyz from %r" % type(value))


def _point(value):
    x, y, z = _xyz(value)
    return {"x": round(x, 4), "y": round(y, 4), "z": round(z, 4)}


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
    """轴对齐最短边 → 垂直，不被沉头/圆角打成曲面。"""
    ax = (abs(axis[0]), abs(axis[1]), abs(axis[2]))
    dom = max(range(3), key=lambda i: ax[i])
    if ax[dom] >= ALIGN_COS:
        shortest = min(range(3), key=lambda i: extents[i])
        if dom == shortest:
            return "垂直"
        if entry_recessed:
            return "深腔"
        return "侧向"
    if entry_curved:
        return "曲面"
    return "倾斜"


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


def classify_through_by_ends(lo_inside, hi_inside):
    """两端都在实体外 → 通孔（含打穿到型腔）；一端在实体内 → 盲孔。"""
    if lo_inside is None or hi_inside is None:
        return None
    if (not lo_inside) and (not hi_inside):
        return "through"
    if lo_inside != hi_inside:
        return "blind"
    return None


def radial_bbox_extents(axis, extents):
    """Two bbox lengths perpendicular to the cylinder axis."""
    if not extents or not axis:
        return tuple(extents or ())
    ax = (abs(axis[0]), abs(axis[1]), abs(axis[2]))
    dom = max(range(3), key=lambda i: ax[i])
    radial = tuple(extents[i] for i in range(3) if i != dom)
    return radial or tuple(extents)


def likely_outer_od(diameter, extents, axis):
    """直径接近垂直于轴的外轮廓 → 外圆，不能当孔。"""
    if not extents or not axis or diameter <= 0:
        return False
    radial = radial_bbox_extents(axis, extents)
    if not radial:
        return False
    return diameter >= min(radial) * 0.85


def override_false_outer(side, diameter, extents, axis):
    """Ø3.3 不可能是 50mm 件外圆：containment 标 outer 也改 inner。"""
    if likely_outer_od(diameter, extents, axis):
        return "outer"
    if side == "outer":
        return "inner"
    return side


def is_quote_hole(diameter, depth, hole_type, extents, axis=None):
    """Ø50 外圆、Ø33.4 浅盲腔不当孔；小通孔要进链。"""
    if not extents or diameter <= 0 or depth <= 0:
        return False
    shortest = min(extents)
    longest = max(extents)
    if diameter >= shortest * 0.9:
        return False
    if axis is not None:
        if likely_outer_od(diameter, extents, axis):
            return False
        radial = radial_bbox_extents(axis, extents)
        if radial and diameter >= min(radial) * 0.5:
            return False
    if hole_type == "blind" and diameter > max(depth * 1.2, 20):
        return False
    if diameter > longest * 0.45 and hole_type != "through":
        return False
    return True


def through_wall_depth(cyl_span, solid_span, cavity_span=None):
    """通孔打穿到同轴型腔时，H = 件高 − 型腔深。"""
    if cavity_span and solid_span > cavity_span:
        wall = solid_span - cavity_span
        if wall > 0 and (cyl_span <= 0 or abs(wall - cyl_span) <= max(3.0, cyl_span * 0.2)):
            return wall
    return cyl_span


def recover_through_depth(cyl_depth, wall_depth, min_ratio=0.85):
    """通孔圆柱略短于壁厚时用壁厚。不向更短收缩，也不跳到整段外圆高。"""
    if not wall_depth or wall_depth <= cyl_depth:
        return cyl_depth
    if cyl_depth >= wall_depth * min_ratio:
        return wall_depth
    return cyl_depth


def through_into_cavity(cyl_span, solid_span, cavity_span):
    """圆柱跨度接近剩余壁厚 → 打穿到型腔的通孔。"""
    if not cavity_span or not solid_span or solid_span <= cavity_span:
        return False
    wall = solid_span - cavity_span
    if wall <= 0:
        return False
    return abs(wall - cyl_span) <= max(3.0, cyl_span * 0.2)


def _axis_point(origin, axis, t):
    t0 = _project(origin, axis)
    dt = t - t0
    return (origin[0] + axis[0] * dt, origin[1] + axis[1] * dt, origin[2] + axis[2] * dt)


def _same_axis(a, b, tol_dir=0.02, tol_axis=1.5):
    if abs(_dot(a["axis_t"], b["axis_t"])) < 1 - tol_dir:
        return False
    w = (b["origin"][0] - a["origin"][0], b["origin"][1] - a["origin"][1], b["origin"][2] - a["origin"][2])
    cross = (
        w[1] * a["axis_t"][2] - w[2] * a["axis_t"][1],
        w[2] * a["axis_t"][0] - w[0] * a["axis_t"][2],
        w[0] * a["axis_t"][1] - w[1] * a["axis_t"][0],
    )
    dist = (cross[0] ** 2 + cross[1] ** 2 + cross[2] ** 2) ** 0.5
    return dist <= tol_axis


def coaxial_cavity_span(hole, cylinders, solid_span, extents=None):
    """同轴更大圆柱里选型腔（短于件高），不要把 Ø50 外圆当型腔。"""
    best = None
    hole_d = hole.get("diameter_mm") or 0
    for cav in cylinders or []:
        d = cav.get("diameter_mm") or 0
        if d <= hole_d + 0.5:
            continue
        if not cav.get("axis_t") or not hole.get("axis_t"):
            continue
        if not _same_axis(hole, cav):
            continue
        span = cav["cyl_max"] - cav["cyl_min"]
        if span <= 0:
            continue
        if solid_span and span >= solid_span * 0.88:
            continue
        axis = cav.get("axis_t")
        if extents and axis and likely_outer_od(d, extents, axis):
            continue
        if best is None or span > best:
            best = span
    return best


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
        pt = _xyz(vertex.Center())
        projections.append(_project(pt, axis))
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
    c = _xyz(face.Center())
    vec = (c[0] - origin[0], c[1] - origin[1], c[2] - origin[2])
    t = _dot(vec, axis)
    closest = (origin[0] + t * axis[0], origin[1] + t * axis[1], origin[2] + t * axis[2])
    return (c[0] - closest[0], c[1] - closest[1], c[2] - closest[2])


def _face_normal(face):
    try:
        n = face.normalAt()
        vec = _xyz(n)
    except Exception:
        try:
            n = face.normalAt(None)
            vec = _xyz(n)
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


def is_curved_entry_kind(kind):
    """沉头锥/圆角不当曲面入口；球面或自由曲面才是。"""
    return kind in ("SPHERE", "BSPLINE", "BEZIER")


def _entry_is_curved(faces, axis, cyl_min, cyl_max, radius):
    for face in faces:
        kind = face.geomType()
        if kind in ("PLANE", "CYLINDER"):
            continue
        if not is_curved_entry_kind(kind):
            continue
        c = _xyz(face.Center())
        t = _project(c, axis)
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


def _hole_feature(group, bbox, all_faces, index, cavities=None):
    item = group[0]
    cyl_min = min(g["cyl_min"] for g in group)
    cyl_max = max(g["cyl_max"] for g in group)
    depth = cyl_max - cyl_min
    diameter = item["diameter_mm"]
    axis = item["axis_t"]
    solid_min, solid_max = item["solid_min"], item["solid_max"]
    solid_span = solid_max - solid_min
    extents = (bbox.xlen, bbox.ylen, bbox.zlen)
    hole_type = item.get("hole_type") or classify_through_blind(cyl_min, cyl_max, solid_min, solid_max)
    cavity_span = coaxial_cavity_span(item, cavities, solid_span, extents)
    if hole_type != "through" and through_into_cavity(depth, solid_span, cavity_span):
        hole_type = "through"
    if hole_type == "through":
        depth = through_wall_depth(depth, solid_span, cavity_span)
        wall_span = max((g.get("wall_span") or 0) for g in group) or None
        if wall_span:
            depth = recover_through_depth(depth, wall_span)
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
    feat = {
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
    origin = item.get("origin")
    if origin and axis:
        start = _axis_point(origin, axis, cyl_min)
        feat["pose"] = {
            "origin": {"x": round(start[0], 4), "y": round(start[1], 4), "z": round(start[2], 4)},
            "axis": {"x": round(axis[0], 6), "y": round(axis[1], 6), "z": round(axis[2], 6)},
            "length_mm": round(cyl_max - cyl_min, 4),
            "diameter_mm": round(diameter, 4),
        }
    return feat


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

    inner, outer, unknown, other, all_cyls = [], [], [], [], []
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
            face_center = _xyz(location)
            side = classify_side(solids, face_center, axis, origin, radius, _face_normal(face))
            solid_min, solid_max = _solid_span_on_axis(bbox, axis)
            extents = (bbox.xlen, bbox.ylen, bbox.zlen)
            side = override_false_outer(side, radius * 2, extents, axis)
            if side is None and likely_plate_hole(
                radius * 2, cyl_min, cyl_max, solid_min, solid_max, extents,
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
            ht = classify_through_blind(cyl_min, cyl_max, solid_min, solid_max)
            lo = _axis_point(origin, axis, cyl_min - 0.4)
            hi = _axis_point(origin, axis, cyl_max + 0.4)
            end_ht = None
            for solid in solids:
                end_ht = classify_through_by_ends(_point_inside(solid, lo), _point_inside(solid, hi))
                if end_ht:
                    break
            if end_ht:
                ht = end_ht
            rec["hole_type"] = ht
            all_cyls.append(rec)
            if side == "inner" and not is_quote_hole(radius * 2, cyl_max - cyl_min, ht, extents, axis):
                side = None
            if side == "inner":
                inner.append(rec)
            elif side == "outer":
                outer.append(rec)
            else:
                axis_d = {"x": round(axis[0], 6), "y": round(axis[1], 6), "z": round(axis[2], 6)}
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
        features.append(_hole_feature(group, bbox, faces, i, cavities=all_cyls))
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
    mesh_glb = None
    try:
        from cncflow_core.geometry.mesh import step_to_glb
        mesh_glb = step_to_glb(path)
    except Exception:
        warnings.append("网格导出失败，零件详情将显示空态")

    out = {
        "parser": "cadquery-occ", "parser_version": getattr(cq, "__version__", "unknown"),
        "feature_schema": "hole-v3",
        "geometry": {
            "unit": "mm", "solid_count": len(solids), "volume_cm3": round(volume / 1000, 6),
            "surface_area_cm2": round(area / 100, 6), "bounding_box_mm": _bbox(bbox),
            "center_mm": _point(center), "face_count": len(faces), "edge_count": len(edges),
            "surface_types": geom_counts,
        },
        "features": features, "warnings": warnings,
    }
    if mesh_glb:
        out["_mesh_glb"] = mesh_glb
    return out

