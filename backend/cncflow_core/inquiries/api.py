"""询价 / 零件 HTTP。"""
import json
import math
import os
import re
from io import BytesIO

from flask import Blueprint, current_app, jsonify, request, Response, send_file

from ..common.db import get_conn
from ..geometry.service import apply_quote_default_selection
from ..ingestion.jobs import get_job
from ..ingestion import r2
from ..common.materials import resolve_material
from ..quoting.engine import quote
from ..quoting import process_edits
from . import store
from .quote_pdf import build_quote_pdf

bp = Blueprint("inquiries", __name__)
_UNSET = object()


def _conn():
    return get_conn(current_app.config.get("DB_PATH"))


def _bbox_lwh(part, geometry):
    box = (geometry or {}).get("bounding_box_mm") or {}
    L = part.get("length") or part.get("diameter") or box.get("x")
    W = part.get("width") or part.get("diameter") or box.get("y")
    H = part.get("height") or box.get("z")
    if (not part.get("length") or not part.get("width")) and box.get("x") and box.get("y"):
        nums = sorted([float(box.get("x") or 0), float(box.get("y") or 0), float(box.get("z") or 0)], reverse=True)
        L, W, H = nums[0], nums[1], nums[2]
    return L, W, H


_POS_TO_SURFACE = {
    "垂直": "top", "倾斜": "inclined", "曲面": "curved", "侧向": "side", "深腔": "top",
    "top": "top", "inclined": "inclined", "curved": "curved", "side": "side",
    "vertical": "top",
}
_HOLE_TYPE = {"through": "through", "blind": "blind", "通孔": "through", "盲孔": "blind"}
_BOTTOM = {"cone": "cone", "flat": "flat", "锥底": "cone", "conical": "cone", "平底": "flat"}


def _hole_for_pipeline(feat, fid):
    dim = feat.get("dimensions") or {}
    d = dim.get("diameter_mm") or feat.get("diameter_mm")
    depth = dim.get("depth_mm") or feat.get("depth_mm")
    if not d or not depth:
        return None
    hole_type = _HOLE_TYPE.get(str(feat.get("hole_type") or dim.get("hole_type") or "through"), "through")
    pos = feat.get("position_type") or feat.get("surface") or "垂直"
    surface = _POS_TO_SURFACE.get(str(pos), feat.get("surface") or "top")
    if surface not in {"top", "side", "inclined", "curved"}:
        surface = "top"
    bottom = _BOTTOM.get(str(feat.get("bottom_shape") or "cone"), "cone")
    thread = feat.get("thread")
    if thread is not None and not isinstance(thread, dict):
        thread = None
    cut = feat.get("cut_depth_mm")
    if cut is None:
        cut = float(depth) + (0.3 * float(d) if hole_type == "through" else 0.0)
    return {
        "type": "hole",
        "diameter_mm": d,
        "depth_mm": depth,
        "cut_depth_mm": cut,
        "hole_type": hole_type,
        "surface": surface,
        "position_type": pos if pos in _POS_TO_SURFACE else None,
        "bottom_shape": bottom,
        "thread": thread,
        "feature_id": fid,
    }


def _pocket_for_pipeline(feat, fid):
    dim = feat.get("dimensions") or {}
    length = feat.get("length") if feat.get("length") is not None else dim.get("length")
    width = feat.get("width") if feat.get("width") is not None else dim.get("width")
    depth = feat.get("depth") if feat.get("depth") is not None else dim.get("depth")
    if depth is None:
        depth = feat.get("depth_mm") or dim.get("depth_mm")
    if not length or not width or not depth:
        return None
    corner = feat.get("corner_radius")
    if corner is None:
        corner = dim.get("corner_radius") or 1
    return {
        "type": "pocket",
        "feature_id": fid,
        "pocket_type": feat.get("pocket_type") or dim.get("pocket_type") or "封闭",
        "length": float(length),
        "width": float(width),
        "depth": float(depth),
        "corner_radius": float(corner),
    }



