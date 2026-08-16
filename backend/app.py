"""cncflow 后端服务：加工特征评估统一入口。

POST /api/v1/process-plan  —— feature.type 分发（一期仅 hole，二期加 face 时注册新 pipeline 即可）
"""
import json
import subprocess
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
import os

from cncflow_core.common.db import get_conn, init_schema
from cncflow_core.common import persist
from cncflow_core.common.materials import list_materials, seed_material_catalog
from cncflow_core.features.hole import pipeline as hole_pipeline
from cncflow_core.features.face import pipeline as face_pipeline
from cncflow_core.features.pocket import pipeline as pocket_pipeline
from cncflow_core.features.thread import pipeline as thread_pipeline
from cncflow_core.features.surface import pipeline as surface_pipeline
from cncflow_core.features.fixture import pipeline as fixture_pipeline
from cncflow_core.factory.api import bp as factory_bp
from cncflow_core.quoting.api import bp as quoting_bp
from cncflow_core.inquiries.api import bp as inquiries_bp
from cncflow_core.factory.store import seed_factory
from data.seed_tool_specs import seed_tool_specs
from data.seed_tools import seed as seed_tools
from cncflow_core.ingestion.api import bp as ingestion_bp
from cncflow_core.geometry.api import bp as geometry_bp


def _install_cors(app: Flask) -> None:
    """Pages 与 API 不同源时放开浏览器预检。未配置则保持同域（VPS nginx）。"""
    allowed = [item.strip() for item in os.environ.get("CNCFLOW_CORS_ORIGINS", "").split(",") if item.strip()]

    def _apply(resp):
        origin = request.headers.get("Origin")
        if origin and ("*" in allowed or origin in allowed):
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Vary"] = "Origin"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
            resp.headers["Access-Control-Max-Age"] = "86400"
        return resp

    @app.before_request
    def _cors_preflight():
        if request.method == "OPTIONS" and allowed:
            return _apply(app.make_response(("", 204)))

    @app.after_request
    def _cors_headers(resp):
        return _apply(resp) if allowed else resp


FEATURE_PIPELINES = {
    "hole": hole_pipeline.run,
    "face": face_pipeline.run,
    "pocket": pocket_pipeline.run,
    "thread": thread_pipeline.run,
    "surface": surface_pipeline.run,
    "fixture": fixture_pipeline.run,
}


def _rules_version() -> str:
    """规则版本 = git hash，写入 audit_log 保证判定可复现。"""
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=3,
            cwd=Path(__file__).resolve().parent,
        ).stdout.strip() or "unknown"
    except OSError:
        return "unknown"


