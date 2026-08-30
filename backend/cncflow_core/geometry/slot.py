"""槽腔 B-Rep 识别：内凹底面 + 侧壁，产出 pocket 最小字段。"""
import math

from cncflow_core.ingestion.step_parser import (
    _dot, _face_normal, _norm, _point, _point_inside, _xyz,
)


def _edge_kind(edge):
    try:
        return str(edge.geomType() or "").upper()
    except Exception:
        return ""


def _edge_key(edge):
    try:
        bb = edge.BoundingBox()
        return (
            round(bb.xmin, 3), round(bb.ymin, 3), round(bb.zmin, 3),
            round(bb.xmax, 3), round(bb.ymax, 3), round(bb.zmax, 3),
        )
    except Exception:
        return None


def _is_hole_bottom(face):
    kinds = [_edge_kind(e) for e in face.Edges()]
    if not kinds:
        return False
    circ = sum(1 for k in kinds if k in {"CIRCLE", "ARC"})
    line = sum(1 for k in kinds if k == "LINE")
    return circ > 0 and line == 0


def _face_on_bbox(fb, bbox, tol=0.35):
    if fb.xlen <= tol and (abs(fb.xmin - bbox.xmin) <= tol or abs(fb.xmax - bbox.xmax) <= tol):
        return True
    if fb.ylen <= tol and (abs(fb.ymin - bbox.ymin) <= tol or abs(fb.ymax - bbox.ymax) <= tol):
        return True
    if fb.zlen <= tol and (abs(fb.zmin - bbox.zmin) <= tol or abs(fb.zmax - bbox.zmax) <= tol):
        return True
    return False


def _cyl_radius(face):
    try:
        return float(face._geomAdaptor().Cylinder().Radius())
    except Exception:
        try:
            return float(face.radius())
        except Exception:
            return None


def _torus_minor(face):
    try:
        return float(face._geomAdaptor().Torus().MinorRadius())
    except Exception:
        return None


def _edge_radius(edge):
    try:
        return float(edge.radius())
    except Exception:
        try:
            return float(edge.Radius())
        except Exception:
            return None


def _corner_radius(bottom, walls, all_faces, pocket_box):
    radii = []
    for item in walls + [bottom]:
        face = item["face"] if isinstance(item, dict) else item
        for edge in face.Edges():
            if _edge_kind(edge) not in {"CIRCLE", "ARC"}:
                continue
            r = _edge_radius(edge)
            if r and 0.05 < r < 40:
                radii.append(r)
    if radii:
        return round(min(radii), 3)
    px0, px1 = pocket_box[0], pocket_box[1]
    py0, py1 = pocket_box[2], pocket_box[3]
    pz0, pz1 = pocket_box[4], pocket_box[5]
    pad = 3.0
    nearby = []
    for face in all_faces:
        kind = face.geomType()
        try:
            c = _xyz(face.Center())
        except Exception:
            continue
        if not (px0 - pad <= c[0] <= px1 + pad and py0 - pad <= c[1] <= py1 + pad and pz0 - pad <= c[2] <= pz1 + pad):
            continue
        if kind == "CYLINDER":
            r = _cyl_radius(face)
            if not r or r < 0.05 or r > 40:
                continue
            try:
                area = float(face.Area())
                fb = face.BoundingBox()
                depth = max(fb.xlen, fb.ylen, fb.zlen)
                full = 2 * math.pi * r * max(depth, 1e-6)
                if full > 1e-9 and area / full >= 0.8:
                    continue
            except Exception:
                pass
            nearby.append(r)
        elif kind == "TORUS":
            r = _torus_minor(face)
            if r and 0.05 < r < 40:
                nearby.append(r)
    if nearby:
        return round(min(nearby), 3)
    return None


def _connected_components(items):
    n = len(items)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    edge_owners = {}
    for i, item in enumerate(items):
        for key in item.get("edge_keys") or []:
            if key is None:
                continue
            if key in edge_owners:
                union(i, edge_owners[key])
            else:
                edge_owners[key] = i
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(items[i])
    return list(groups.values())