def _face_for_pipeline(feat, fid):
    dim = feat.get("dimensions") or {}
    length = feat.get("length") if feat.get("length") is not None else dim.get("length")
    width = feat.get("width") if feat.get("width") is not None else dim.get("width")
    if not length or not width:
        return None
    pos = feat.get("face_position") or dim.get("face_position") or "水平"
    return {
        "type": "face",
        "feature_id": fid,
        "length": float(length),
        "width": float(width),
        "face_position": pos,
    }



def _thread_for_pipeline(feat, fid):
    dim = feat.get("dimensions") or {}
    d = feat.get("diameter_mm") if feat.get("diameter_mm") is not None else dim.get("diameter_mm")
    if d is None:
        d = feat.get("nominal_d") or dim.get("nominal_d")
    length = feat.get("thread_length")
    if length is None:
        length = dim.get("thread_length") or feat.get("length") or feat.get("depth_mm")
    if not d or not length:
        return None
    pitch = feat.get("pitch")
    if pitch is None:
        pitch = dim.get("pitch")
    return {
        "type": "thread",
        "feature_id": fid,
        "diameter_mm": float(d),
        "nominal_d": float(d),
        "pitch": float(pitch) if pitch not in (None, "") else None,
        "thread_length": float(length),
    }



def _step_for_pipeline(feat, fid):
    dim = feat.get("dimensions") or {}
    length = feat.get("length") if feat.get("length") is not None else dim.get("length")
    width = feat.get("width") if feat.get("width") is not None else dim.get("width")
    height = feat.get("height") if feat.get("height") is not None else dim.get("height")
    if height is None:
        height = feat.get("depth") or dim.get("depth") or feat.get("depth_mm")
    if not length or not height:
        return None
    mapped = {
        "type": "step",
        "feature_id": fid,
        "profile_type": feat.get("profile_type") or dim.get("profile_type") or "台阶",
        "length": float(length),
        "height": float(height),
    }
    if width is not None:
        mapped["width"] = float(width)
    return mapped



def _surface_for_pipeline(feat, fid):
    dim = feat.get("dimensions") or {}
    surface_type = feat.get("surface_type") or dim.get("surface_type")
    radius = feat.get("curvature_radius")
    if radius is None:
        radius = dim.get("curvature_radius")
    if radius is None:
        radius = feat.get("radius")
    if not surface_type:
        return None
    try:
        radius = float(radius) if radius is not None else None
    except (TypeError, ValueError):
        return None
    return {
        "type": "surface",
        "feature_id": fid,
        "surface_type": surface_type,
        "curvature_radius": radius,
        "position": feat.get("position") or dim.get("position"),
        "manual_hours": float(feat.get("manual_hours") or 0),
    }


_FEATURE_DIMENSION_FIELDS = {
    "hole": {"diameter_mm", "depth_mm"},
    "thread": {"diameter_mm", "thread_length"},
    "slot": {"length", "width", "depth"},
    "pocket": {"length", "width", "depth"},
    "face": {"length", "width"},
    "step": {"length", "width", "height"},
}


