"""POST /api/v1/quotes — 始终 200 出报价。"""
from flask import Blueprint, current_app, jsonify, request

from ..common.db import get_conn
from .engine import quote

bp = Blueprint("quoting", __name__)


@bp.post("/api/v1/quotes")
def create_quote():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "请求体须为 JSON 对象"}), 400
    conn = get_conn(current_app.config.get("DB_PATH"))
    try:
        result = quote(payload, conn, rules_version=current_app.config.get("RULES_VERSION") or "")
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    finally:
        conn.close()