def _pick_bottom(faces):
    best = None
    best_score = None
    for face in faces:
        n_perp = sum(1 for other in faces if other is not face and abs(_dot(face["n"], other["n"])) < 0.25)
        n_opp = sum(1 for other in faces if other is not face and _dot(face["n"], other["n"]) < -0.85)
        score = (n_perp, -n_opp, face["area"])
        if best is None or score > best_score:
            best, best_score = face, score
    return best


def _pair_walls(walls):
    used = set()
    pairs = []
    singles = []
    for i, a in enumerate(walls):
        if i in used:
            continue
        matched = False
        for j in range(i + 1, len(walls)):
            if j in used:
                continue
            b = walls[j]
            if _dot(a["n"], b["n"]) > -0.85:
                continue
            delta = (b["c"][0] - a["c"][0], b["c"][1] - a["c"][1], b["c"][2] - a["c"][2])
            dist = abs(_dot(delta, a["n"]))
            if dist < 0.4:
                continue
            pairs.append((a, b, dist))
            used.add(i)
            used.add(j)
            matched = True
            break
        if not matched:
            singles.append(a)
    return pairs, singles


def _extent_along(faces, direction):
    axis, mag = _norm(direction)
    if mag < 1e-9:
        return 0.0
    projs = []
    for face in faces:
        for vertex in face["face"].Vertices():
            pt = _xyz(vertex.Center())
            projs.append(_dot(pt, axis))
    if len(projs) < 2:
        return 0.0
    return max(projs) - min(projs)


def _depth_from_walls(bottom, walls):
    projs = []
    for wall in walls:
        for vertex in wall["face"].Vertices():
            pt = _xyz(vertex.Center())
            delta = (pt[0] - bottom["c"][0], pt[1] - bottom["c"][1], pt[2] - bottom["c"][2])
            projs.append(_dot(delta, bottom["n"]))
    if not projs:
        return 0.0
    return max(projs) - min(projs)


def _cavity_ok(solids, bottom, walls, depth):
    n, mag = _norm(bottom["n"])
    if mag < 1e-9:
        return False
    plus = (bottom["c"][0] + 0.6 * n[0], bottom["c"][1] + 0.6 * n[1], bottom["c"][2] + 0.6 * n[2])
    minus = (bottom["c"][0] - 0.6 * n[0], bottom["c"][1] - 0.6 * n[1], bottom["c"][2] - 0.6 * n[2])
    plus_in = any(_point_inside(solid, plus) for solid in solids)
    minus_in = any(_point_inside(solid, minus) for solid in solids)
    if plus_in == minus_in:
        return False
    if plus_in and not minus_in:
        n = (-n[0], -n[1], -n[2])
        bottom["n"] = n
    mid = depth * 0.45 if depth > 1 else 0.6
    probe = (bottom["c"][0] + mid * n[0], bottom["c"][1] + mid * n[1], bottom["c"][2] + mid * n[2])
    if any(_point_inside(solid, probe) for solid in solids):
        return False
    return True


def _opens_to_side(bottom, walls, bbox, pairs):
    if len(walls) < 4:
        return True
    fb = bottom["fb"]
    axes = (
        (fb.xmin, bbox.xmin, fb.xmax, bbox.xmax),
        (fb.ymin, bbox.ymin, fb.ymax, bbox.ymax),
        (fb.zmin, bbox.zmin, fb.zmax, bbox.zmax),
    )
    for fmin, smin, fmax, smax in axes:
        span = max(smax - smin, 1e-6)
        if abs(fmax - fmin) < 0.8 * span and (abs(fmin - smin) < 1.2 or abs(fmax - smax) < 1.2):
            return True
    return False


def _pocket_type(length, width, n_walls, t_slot, opens):
    if t_slot:
        return "T型"
    if opens:
        return "开放"
    if length / max(width, 1e-6) >= 3 and width <= 12.0001:
        return "键槽"
    if n_walls >= 4:
        return "封闭"
    return "开放"


def _is_t_slot(pairs):
    if len(pairs) < 2:
        return False
    buckets = {}
    for a, _b, dist in pairs:
        axis = max(range(3), key=lambda i: abs(a["n"][i]))
        buckets.setdefault(axis, []).append(dist)
    for dists in buckets.values():
        if len(dists) >= 2 and max(dists) - min(dists) > max(1.0, 0.15 * max(dists)):
            return True
    return False