def _normalize_feature_overrides(raw, features, *, strict=True):
    if raw in (None, []):
        return []
    if not isinstance(raw, list):
        if not strict:
            return []
        raise ValueError("feature_overrides 须为数组")
    feature_by_id = {
        str(feature.get("feature_id") or feature.get("id")): feature
        for feature in features or []
        if isinstance(feature, dict) and (feature.get("feature_id") or feature.get("id"))
    }
    normalized = []
    seen = set()
    for item in raw:
        if not isinstance(item, dict):
            if not strict:
                continue
            raise ValueError("feature_overrides 每项须为对象")
        fid = str(item.get("feature_id") or "").strip()
        if not fid or fid not in feature_by_id:
            if not strict:
                continue
            raise ValueError(f"特征不存在：{fid or '—'}")
        if fid in seen:
            if not strict:
                continue
            raise ValueError(f"特征覆盖重复：{fid}")
        seen.add(fid)
        feature_type = str(feature_by_id[fid].get("type") or "").lower()
        allowed = _FEATURE_DIMENSION_FIELDS.get(feature_type, set())
        dimensions = item.get("dimensions")
        if not isinstance(dimensions, dict) or not dimensions:
            if not strict:
                continue
            raise ValueError(f"{fid}.dimensions 须为非空对象")
        unknown = set(dimensions) - allowed
        if unknown:
            if not strict:
                dimensions = {
                    field: value
                    for field, value in dimensions.items()
                    if field in allowed
                }
                if not dimensions:
                    continue
            else:
                raise ValueError(f"{fid} 不支持修改尺寸：{', '.join(sorted(unknown))}")
        values = {}
        for field, value in dimensions.items():
            try:
                number = float(value)
            except (TypeError, ValueError):
                if not strict:
                    continue
                raise ValueError(f"{fid}.{field} 须为数字") from None
            if not math.isfinite(number) or number <= 0:
                if not strict:
                    continue
                raise ValueError(f"{fid}.{field} 须大于 0")
            values[field] = number
        if values:
            normalized.append({"feature_id": fid, "dimensions": values})
    return normalized


def _merge_feature_overrides(features, saved, incoming=_UNSET):
    merged = {
        item["feature_id"]: dict(item["dimensions"])
        for item in _normalize_feature_overrides(saved, features, strict=False)
    }
    if incoming is not _UNSET:
        for item in _normalize_feature_overrides(incoming, features):
            merged.setdefault(item["feature_id"], {}).update(item["dimensions"])
    feature_order = {
        str(feature.get("feature_id") or feature.get("id")): index
        for index, feature in enumerate(features or [])
        if isinstance(feature, dict)
    }
    return [
        {"feature_id": fid, "dimensions": dimensions}
        for fid, dimensions in sorted(
            merged.items(),
            key=lambda pair: feature_order.get(pair[0], len(feature_order)),
        )
    ]


def _apply_feature_overrides(features, overrides):
    override_by_id = {
        item["feature_id"]: item["dimensions"]
        for item in overrides or []
    }
    result = []
    for source in features or []:
        feature = dict(source)
        fid = str(feature.get("feature_id") or feature.get("id") or "")
        values = override_by_id.get(fid)
        if not values:
            result.append(feature)
            continue
        dimensions = dict(feature.get("dimensions") or {})
        dimensions.update(values)
        feature["dimensions"] = dimensions
        feature.update(values)
        feature_type = str(feature.get("type") or "").lower()
        pose = dict(feature.get("pose") or {})
        if pose and feature_type in {"hole", "thread"}:
            if "diameter_mm" in values:
                pose["diameter_mm"] = values["diameter_mm"]
            length_key = "depth_mm" if feature_type == "hole" else "thread_length"
            if length_key in values:
                pose["length_mm"] = values[length_key]
            feature["pose"] = pose
        if feature_type == "hole" and (
            "diameter_mm" in values or "depth_mm" in values
        ):
            diameter = float(feature.get("diameter_mm") or 0)
            depth = float(feature.get("depth_mm") or 0)
            hole_type = _HOLE_TYPE.get(
                str(feature.get("hole_type") or dimensions.get("hole_type") or "through"),
                "through",
            )
            feature["cut_depth_mm"] = depth + (0.3 * diameter if hole_type == "through" else 0.0)
        result.append(feature)
    return result