def create_app(db_path=None) -> Flask:
    frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    app = Flask(__name__, static_folder=None)
    app.config["DB_PATH"] = db_path
    app.config["RULES_VERSION"] = _rules_version()
    app.config["MAX_CONTENT_LENGTH"] = 150 * 1024 * 1024
    _install_cors(app)

    require_persistent = os.environ.get("CNCFLOW_REQUIRE_PERSISTENT_DB") == "1"
    resolved = Path(db_path or os.environ.get("CNCFLOW_DB_PATH") or "")
    if require_persistent and not str(resolved).startswith("/data"):
        raise RuntimeError("CNCFLOW_REQUIRE_PERSISTENT_DB=1 要求数据库在 /data 持久卷")

    conn = get_conn(db_path)
    init_schema(conn)
    seed_material_catalog(conn)
    seed_tool_specs(conn)
    if conn.execute("SELECT COUNT(*) FROM tools").fetchone()[0] == 0:
        seed_tools(conn)
    seed_factory(conn)
    conn.close()
    app.register_blueprint(ingestion_bp)
    app.register_blueprint(ingestion_bp, url_prefix="/cncflow", name="ingestion_prefixed")
    app.register_blueprint(factory_bp)
    app.register_blueprint(factory_bp, url_prefix="/cncflow", name="factory_prefixed")
    app.register_blueprint(quoting_bp)
    app.register_blueprint(quoting_bp, url_prefix="/cncflow", name="quoting_prefixed")
    app.register_blueprint(inquiries_bp)
    app.register_blueprint(inquiries_bp, url_prefix="/cncflow", name="inquiries_prefixed")
    app.register_blueprint(geometry_bp)
    app.register_blueprint(geometry_bp, url_prefix="/cncflow", name="geometry_prefixed")

    @app.errorhandler(413)
    def upload_too_large(_exc):
        return jsonify({"error": "单次上传总大小不能超过150MB"}), 413

    @app.post("/api/v1/process-plan")
    def process_plan():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "请求体须为 JSON 对象"}), 400

        feature_type = (payload.get("feature") or {}).get("type")
        pipeline_fn = FEATURE_PIPELINES.get(feature_type)
        if pipeline_fn is None:
            return jsonify({
                "error": f"暂不支持的特征类型: {feature_type!r}，当前支持 {sorted(FEATURE_PIPELINES)}"
            }), 400

        conn = get_conn(app.config["DB_PATH"])
        try:
            result = pipeline_fn(payload, conn)
        except ValueError as exc:
            conn.close()
            return jsonify({"error": str(exc)}), 400
        verdict = result.get("machinability") or result.get("difficulty") or {}
        conn.execute(
            "INSERT INTO audit_log (request_json, machinability_level, fired_rules, "
            "response_json, rules_version) VALUES (?,?,?,?,?)",
            (
                json.dumps(payload, ensure_ascii=False),
                verdict.get("level"),
                json.dumps(verdict.get("fired_rules") or [], ensure_ascii=False),
                json.dumps(result, ensure_ascii=False),
                app.config["RULES_VERSION"],
            ),
        )
        conn.commit()
        conn.close()
        return jsonify(result)

    @app.get("/api/v1/health")
    @app.get("/cncflow/api/v1/health")
    def health():
        conn = get_conn(app.config["DB_PATH"])
        queued = conn.execute("SELECT COUNT(*) FROM parse_jobs WHERE status='queued'").fetchone()[0]
        worker = conn.execute(
            "SELECT worker_id,parser_version,heartbeat_at FROM parser_workers "
            "WHERE heartbeat_at>=datetime('now','-10 seconds') ORDER BY heartbeat_at DESC LIMIT 1"
        ).fetchone()
        conn.close()
        persist_info = persist.health_snapshot()
        require_persistent = os.environ.get("CNCFLOW_REQUIRE_PERSISTENT_DB") == "1"
        degraded = (not worker) or (require_persistent and not persist_info["r2"])
        return jsonify({"status": "degraded" if degraded else "ok", "features": sorted(FEATURE_PIPELINES),
                        "parser": {"available": bool(worker), "queued": queued,
                                   "worker_id": worker["worker_id"] if worker else None,
                                   "version": worker["parser_version"] if worker else None,
                                   "last_heartbeat": worker["heartbeat_at"] if worker else None,
                                   "mesh_export": True},
                        "persist": persist_info})

    @app.get("/api/v1/materials")
    @app.get("/cncflow/api/v1/materials")
    def materials_catalog():
        conn = get_conn(app.config["DB_PATH"])
        try:
            items = list_materials(
                conn,
                family=request.args.get("family"),
                planning_status=request.args.get("planning_status"),
                query=request.args.get("q"),
            )
            return jsonify({"items": items, "count": len(items)})
        finally:
            conn.close()

    @app.get("/")
    @app.get("/cncflow/")
    def frontend_index():
        if (frontend_dist / "index.html").exists():
            return send_from_directory(frontend_dist, "index.html")
        return jsonify({"service": "cncflow", "message": "frontend not built"})

    @app.get("/assets/<path:filename>")
    @app.get("/cncflow/assets/<path:filename>")
    def frontend_assets(filename):
        return send_from_directory(frontend_dist / "assets", filename)

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5001, debug=False)
