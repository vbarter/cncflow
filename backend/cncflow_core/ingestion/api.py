"""工程文件上传、任务查询与孔特征确认API。"""
import json
import os
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from ..common.db import get_conn
from ..features.hole import pipeline as hole_pipeline
from .jobs import create_job, get_job
from .storage import MAX_JOB_BYTES, store_upload


bp = Blueprint("ingestion", __name__)


def _conn():
    return get_conn(current_app.config.get("DB_PATH"))


@bp.get("/api/v1/parse-capabilities")
def capabilities():
    return jsonify({
        "formats": ["step", "stp", "pdf"], "max_file_mb": 100, "max_job_mb": 150,
        "max_files": 2, "external_ai_available": bool(os.environ.get("VISION_API_KEY")),
        "retention": "local_archive", "confirmation_required": True,
    })


@bp.post("/api/v1/parse-jobs")
def upload_job():
    step = request.files.get("step_file")
    drawing = request.files.get("drawing_file")
    if step is None and drawing is None:
        return jsonify({"error": "至少上传一个STP或PDF文件"}), 400
    conn = _conn()
    provisional_id = os.urandom(16).hex()
    files = []
    try:
        if step is not None and step.filename:
            files.append(store_upload(step, provisional_id, "step"))
        if drawing is not None and drawing.filename:
            files.append(store_upload(drawing, provisional_id, "drawing"))
        if not files:
            raise ValueError("未选择有效文件")
        if sum(item["size_bytes"] for item in files) > MAX_JOB_BYTES:
            raise ValueError("单次任务文件总大小不能超过150MB")
        options = {"allow_external_ai": request.form.get("allow_external_ai", "false").lower() == "true"}
        job_id = create_job(conn, files, options)
        return jsonify({
            "job_id": job_id, "status": "queued", "status_url": f"/api/v1/parse-jobs/{job_id}"
        }), 202
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    finally:
        conn.close()


@bp.get("/api/v1/parse-jobs/<job_id>")
def job_status(job_id):
    conn = _conn()
    try:
        return jsonify(get_job(conn, job_id))
    except KeyError:
        return jsonify({"error": "解析任务不存在"}), 404
    finally:
        conn.close()


@bp.post("/api/v1/parse-jobs/<job_id>/confirm")
def confirm_job(job_id):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "请求体须为JSON对象"}), 400
    holes = payload.get("holes")
    if not isinstance(holes, list) or not holes:
        return jsonify({"error": "至少确认一个孔特征"}), 400
    material = payload.get("material_code") or payload.get("material")
    if not material:
        return jsonify({"error": "material_code或material必填"}), 400
    conn = _conn()
    try:
        job = get_job(conn, job_id)
        if job["status"] not in {"needs_review", "completed"}:
            return jsonify({"error": f"任务状态 {job['status']} 尚不能确认"}), 409
        plans = []
        for index, hole in enumerate(holes, start=1):
            feature = {
                "type": "hole", "diameter_mm": hole.get("diameter_mm"), "depth_mm": hole.get("depth_mm"),
                "hole_type": hole.get("hole_type", "through"), "bottom_shape": hole.get("bottom_shape", "cone"),
                "surface": hole.get("surface", "top"), "thread": hole.get("thread"),
            }
            plan_payload = {
                "feature": feature, "material_code": material,
                "tolerance_it": payload.get("tolerance_it"), "roughness_ra": payload.get("roughness_ra"),
                "strategy": payload.get("strategy", "both"), "machine_profile": payload.get("machine_profile"),
            }
            plan = hole_pipeline.run(plan_payload, conn)
            plans.append({"hole_id": hole.get("feature_id") or f"confirmed-hole-{index}", "input": feature, "plan": plan})
        conn.execute(
            "UPDATE parse_jobs SET status='completed',stage='completed',confirmed_json=?,plans_json=?,"
            "updated_at=datetime('now') WHERE job_id=?",
            (json.dumps(payload, ensure_ascii=False), json.dumps(plans, ensure_ascii=False), job_id),
        )
        conn.execute(
            "INSERT INTO parser_events(job_id,stage,message) VALUES(?,?,?)",
            (job_id, "completed", f"已确认{len(holes)}个孔并生成工艺方案"),
        )
        conn.commit()
        return jsonify({"job_id": job_id, "status": "completed", "plans": plans})
    except (ValueError, TypeError) as exc:
        conn.rollback()
        return jsonify({"error": str(exc)}), 400
    except KeyError:
        return jsonify({"error": "解析任务不存在"}), 404
    finally:
        conn.close()