def _review_and_quote_features(parsed_feats, selected_ids, L, W):
    review = []
    quoted = []
    selected = set(str(x) for x in selected_ids) if selected_ids is not None else None
    feats = [dict(feat) for feat in (parsed_feats or []) if isinstance(feat, dict)]
    if selected is None:
        feats = apply_quote_default_selection(feats, L, W)
    for i, feat in enumerate(feats):
        fid = str(feat.get("feature_id") or feat.get("id") or f"f{i}")
        on = True if selected is None else fid in selected
        if selected is None and feat.get("selected") is False:
            on = False
        item = {**feat, "feature_id": fid, "selected": on}
        review.append(item)
        if not on:
            continue
        if feat.get("type") == "hole":
            mapped = _hole_for_pipeline(feat, fid)
            if mapped:
                quoted.append(mapped)
        elif feat.get("type") in {"pocket", "slot"}:
            mapped = _pocket_for_pipeline(feat, fid)
            if mapped:
                quoted.append(mapped)
        elif feat.get("type") == "face":
            mapped = _face_for_pipeline(feat, fid)
            if mapped:
                quoted.append(mapped)
        elif feat.get("type") == "thread":
            mapped = _thread_for_pipeline(feat, fid)
            if mapped:
                quoted.append(mapped)
        elif feat.get("type") == "step":
            mapped = _step_for_pipeline(feat, fid)
            if mapped:
                quoted.append(mapped)
        elif feat.get("type") == "surface":
            mapped = _surface_for_pipeline(feat, fid)
            if mapped:
                quoted.append(mapped)
    features = quoted
    return review, features


def _parse_result(conn, part):
    job = None
    if part.get("parse_job_id"):
        try:
            job = get_job(conn, part["parse_job_id"])
        except KeyError:
            job = None
    geom = (job or {}).get("result") or {}
    return geom if isinstance(geom, dict) else {}


def _parse_geom(conn, part):
    geom = _parse_result(conn, part)
    return geom.get("geometry") or {}, geom.get("features") or []


def _load_mesh_bytes(result):
    mesh = (result or {}).get("mesh") or {}
    path = mesh.get("path")
    if path and os.path.isfile(path):
        with open(path, "rb") as fh:
            return fh.read()
    key = mesh.get("key")
    if key and r2.configured():
        try:
            return r2.get_object(key)
        except FileNotFoundError:
            return None
    return None


def _step_path_for_job(conn, job_id):
    if not job_id:
        return None
    row = conn.execute(
        "SELECT storage_path FROM uploaded_files WHERE job_id=? AND detected_type='step' LIMIT 1",
        (job_id,),
    ).fetchone()
    if not row:
        return None
    from ..ingestion.storage import materialize
    try:
        return materialize(row["storage_path"], suffix=".step")
    except FileNotFoundError:
        return None


def _ensure_part_mesh(conn, part):
    """Serve stored GLB, or build it now from the job STEP (covers stale parses)."""
    result = _parse_result(conn, part)
    data = _load_mesh_bytes(result)
    if data:
        return data
    path = _step_path_for_job(conn, part.get("parse_job_id"))
    if not path:
        return None
    from ..geometry.mesh import step_to_glb
    from ..ingestion.worker import _store_mesh
    try:
        data = step_to_glb(path)
    except Exception:
        return None
    mesh = _store_mesh(part["parse_job_id"], data)
    if not mesh:
        return None
    result = dict(result)
    result["mesh"] = mesh
    conn.execute(
        "UPDATE parse_jobs SET result_json=?, updated_at=datetime('now') WHERE job_id=?",
        (json.dumps(result, ensure_ascii=False), part["parse_job_id"]),
    )
    conn.commit()
    return data


def _ensure_pose(feat):
    if feat.get("pose"):
        return feat
    loc, ax = feat.get("location"), feat.get("axis")
    d, h = feat.get("diameter_mm"), feat.get("depth_mm")
    if isinstance(loc, dict) and isinstance(ax, dict) and d and h:
        feat["pose"] = {
            "origin": {"x": loc.get("x"), "y": loc.get("y"), "z": loc.get("z")},
            "axis": ax,
            "length_mm": h,
            "diameter_mm": d,
        }
    return feat


