"""cncflow 后端服务：加工特征评估统一入口。

POST /api/v1/process-plan  —— feature.type 分发（一期仅 hole，二期加 face 时注册新 pipeline 即可）
"""
import json
import subprocess
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from cncflow_core.common.db import get_conn, init_schema
from cncflow_core.common.materials import list_materials, seed_material_catalog
from cncflow_core.features.hole import pipeline as hole_pipeline
from data.seed_tool_specs import seed_tool_specs
from cncflow_core.ingestion.api import bp as ingestion_bp

# 特征分发注册表：feature_type → pipeline 函数（二期：FEATURE_PIPELINES["face"] = face_pipeline.run）
FEATURE_PIPELINES = {"hole": hole_pipeline.run}


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

    conn = get_conn(db_path)
    init_schema(conn)
    seed_material_catalog(conn)
    seed_tool_specs(conn)
    conn.close()
    app.register_blueprint(ingestion_bp)
    # 便于本地直接访问构建时base=/cncflow/的前端；生产Nginx会先剥离此前缀。
    app.register_blueprint(ingestion_bp, url_prefix="/cncflow", name="ingestion_prefixed")

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
        conn.execute(
            "INSERT INTO audit_log (request_json, machinability_level, fired_rules, "
            "response_json, rules_version) VALUES (?,?,?,?,?)",
            (
                json.dumps(payload, ensure_ascii=False),
                result["machinability"]["level"],
                json.dumps(result["machinability"]["fired_rules"], ensure_ascii=False),
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
        return jsonify({"status": "ok" if worker else "degraded", "features": sorted(FEATURE_PIPELINES),
                        "parser": {"available": bool(worker), "queued": queued,
                                   "worker_id": worker["worker_id"] if worker else None,
                                   "version": worker["parser_version"] if worker else None,
                                   "last_heartbeat": worker["heartbeat_at"] if worker else None}})

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
