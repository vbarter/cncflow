"""cncflow 后端服务：加工特征评估统一入口。

POST /api/v1/process-plan  —— feature.type 分发（一期仅 hole，二期加 face 时注册新 pipeline 即可）
"""
import json
import subprocess
from pathlib import Path

from flask import Flask, jsonify, request

from cncflow_core.common.db import get_conn, init_schema
from cncflow_core.common.materials import list_materials, seed_material_catalog
from cncflow_core.features.hole import pipeline as hole_pipeline
from data.seed_tool_specs import seed_tool_specs

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
    app = Flask(__name__)
    app.config["DB_PATH"] = db_path
    app.config["RULES_VERSION"] = _rules_version()

    conn = get_conn(db_path)
    init_schema(conn)
    seed_material_catalog(conn)
    seed_tool_specs(conn)
    conn.close()

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
    def health():
        return jsonify({"status": "ok", "features": sorted(FEATURE_PIPELINES)})

    @app.get("/api/v1/materials")
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

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5001, debug=False)
