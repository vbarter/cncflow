"""询价 / 零件 HTTP。"""
from flask import Blueprint, current_app, jsonify, request

from ..common.db import get_conn
from ..quoting.engine import quote
from . import store

bp = Blueprint("inquiries", __name__)


def _conn():
    return get_conn(current_app.config.get("DB_PATH"))


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
        out = []
        for part in inquiry["parts"]:
            if part["status"] == "confirmed":
                out.append(part)
                continue
            L = part.get("length") or part.get("diameter")
            W = part.get("width") or part.get("diameter")
            H = part.get("height")
            if not L or not W:
                out.append(part)
                continue
            payload = {
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
                "features": (request.get_json(silent=True) or {}).get("features") or [
                    {"type": "face", "length": L, "width": W, "depth": 1}
                ],
            }
            result = quote(payload, conn, rules_version=current_app.config.get("RULES_VERSION") or "")
            out.append(store.set_quote(conn, part["id"], result))
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
        if part["status"] == "revising":
            L = part.get("length") or part.get("diameter")
            W = part.get("width") or part.get("diameter")
            H = part.get("height")
            if not L or not W:
                return jsonify(part)
            q = quote({
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
                "features": payload.get("features") or [
                    {"type": "face", "length": L, "width": W, "depth": 1}
                ],
            }, conn, rules_version=current_app.config.get("RULES_VERSION") or "")
            part = store.set_quote(conn, pid, q)
        return jsonify(part)
    except PermissionError:
        return jsonify({"error": "已确认报价不可再改"}), 409
    except KeyError:
        return jsonify({"error": "零件不存在"}), 404
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
