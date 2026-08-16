"""询价 / 零件 HTTP。"""
from flask import Blueprint, current_app, jsonify, request

from ..common.db import get_conn
from ..ingestion.jobs import get_job
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


def _review_and_quote_features(parsed_feats, selected_ids, L, W):
    review = []
    holes = []
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
        if feat.get("type") == "hole" and on:
            dim = feat.get("dimensions") or {}
            d = dim.get("diameter_mm") or feat.get("diameter_mm")
            depth = dim.get("depth_mm") or feat.get("depth_mm")
            if d and depth:
                holes.append({"type": "hole", "diameter_mm": d, "depth_mm": depth, "hole_type": "through", "feature_id": fid})
    features = holes + [{"type": "face", "length": L, "width": W, "depth": 1}]
    return review, features


def _parse_geom(conn, part):
    job = None
    if part.get("parse_job_id"):
        try:
            job = get_job(conn, part["parse_job_id"])
        except KeyError:
            job = None
    geom = (job or {}).get("result") or {}
    if isinstance(geom, dict):
        return geom.get("geometry") or {}, geom.get("features") or []
    return {}, []


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
    result = quote({
        "material": part.get("material_code") or "铝合金",
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
    }, conn, rules_version=current_app.config.get("RULES_VERSION") or "")
    result["review_features"] = review
    return store.set_quote(conn, part["id"], result)


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
        return jsonify(store.get_part(conn, pid))
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
        if part["status"] == "revising" or selected_ids is not None:
            quoted = _quote_part(
                conn, part, selected_ids=selected_ids, features_override=payload.get("features"),
            )
            if quoted is not None:
                part = quoted
        return jsonify(part)
    except PermissionError:
        return jsonify({"error": "已确认报价不可再改"}), 409
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
