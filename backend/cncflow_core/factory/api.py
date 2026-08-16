"""工厂配置 HTTP。"""
from flask import Blueprint, current_app, jsonify, request

from ..common.db import get_conn
from .store import get_config, put_config

bp = Blueprint("factory", __name__)


def _conn():
    return get_conn(current_app.config.get("DB_PATH"))


@bp.get("/api/v1/factory-config")
def read_config():
    conn = _conn()
    try:
        return jsonify(get_config(conn))
    finally:
        conn.close()


@bp.put("/api/v1/factory-config")
def write_config():
    payload = request.get_json(silent=True)
    conn = _conn()
    try:
        return jsonify(put_config(conn, payload if isinstance(payload, dict) else {}))
    except (ValueError, KeyError, TypeError) as exc:
        return jsonify({"error": str(exc)}), 400
    finally:
        conn.close()