def _flatten_hole_fields(feat):
    if not isinstance(feat, dict):
        return feat
    dim = feat.get("dimensions") or {}
    out = dict(feat)
    for key in (
        "diameter_mm", "depth_mm", "hole_type", "position_type", "cut_depth_mm",
        "pocket_type", "length", "width", "depth", "corner_radius", "profile_type", "height",
    ):
        if out.get(key) is None and dim.get(key) is not None:
            out[key] = dim[key]
    return _ensure_pose(out)


def _attach_parsed_features(conn, part):
    """零件详情在未报价时也能看到 parse-job 孔参数。"""
    result = _parse_result(conn, part)
    feats = [_flatten_hole_fields(f) for f in (result.get("features") or [])]
    part["parsed_features"] = feats
    mesh = result.get("mesh") if isinstance(result.get("mesh"), dict) else None
    stored = bool(mesh and (mesh.get("key") or mesh.get("path")))
    can_build = bool(part.get("parse_job_id") and _step_path_for_job(conn, part.get("parse_job_id")))
    available = stored or can_build
    part["mesh"] = {
        "available": available,
        "url": f"/api/v1/parts/{part['id']}/mesh" if available else None,
        "bytes": (mesh or {}).get("bytes"),
        "format": "glb" if available else None,
    }
    quote = part.get("quote")
    if not isinstance(quote, dict):
        quote = {}
        part["quote"] = quote
    if not (quote.get("review_features") or quote.get("features")):
        review, _ = _review_and_quote_features(feats, None, part.get("length") or 0, part.get("width") or 0)
        quote = dict(quote)
        quote["review_features"] = [_flatten_hole_fields(f) for f in review]
        part["quote"] = quote
    return part



def _overlay_manual_hours(features, override, part_hours=None):
    """PATCH 手补工时接到已映射的曲面特征。"""
    by_id = {}
    for item in override or []:
        if not isinstance(item, dict):
            continue
        fid = str(item.get("feature_id") or item.get("id") or "")
        if fid and item.get("manual_hours") is not None:
            by_id[fid] = item.get("manual_hours")
    for feat in features:
        if feat.get("type") != "surface":
            continue
        fid = str(feat.get("feature_id") or feat.get("id") or "")
        if fid in by_id:
            feat["manual_hours"] = float(by_id[fid] or 0)
        elif part_hours is not None:
            feat["manual_hours"] = float(part_hours or 0)
    return features


def _quote_part(
    conn, part, selected_ids=None, features_override=None, extra=None,
    process_overrides=_UNSET,
):
    geometry, parsed_feats = _parse_geom(conn, part)
    L, W, H = _bbox_lwh(part, geometry)
    box = (geometry or {}).get("bounding_box_mm") or {}
    if (not part.get("length") or not part.get("width")) and box.get("x") and box.get("y") and L and W:
        store.update_part(conn, part["id"], {"length": L, "width": W, "height": H})
        part = store.get_part(conn, part["id"])
    if not L or not W:
        return None
    extra = extra or {}
    override = features_override
    if override is None:
        override = extra.get("features") or extra.get("review_features")
    feature_source = parsed_feats
    if not feature_source and isinstance(override, list):
        feature_source = override
    saved_quote = part.get("quote") if isinstance(part.get("quote"), dict) else {}
    incoming_feature_overrides = (
        extra["feature_overrides"] if "feature_overrides" in extra else _UNSET
    )
    feature_overrides = _merge_feature_overrides(
        feature_source,
        saved_quote.get("feature_overrides") or [],
        incoming_feature_overrides,
    )
    feature_source = _apply_feature_overrides(feature_source, feature_overrides)
    review, features = _review_and_quote_features(feature_source, selected_ids, L, W)
    features = _overlay_manual_hours(features, override, extra.get("manual_hours"))
    try:
        rules_version = current_app.config.get("RULES_VERSION") or ""
    except RuntimeError:
        rules_version = ""
    raw_mat = part.get("material_code") or "铝合金"
    try:
        material = resolve_material(conn, raw_mat).family or raw_mat
    except ValueError:
        material = raw_mat
    if process_overrides is _UNSET:
        process_overrides = saved_quote.get("process_overrides") or []
    result = quote({
        "material": material,
        "stock_type": part.get("blank_type") or "板料",
        "length": L,
        "diameter": part.get("diameter") or W,
        "width": W,
        "height": H or 0,
        "batch_size": part.get("batch_size") or 1,
        "is_repeat_order": part.get("is_repeat_order"),
        "slider": part.get("slider") or "标准",
        "tolerance_it": part.get("tolerance_it"),
        "roughness_ra": part.get("roughness_ra"),
        "v_part_cad": geometry.get("volume_cm3"),
        "features": features,
        "process_overrides": process_overrides,
    }, conn, rules_version=rules_version)
    result["review_features"] = review
    result["feature_overrides"] = feature_overrides
    return store.set_quote(conn, part["id"], result)


