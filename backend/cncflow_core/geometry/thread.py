"""螺纹 B-Rep 识别：有螺旋/牙型才出 D/P/L，没有当孔走。"""
import math

from cncflow_core.ingestion.step_parser import _face_normal, _norm, _point, _xyz

# 粗牙常用螺距，P 认不出时按 D 回填
_METRIC_PITCH = (
    (3, 0.5), (4, 0.7), (5, 0.8), (6, 1.0), (8, 1.25),
    (10, 1.5), (12, 1.75), (16, 2.0), (20, 2.5), (24, 3.0),
)


def infer_pitch(diameter):
    if not diameter:
        return None
    d = float(diameter)
    best = min(_METRIC_PITCH, key=lambda item: abs(item[0] - d))
    if abs(best[0] - d) <= 0.15:
        return best[1]
    return None


def major_from_minor(minor_d):
    """底孔≈公称-螺距。M8×1.25 底孔约 6.8。"""
    if not minor_d:
        return None, None
    d0 = float(minor_d)
    for major, pitch in _METRIC_PITCH:
        if abs((major - pitch) - d0) <= 0.25:
            return float(major), float(pitch)
    return None, None


def _axis_from_bbox(fb):
    axis = (
        1.0 if fb.xlen >= fb.ylen and fb.xlen >= fb.zlen else 0.0,
        1.0 if fb.ylen > fb.xlen and fb.ylen >= fb.zlen else 0.0,
        1.0 if fb.zlen > fb.xlen and fb.zlen > fb.ylen else 0.0,
    )
    if axis == (0.0, 0.0, 0.0):
        return (0.0, 0.0, 1.0)
    return axis


def _is_form_face(face):
    kind = str(face.geomType() or "").upper()
    return kind not in {"PLANE", "CYLINDER", "CONE", "SPHERE", "TORUS", "CIRCLE"}


def _near_cylinder(form_fb, cyl_c, cyl_r, axis, length):
    fc = (
        (form_fb.xmin + form_fb.xmax) / 2,
        (form_fb.ymin + form_fb.ymax) / 2,
        (form_fb.zmin + form_fb.zmax) / 2,
    )
    ax, mag = _norm(axis)
    if mag < 1e-9:
        return False
    rel = (fc[0] - cyl_c[0], fc[1] - cyl_c[1], fc[2] - cyl_c[2])
    along = rel[0] * ax[0] + rel[1] * ax[1] + rel[2] * ax[2]
    if abs(along) > length * 0.7 + 2:
        return False
    radial = math.sqrt(max(0.0, rel[0] ** 2 + rel[1] ** 2 + rel[2] ** 2 - along * along))
    return abs(radial - cyl_r) <= max(2.5, cyl_r * 0.6)


def _edge_kind(edge):
    try:
        return str(edge.geomType() or "").upper()
    except Exception:
        return ""


def _cyl_radius(face):
    try:
        return float(face._geomAdaptor().Cylinder().Radius())
    except Exception:
        try:
            return float(face.radius())
        except Exception:
            return None


def _helix_pitch(edge, axis):
    """沿轴走一圈的升程。认不出返回 None。"""
    try:
        pts = []
        n = 12
        for i in range(n + 1):
            p = edge.positionAt(i / n)
            pts.append(_xyz(p))
        if len(pts) < 4:
            return None
        ax, mag = _norm(axis)
        if mag < 1e-9:
            return None
        zs = [p[0] * ax[0] + p[1] * ax[1] + p[2] * ax[2] for p in pts]
        span = max(zs) - min(zs)
        # 转角：在垂直轴平面上累加
        turns = 0.0
        prev = None
        for p, z in zip(pts, zs):
            radial = (
                p[0] - ax[0] * z,
                p[1] - ax[1] * z,
                p[2] - ax[2] * z,
            )
            r, rm = _norm(radial)
            if rm < 1e-6:
                continue
            if prev is not None:
                cross = (
                    prev[1] * r[2] - prev[2] * r[1],
                    prev[2] * r[0] - prev[0] * r[2],
                    prev[0] * r[1] - prev[1] * r[0],
                )
                sin_a = cross[0] * ax[0] + cross[1] * ax[1] + cross[2] * ax[2]
                cos_a = prev[0] * r[0] + prev[1] * r[1] + prev[2] * r[2]
                turns += math.atan2(sin_a, cos_a)
            prev = r
        revs = abs(turns) / (2 * math.pi)
        if revs < 0.4:
            return None
        pitch = span / revs
        if 0.2 <= pitch <= 6.5:
            return round(pitch, 3)
    except Exception:
        return None
    return None


def _looks_helical(face, axis):
    kinds = []
    pitch = None
    for edge in face.Edges():
        kind = _edge_kind(edge)
        kinds.append(kind)
        if kind in {"HELIX", "BSPLINE", "BSPLINECURVE", "OFFSET"}:
            found = _helix_pitch(edge, axis)
            if found:
                pitch = found if pitch is None else min(pitch, found)
    if pitch:
        return True, pitch
    # 仅圆柱直边/圆，不当螺纹
    return False, None


def detect_threads(path: str) -> list:
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

    cylinders = []
    forms = []
    for face in compound.Faces():
        fb = face.BoundingBox()
        kind = str(face.geomType() or "").upper()
        if kind == "CYLINDER":
            radius = _cyl_radius(face)
            if not radius or radius < 1.0 or radius > 20:
                continue
            axis = _axis_from_bbox(fb)
            cylinders.append({
                "face": face, "fb": fb, "r": radius,
                "c": _xyz(face.Center()), "axis": axis,
                "length": max(fb.xlen, fb.ylen, fb.zlen),
            })
        elif _is_form_face(face):
            forms.append({"face": face, "fb": fb})

    found = []
    for cyl in cylinders:
        if cyl["length"] < 1.5:
            continue
        helical, pitch = _looks_helical(cyl["face"], cyl["axis"])
        n_form = sum(
            1 for form in forms
            if _near_cylinder(form["fb"], cyl["c"], cyl["r"], cyl["axis"], cyl["length"])
        )
        # 牙型 STEP 常是底孔圆柱 + 若干 B 样条牙面，不是 HELIX 边。
        # 无螺旋时必须能从底孔推公称，避免开口槽圆角圆柱被当成 M6。
        minor = 2 * cyl["r"]
        major, metric_p = major_from_minor(minor)
        if not helical:
            if n_form < 2 or major is None:
                continue
        else:
            if major is None:
                major = minor
                metric_p = pitch or infer_pitch(minor)
            if metric_p is None:
                continue
        if pitch is None:
            pitch = metric_p
        if metric_p is None:
            continue
        loc = _point(cyl["c"])
        axis = cyl["axis"]
        length = round(cyl["length"], 4)
        found.append({
            "feature_id": "thread-%d" % len(found),
            "type": "thread",
            "subtype": "recognized_thread",
            "selected": True,
            "diameter_mm": round(major, 4),
            "pitch": pitch,
            "thread_length": length,
            "dimensions": {
                "diameter_mm": round(major, 4),
                "pitch": pitch,
                "thread_length": length,
            },
            "location": loc,
            "axis": {"x": round(axis[0], 6), "y": round(axis[1], 6), "z": round(axis[2], 6)},
            "occurrences": 1,
            "confidence": 0.78 if n_form else 0.7,
            "evidence": [
                "bspline-form x%d" % n_form if n_form else "helix",
                "D=%.3f" % major,
                "P=%.3f" % pitch,
                "L=%.3f" % cyl["length"],
            ],
            "warnings": [],
        })
    return found
