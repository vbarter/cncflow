"""询价 / 零件 HTTP。"""
import json
import os
from flask import Blueprint, current_app, jsonify, request, Response

from ..common.db import get_conn
from ..ingestion.jobs import get_job
from ..ingestion import r2
from ..common.materials import resolve_material
from ..quoting.engine import quote
from . import store

bp = Blueprint("inquiries", __name__)


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
    height = feat.get("height") if feat.get("height") is not None else dim.get("height")
    if height is None:
        height = feat.get("depth") or dim.get("depth") or feat.get("depth_mm")
    if not length or not height:
        return None
    return {
        "type": "step",
        "feature_id": fid,
        "profile_type": feat.get("profile_type") or dim.get("profile_type") or "台阶",
        "length": float(length),
        "height": float(height),
    }



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


def _review_and_quote_features(parsed_feats, selected_ids, L, W):
    review = []
    quoted = []
    selected = set(str(x) for x in selected_ids) if selected_ids is not None else None
    for i, feat in enumerate(parsed_feats or []):
        if not isinstance(feat, dict):
            continue
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


def _quote_part(conn, part, selected_ids=None, features_override=None):
    geometry, parsed_feats = _parse_geom(conn, part)
    L, W, H = _bbox_lwh(part, geometry)
    box = (geometry or {}).get("bounding_box_mm") or {}
    if (not part.get("length") or not part.get("width")) and box.get("x") and box.get("y") and L and W:
        store.update_part(conn, part["id"], {"length": L, "width": W, "height": H})
        part = store.get_part(conn, part["id"])
    if not L or not W:
        return None
    review, features = _review_and_quote_features(parsed_feats, selected_ids, L, W)
    if features_override:
        features = features_override
    try:
        rules_version = current_app.config.get("RULES_VERSION") or ""
    except RuntimeError:
        rules_version = ""
    raw_mat = part.get("material_code") or "铝合金"
    try:
        material = resolve_material(conn, raw_mat).family or raw_mat
    except ValueError:
        material = raw_mat
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
    }, conn, rules_version=rules_version)
    result["review_features"] = review
    return store.set_quote(conn, part["id"], result)


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


@bp.post("/api/v1/inquiries/<iid>/parts")
def add_part(iid):
    payload = request.get_json(silent=True) or {}
    conn = _conn()
    try:
        return jsonify(store.add_part(conn, iid, payload)), 201
    except KeyError:
        return jsonify({"error": "询价单不存在"}), 404
    finally:
        conn.close()


@bp.post("/api/v1/inquiries/<iid>/quote")
def quote_inquiry(iid):
    conn = _conn()
    try:
        inquiry = store.get_inquiry(conn, iid)
        req = request.get_json(silent=True) or {}
        out = []
        for part in inquiry["parts"]:
            if part["status"] == "confirmed":
                out.append(part)
                continue
            quoted = _quote_part(conn, part, selected_ids=None, features_override=req.get("features"))
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
        selected_ids = payload.get("selected_feature_ids")
        if selected_ids is not None and not isinstance(selected_ids, list):
            selected_ids = None
        if part["status"] not in {"confirmed", "abandoned"}:
            quoted = _quote_part(
                conn, part, selected_ids=selected_ids, features_override=payload.get("features"),
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
        quoted = _quote_part(conn, part)
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