def _explicit_quote_selection(payload):
    """POST quote 仅把非空 ID 列表视为用户显式选择；features 本身只是刷新快照。"""
    raw = payload.get("selected_feature_ids")
    if not isinstance(raw, list):
        return None
    selected = [str(fid) for fid in raw if fid not in (None, "")]
    return selected or None


def _saved_quote_selection(part):
    quote_data = part.get("quote") if isinstance(part.get("quote"), dict) else {}
    review = quote_data.get("review_features")
    if not isinstance(review, list):
        return None
    return [
        str(feature.get("feature_id") or feature.get("id"))
        for feature in review
        if isinstance(feature, dict)
        and feature.get("selected") is not False
        and (feature.get("feature_id") or feature.get("id")) not in (None, "")
    ]


def _maybe_quote(conn, part):
    """Parse-complete parts with bbox become quoted so 1/2/3/5 have numbers."""
    if not part or part.get("status") in {"confirmed", "abandoned", "parse_failed"}:
        return part
    q = part.get("quote") if isinstance(part.get("quote"), dict) else {}
    already = isinstance(q.get("quote"), dict) and (q.get("quote") or {}).get("amount")
    seq = q.get("process_sequence") or []
    has_sku = any(s.get("sku") for s in seq)
    if already and has_sku and part.get("status") in {"quoted", "revising"}:
        return part
    try:
        quoted = _quote_part(conn, part)
    except ValueError:
        return part
    return quoted if quoted is not None else part


@bp.get("/api/v1/inquiries")
def list_inquiries():
    conn = _conn()
    try:
        return jsonify({"items": store.list_inquiries(
            conn, ui_status=request.args.get("ui_status"),
            customer=request.args.get("customer"), project=request.args.get("project"),
        )})
    finally:
        conn.close()


@bp.post("/api/v1/inquiries")
def create_inquiry():
    payload = request.get_json(silent=True) or {}
    conn = _conn()
    try:
        return jsonify(store.create_inquiry(conn, payload)), 201
    finally:
        conn.close()


@bp.get("/api/v1/inquiries/<iid>")
def get_inquiry(iid):
    conn = _conn()
    try:
        return jsonify(store.get_inquiry(conn, iid))
    except KeyError:
        return jsonify({"error": "询价单不存在"}), 404
    finally:
        conn.close()


@bp.get("/api/v1/inquiries/<iid>/quote.pdf")
def get_inquiry_quote_pdf(iid):
    conn = _conn()
    try:
        inquiry = store.get_inquiry(conn, iid)
        filename_base = re.sub(r"[/\\\r\n]+", "_", inquiry.get("title") or iid)
        return send_file(
            BytesIO(build_quote_pdf(inquiry)),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"{filename_base}-报价单.pdf",
        )
    except KeyError:
        return jsonify({"error": "询价单不存在"}), 404
    finally:
        conn.close()


