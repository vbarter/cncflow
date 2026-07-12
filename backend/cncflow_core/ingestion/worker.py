"""单并发工程文件解析Worker。"""
import os
import socket
import time
import multiprocessing as mp

from ..common.db import get_conn, init_schema
from .jobs import claim_job, fail_job, finish_job, recover_stale, update_job
from .pdf_parser import parse_pdf
from .step_parser import parse_step


PARSER_TIMEOUT_SECONDS = int(os.environ.get("CNCFLOW_PARSER_TIMEOUT", "300"))


def _parse_in_child(detected_type, path, options, output):
    try:
        if detected_type == "step":
            output.put({"ok": True, "value": parse_step(path)})
        else:
            output.put({"ok": True, "value": parse_pdf(path, options.get("allow_external_ai", False))})
    except Exception as exc:
        output.put({"ok": False, "error": str(exc)})


def isolated_parse(detected_type, path, options):
    context = mp.get_context("spawn")
    output = context.Queue(maxsize=1)
    process = context.Process(target=_parse_in_child, args=(detected_type, path, options, output))
    process.start()
    process.join(PARSER_TIMEOUT_SECONDS)
    if process.is_alive():
        process.terminate(); process.join(5)
        raise TimeoutError(f"{detected_type.upper()}解析超过{PARSER_TIMEOUT_SECONDS}秒")
    if output.empty():
        raise RuntimeError(f"{detected_type.upper()}解析子进程异常退出，exitcode={process.exitcode}")
    result = output.get()
    if not result["ok"]:
        raise RuntimeError(result["error"])
    return result["value"]


def process_claimed(conn, job):
    result = {"geometry": None, "features": [], "drawing": None, "warnings": []}
    for file in job["files"]:
        if file["detected_type"] == "step":
            update_job(conn, job["job_id"], stage="step_geometry", progress=20, message="正在解析STEP实体")
            parsed = isolated_parse("step", file["storage_path"], job["options"])
            result["geometry"] = parsed["geometry"]
            result["features"].extend(parsed["features"])
            result["warnings"].extend(parsed["warnings"])
        elif file["detected_type"] == "pdf":
            update_job(conn, job["job_id"], stage="pdf_drawing", progress=65, message="正在识别PDF图纸")
            result["drawing"] = isolated_parse("pdf", file["storage_path"], job["options"])
            result["warnings"].extend(result["drawing"].get("warnings", []))
    if result["geometry"] is None:
        result["warnings"].append("未上传STEP，无法获得真实体积、表面积和B-Rep制造特征")
    finish_job(conn, job["job_id"], result)


def run_forever(poll_seconds=1.0):
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    while True:
        conn = get_conn()
        init_schema(conn)
        conn.execute(
            "INSERT INTO parser_workers(worker_id,parser_version,heartbeat_at) VALUES(?,? ,datetime('now')) "
            "ON CONFLICT(worker_id) DO UPDATE SET parser_version=excluded.parser_version,heartbeat_at=datetime('now')",
            (worker_id, "mvp-1"),
        )
        conn.commit()
        recover_stale(conn)
        job = claim_job(conn, worker_id)
        if job is None:
            conn.close()
            time.sleep(poll_seconds)
            continue
        try:
            process_claimed(conn, job)
        except Exception as exc:
            fail_job(conn, job["job_id"], exc)
        finally:
            conn.close()


if __name__ == "__main__":
    run_forever()
