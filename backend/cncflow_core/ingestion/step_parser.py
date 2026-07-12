"""STEP B-Rep整体计量与制造特征候选提取（仅在解析Worker中导入CadQuery）。"""
import math


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


def _cylinder_axis_and_depth(face, bbox):
    try:
        cylinder = face._geomAdaptor().Cylinder()
        direction = cylinder.Axis().Direction()
        axis = {"x": float(direction.X()), "y": float(direction.Y()), "z": float(direction.Z())}
        projections = []
        for vertex in face.Vertices():
            p = vertex.Center()
            projections.append(p.x * axis["x"] + p.y * axis["y"] + p.z * axis["z"])
        depth = max(projections) - min(projections) if len(projections) >= 2 else max(bbox.xlen, bbox.ylen, bbox.zlen)
        return {k: round(v, 6) for k, v in axis.items()}, float(depth)
    except Exception:
        return None, max(bbox.xlen, bbox.ylen, bbox.zlen)


def parse_step(path: str) -> dict:
    try:
        import cadquery as cq
    except ImportError as exc:
        raise RuntimeError(f"CadQuery/OCP加载失败：{exc}") from exc

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

    features = []
    cylinders = []
    for index, face in enumerate(faces):
        kind = face.geomType()
        radius = _face_radius(face)
        fb = face.BoundingBox()
        location = face.Center()
        if kind == "CYLINDER" and radius and radius > 0:
            axis, depth = _cylinder_axis_and_depth(face, fb)
            # 圆柱面可能是外圆；先全部作为孔/圆柱面候选，交由用户确认。
            candidate = {
                "feature_id": f"cylinder-{index}", "type": "hole", "subtype": "cylindrical_candidate",
                "dimensions": {"diameter_mm": round(radius * 2, 4), "depth_mm": round(depth, 4)},
                "location": _point(location), "axis": axis, "occurrences": 1,
                "confidence": 0.62, "selected": True,
                "evidence": [f"B-Rep圆柱面#{index}", f"半径={radius:.4f}mm"],
                "warnings": ["圆柱面也可能是外圆；需确认是否为孔", "通孔/盲孔需结合图纸确认"],
            }
            cylinders.append(candidate)
            features.append(candidate)
        elif kind == "CONE":
            features.append({
                "feature_id": f"cone-{index}", "type": "chamfer", "subtype": "conical_face",
                "dimensions": _bbox(fb), "location": _point(location), "axis": None, "occurrences": 1,
                "confidence": 0.55, "selected": False, "evidence": [f"B-Rep圆锥面#{index}"],
                "warnings": ["可能是沉头孔、倒角或锥面，需人工分类"],
            })
        elif kind == "TORUS":
            features.append({
                "feature_id": f"torus-{index}", "type": "fillet", "subtype": "toroidal_face",
                "dimensions": _bbox(fb), "location": _point(location), "axis": None, "occurrences": 1,
                "confidence": 0.55, "selected": False, "evidence": [f"B-Rep环面#{index}"],
                "warnings": ["可能是圆角或环形槽，需人工分类"],
            })

    # 对相同直径的圆柱面聚合为孔组提示，但保留原候选供编辑。
    groups = {}
    for feature in cylinders:
        key = round(feature["dimensions"]["diameter_mm"], 2)
        groups.setdefault(key, []).append(feature["feature_id"])
    for diameter, ids in groups.items():
        if len(ids) > 1:
            for feature in cylinders:
                if feature["feature_id"] in ids:
                    feature["occurrences"] = len(ids)
                    feature["evidence"].append(f"检测到同直径圆柱面组：{len(ids)}个")

    planar = geom_counts.get("PLANE", 0)
    if planar >= 6:
        features.append({
            "feature_id": "prismatic-region-0", "type": "pocket_or_step", "subtype": "planar_region",
            "dimensions": _bbox(bbox), "location": _point(center), "axis": None, "occurrences": 1,
            "confidence": 0.35, "selected": False,
            "evidence": [f"检测到{planar}个平面"],
            "warnings": ["MVP仅标识可能的槽/型腔/台阶区域，尚未自动生成非孔工艺"],
        })

    warnings = []
    if len(solids) > 1:
        warnings.append(f"检测到{len(solids)}个实体，结果按组合体统计")
    return {
        "parser": "cadquery-occ", "parser_version": getattr(cq, "__version__", "unknown"),
        "geometry": {
            "unit": "mm", "solid_count": len(solids), "volume_cm3": round(volume / 1000, 6),
            "surface_area_cm2": round(area / 100, 6), "bounding_box_mm": _bbox(bbox),
            "center_mm": _point(center), "face_count": len(faces), "edge_count": len(edges),
            "surface_types": geom_counts,
        },
        "features": features, "warnings": warnings,
    }