@bp.post("/api/v1/inquiries/<iid>/parts")
def add_part(iid):
    payload = request.get_json(silent=True) or {}
    conn = _conn()
    try:
        return jsonify(store.add_part(conn, iid, payload)), 201
    except KeyError:
        return jsonify({"error": "询价单不存在"}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    finally:
        conn.close()


@bp.post("/api/v1/inquiries/<iid>/quote")
def quote_inquiry(iid):
    conn = _conn()
    try:
        inquiry = store.get_inquiry(conn, iid)
        req = request.get_json(silent=True) or {}
        selected_ids = _explicit_quote_selection(req)
        out = []
        for part in inquiry["parts"]:
            if part["status"] == "confirmed":
                out.append(part)
                continue
            quoted = _quote_part(
                conn, part, selected_ids=selected_ids,
                features_override=req.get("features") or req.get("review_features"), extra=req,
            )
            out.append(quoted if quoted is not None else part)
        return jsonify(store.get_inquiry(conn, iid))
    except KeyError:
        return jsonify({"error": "询价单不存在"}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    finally:
        conn.close()


@bp.get("/api/v1/parts/<pid>")
def get_part(pid):
    conn = _conn()
    try:
        part = _maybe_quote(conn, store.get_part(conn, pid))
        return jsonify(_attach_parsed_features(conn, part))
    except KeyError:
        return jsonify({"error": "零件不存在"}), 404
    finally:
        conn.close()


@bp.get("/api/v1/parts/<pid>/mesh")
def get_part_mesh(pid):
    conn = _conn()
    try:
        part = store.get_part(conn, pid)
        data = _ensure_part_mesh(conn, part)
        if not data:
            return jsonify({"error": "暂无模型"}), 404
        return Response(data, mimetype="model/gltf-binary")
    except KeyError:
        return jsonify({"error": "零件不存在"}), 404
    finally:
        conn.close()


@bp.patch("/api/v1/parts/<pid>")
def patch_part(pid):
    payload = request.get_json(silent=True) or {}
    conn = _conn()
    try:
        part = store.update_part(conn, pid, payload)
        selected_ids = payload.get("selected_feature_ids", _UNSET)
        if selected_ids is _UNSET:
            selected_ids = _saved_quote_selection(part)
        elif not isinstance(selected_ids, list):
            selected_ids = None
        if part["status"] not in {"confirmed", "abandoned"}:
            quoted = _quote_part(
                conn, part, selected_ids=selected_ids,
                features_override=payload.get("features") or payload.get("review_features"),
                extra=payload,
            )
            if quoted is not None:
                part = quoted
        return jsonify(_attach_parsed_features(conn, part))
    except PermissionError:
        return jsonify({"error": "已确认报价不可再改"}), 409
    except KeyError:
        return jsonify({"error": "零件不存在"}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    finally:
        conn.close()


@bp.post("/api/v1/parts/<pid>/quote")
def quote_part(pid):
    conn = _conn()
    try:
        part = store.get_part(conn, pid)
        if part["status"] in {"confirmed", "abandoned"}:
            return jsonify({"error": f"状态 {part['status']} 不能再报价"}), 409
        req = request.get_json(silent=True) or {}
        quoted = _quote_part(
            conn, part, selected_ids=_explicit_quote_selection(req),
            features_override=req.get("features") or req.get("review_features"), extra=req,
        )
        if quoted is None:
            return jsonify({"error": "缺少长宽尺寸，无法报价"}), 400
        return jsonify(_attach_parsed_features(conn, quoted))
    except KeyError:
        return jsonify({"error": "零件不存在"}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    finally:
        conn.close()


def _merge_process_overrides(current_sequence, saved, incoming):
    if not isinstance(incoming, list) or not incoming:
        raise ValueError("steps 须为非空数组")
    valid_ids = {str(step.get("step_id") or "") for step in current_sequence}
    merged = {
        item["step_id"]: dict(item)
        for item in process_edits.normalize_overrides(saved)
    }
    for patch in incoming:
        if not isinstance(patch, dict):
            raise ValueError("steps 每项须为对象")
        step_id = str(patch.get("step_id") or "").strip()
        if not step_id or step_id not in valid_ids:
            raise ValueError(f"工步不存在：{step_id or '—'}")
        item = merged.setdefault(step_id, {"step_id": step_id})
        for field in ("order", *process_edits.EDITABLE_PARAMS):
            if field not in patch:
                continue
            if patch[field] is None:
                item.pop(field, None)
            else:
                item[field] = patch[field]
        # minutes 是直接工时覆盖；改公式参数时切回公式重算，避免旧 minutes 吞掉本次修改。
        if "minutes" not in patch and any(
            field in patch for field in ("n", "f", "cut", "passes")
        ):
            item.pop("minutes", None)
        if len(item) == 1:
            merged.pop(step_id, None)

    normalized = process_edits.normalize_overrides(list(merged.values()))
    if any("order" in patch for patch in incoming):
        by_id = {item["step_id"]: item for item in normalized}
        orders = [
            by_id.get(step["step_id"], {}).get("order", step.get("order"))
            for step in current_sequence
        ]
        if sorted(orders) != list(range(1, len(current_sequence) + 1)):
            raise ValueError("改序时须提交完整且不重复的 1..N order")
    return normalized


@bp.patch("/api/v1/parts/<pid>/process-sequence")
def patch_process_sequence(pid):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "请求体须为 JSON 对象"}), 400
    conn = _conn()
    try:
        part = store.get_part(conn, pid)
        if part["status"] in {"confirmed", "abandoned"}:
            return jsonify({"error": f"状态 {part['status']} 不能修改工步"}), 409
        quote_data = part.get("quote") if isinstance(part.get("quote"), dict) else {}
        sequence_now = quote_data.get("process_sequence") or []
        if not sequence_now or not all(step.get("step_id") for step in sequence_now):
            part = _quote_part(
                conn, part, selected_ids=_saved_quote_selection(part),
                features_override=quote_data.get("review_features"),
            )
            if part is None:
                return jsonify({"error": "缺少长宽尺寸，无法报价"}), 400
            quote_data = part.get("quote") or {}
            sequence_now = quote_data.get("process_sequence") or []
        if payload.get("reset") is True:
            overrides = []
        else:
            overrides = _merge_process_overrides(
                sequence_now, quote_data.get("process_overrides") or [], payload.get("steps"),
            )
        quoted = _quote_part(
            conn, part,
            selected_ids=_saved_quote_selection(part),
            features_override=quote_data.get("review_features"),
            process_overrides=overrides,
        )
        if quoted is None:
            return jsonify({"error": "缺少长宽尺寸，无法报价"}), 400
        return jsonify(_attach_parsed_features(conn, quoted))
    except KeyError:
        return jsonify({"error": "零件不存在"}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    finally:
        conn.close()


@bp.post("/api/v1/parts/<pid>/confirm")
def confirm_part(pid):
    conn = _conn()
    try:
        part = store.get_part(conn, pid)
        if part["status"] not in {"quoted", "revising"}:
            return jsonify({"error": f"状态 {part['status']} 不能确认"}), 409
        return jsonify(store.set_status(conn, pid, "confirmed"))
    except KeyError:
        return jsonify({"error": "零件不存在"}), 404
    finally:
        conn.close()


@bp.post("/api/v1/parts/<pid>/abandon")
def abandon_part(pid):
    conn = _conn()
    try:
        return jsonify(store.set_status(conn, pid, "abandoned"))
    except KeyError:
        return jsonify({"error": "零件不存在"}), 404
    finally:
        conn.close()