def _measure(bottom, walls):
    pairs, _singles = _pair_walls(walls)
    t_slot = _is_t_slot(pairs)
    dists = [p[2] for p in pairs]
    if len(dists) >= 2:
        width, length = min(dists), max(dists)
    elif len(dists) == 1:
        width = dists[0]
        a, b, _ = pairs[0]
        along = (
            a["n"][1] * bottom["n"][2] - a["n"][2] * bottom["n"][1],
            a["n"][2] * bottom["n"][0] - a["n"][0] * bottom["n"][2],
            a["n"][0] * bottom["n"][1] - a["n"][1] * bottom["n"][0],
        )
        length = _extent_along(walls, along)
        if length < width:
            length, width = width, length
    else:
        dims = sorted((bottom["fb"].xlen, bottom["fb"].ylen, bottom["fb"].zlen), reverse=True)
        length, width = dims[0], dims[1]
    depth = _depth_from_walls(bottom, walls)
    if depth < 0.5:
        fb = bottom["fb"]
        thick = min(fb.xlen, fb.ylen, fb.zlen)
        dims = sorted((fb.xlen, fb.ylen, fb.zlen), reverse=True)
        if thick <= 2.5:
            length, width = dims[0], dims[1]
    return length, width, depth, t_slot, pairs


def detect_slots(path: str) -> list:
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
        solids = compound.Solids()
        if not solids:
            return []
    except Exception:
        return []

    bbox = compound.BoundingBox()
    faces = compound.Faces()
    inner = []
    for index, face in enumerate(faces):
        if face.geomType() != "PLANE":
            continue
        if _is_hole_bottom(face):
            continue
        fb = face.BoundingBox()
        if _face_on_bbox(fb, bbox):
            continue
        normal = _face_normal(face)
        if not normal:
            continue
        n, mag = _norm(normal)
        if mag < 1e-9:
            continue
        keys = [_edge_key(edge) for edge in face.Edges()]
        inner.append({
            "index": index,
            "face": face,
            "fb": fb,
            "c": _xyz(face.Center()),
            "n": n,
            "area": float(face.Area()),
            "edge_keys": [k for k in keys if k],
        })

    if len(inner) < 3:
        return []

    found = []
    for cluster in _connected_components(inner):
        if len(cluster) < 3:
            continue
        bottom = _pick_bottom(cluster)
        if not bottom:
            continue
        walls = [f for f in cluster if f is not bottom and abs(_dot(f["n"], bottom["n"])) < 0.25]
        if len(walls) < 2:
            continue
        length, width, depth, t_slot, pairs = _measure(bottom, walls)
        if min(length, width, depth) < 0.8:
            continue
        if not _cavity_ok(solids, bottom, walls, depth):
            continue
        if depth < 0.8:
            continue
        opens = _opens_to_side(bottom, walls, bbox, pairs)
        found_r = _corner_radius(
            bottom, walls, faces,
            (bottom["fb"].xmin, bottom["fb"].xmax, bottom["fb"].ymin, bottom["fb"].ymax,
             bottom["fb"].zmin, bottom["fb"].zmax),
        )
        # 开口封闭端圆角吃掉一段直壁，L 要补回 R
        if opens and found_r:
            length = length + found_r
        radius = found_r if found_r is not None else 1.0
        ptype = _pocket_type(length, width, len(walls), t_slot, opens)
        loc = _point(bottom["c"])
        found.append({
            "feature_id": "slot-%d" % len(found),
            "type": "pocket",
            "subtype": "recognized_slot",
            "selected": True,
            "pocket_type": ptype,
            "length": round(length, 4),
            "width": round(width, 4),
            "depth": round(depth, 4),
            "corner_radius": radius,
            "dimensions": {
                "length": round(length, 4),
                "width": round(width, 4),
                "depth": round(depth, 4),
                "corner_radius": radius,
            },
            "location": loc,
            "axis": {"x": round(bottom["n"][0], 6), "y": round(bottom["n"][1], 6), "z": round(bottom["n"][2], 6)},
            "occurrences": 1,
            "confidence": 0.82,
            "evidence": [
                "inner-walls x%d" % len(walls),
                "L=%.3f" % length,
                "W=%.3f" % width,
                "H=%.3f" % depth,
                ptype,
            ],
            "warnings": [],
        })
    return found
