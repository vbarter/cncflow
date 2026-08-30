"""单并发工程文件解析Worker。"""
import os
import socket
import time
import multiprocessing as mp

from ..common.db import get_conn, init_schema
from ..geometry import FEATURE_SCHEMA
from ..geometry.plugins import plugin_names
from ..geometry.service import parse_step_file
from ..geometry.mesh import step_to_glb
from .jobs import (
    StaleJobClaim,
    claim_job,
    fail_job,
    finish_job,
    recover_stale,
    update_job,
)
from .pdf_parser import parse_pdf
from .storage import materialize, storage_root
from . import r2



def _store_mesh(job_id, mesh_bytes):
    """Write GLB to local disk and R2. Never put bytes into result_json."""
    if not mesh_bytes:
        return None
    key = f"meshes/{job_id}.glb"
    local = str(storage_root() / "meshes" / f"{job_id}.glb")
    os.makedirs(os.path.dirname(local), exist_ok=True)
    with open(local, "wb") as fh:
        fh.write(mesh_bytes)
    stored = {"key": key, "format": "glb", "bytes": len(mesh_bytes), "path": local, "storage": "local"}
    if r2.configured():
        try:
            r2.put_object(key, mesh_bytes, "model/gltf-binary")
            stored["storage"] = "r2"
        except Exception:
            pass
    return stored


PARSER_TIMEOUT_SECONDS = int(os.environ.get("CNCFLOW_PARSER_TIMEOUT", "300"))


def _parse_in_child(detected_type, path, options, output):
    try:
        if detected_type == "step":
            output.put({"ok": True, "value": parse_step_file(path)})
        else:
            output.put({"ok": True, "value": parse_pdf(path, options.get("allow_external_ai", False))})
    except Exception as exc:
        output.put({"ok": False, "error": str(exc)})


def _parse_inline(detected_type, path, options):
    if detected_type == "step":
        return parse_step_file(path)
    return parse_pdf(path, options.get("allow_external_ai", False))


def isolated_parse(detected_type, path, options):
    if not os.path.exists(path):
        raise FileNotFoundError(f"解析文件不存在: {path}")
    if os.environ.get("CNCFLOW_PARSE_INLINE") == "1":
        return _parse_inline(detected_type, path, options)
    # Cloudchamber 可能禁 exec，spawn 会抛裸 Errno 2；回退同进程解析。
    try:
        context = mp.get_context("spawn")
        output = context.Queue(maxsize=1)
        process = context.Process(target=_parse_in_child, args=(detected_type, path, options, output))
        process.start()
    except (FileNotFoundError, OSError) as exc:
        if getattr(exc, "errno", None) not in (None, 2) and not isinstance(exc, FileNotFoundError):
            raise
        return _parse_inline(detected_type, path, options)
    process.join(PARSER_TIMEOUT_SECONDS)
    if process.is_alive():
        process.terminate(); process.join(5)
        raise TimeoutError(f"{detected_type.upper()}解析超过{PARSER_TIMEOUT_SECONDS}秒")
    if output.empty():
        raise RuntimeError(f"{detected_type.upper()}解析子进程异常退出，exitcode={process.exitcode}")
    result = output.get()
    if not result["ok"]:
        err = result["error"]
        if "No such file or directory" in err:
            return _parse_inline(detected_type, path, options)
        raise RuntimeError(err)
    return result["value"]


def process_claimed(conn, job):
    result = {"geometry": None, "features": [], "drawing": None, "warnings": []}
    claim = {
        "worker_id": job.get("worker_id"),
        "attempt": job.get("attempt"),
    }
    for file in job["files"]:
        suffix = ".step" if file["detected_type"] == "step" else ".pdf"
        if file["detected_type"] == "step":
            names = ",".join(plugin_names())
            update_job(
                conn, job["job_id"], stage="geometry_parse", progress=20,
                message=f"geometry-service {FEATURE_SCHEMA} plugins={names}",
                **claim,
            )
            step_path = materialize(file["storage_path"], suffix=suffix)
            parsed = isolated_parse("step", step_path, job["options"])
            result["geometry"] = parsed["geometry"]
            result["features"].extend(parsed.get("features") or [])
            result["warnings"].extend(parsed.get("warnings") or [])
            result["plugins"] = parsed.get("plugins")
            result["feature_schema"] = parsed.get("feature_schema") or FEATURE_SCHEMA
            result["parser"] = parsed.get("parser") or "geometry-service"
            result["parser_version"] = parsed.get("parser_version") or FEATURE_SCHEMA
            mesh_bytes = parsed.pop("_mesh_glb", None)
            if not mesh_bytes:
                try:
                    mesh_bytes = step_to_glb(step_path)
                except Exception as exc:
                    result["warnings"].append("网格导出失败: %s" % exc)
            mesh = _store_mesh(job["job_id"], mesh_bytes)
            if mesh:
                result["mesh"] = mesh
            else:
                result["warnings"].append("网格未写入，零件详情将显示空态")
        elif file["detected_type"] == "pdf":
            update_job(
                conn, job["job_id"], stage="pdf_drawing", progress=65,
                message="正在通过 tu-zi 识别 PDF 图纸", **claim,
            )
            try:
                result["drawing"] = isolated_parse(
                    "pdf",
                    materialize(file["storage_path"], suffix=suffix),
                    job["options"],
                )
                result["warnings"].extend(result["drawing"].get("warnings", []))
            except Exception as exc:
                warning = f"PDF 回填失败，STEP 报价继续: {exc}"
                result["drawing"] = {
                    "parser": "pdf",
                    "backfill": {},
                    "tuzi": {"provider": "tu-zi", "called": False, "ok": False},
                    "warnings": [warning],
                }
                result["warnings"].append(warning)
    if result["geometry"] is None:
        result["warnings"].append("未上传STEP，无法获得真实体积、表面积和B-Rep制造特征")
    finish_job(conn, job["job_id"], result, **claim)


def run_forever(poll_seconds=1.0):
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    while True:
        conn = get_conn()
        init_schema(conn)
        conn.execute(
            "INSERT INTO parser_workers(worker_id,parser_version,heartbeat_at) VALUES(?,? ,datetime('now')) "
            "ON CONFLICT(worker_id) DO UPDATE SET parser_version=excluded.parser_version,heartbeat_at=datetime('now')",
            (worker_id, FEATURE_SCHEMA),
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
        except StaleJobClaim:
            pass
        except Exception as exc:
            try:
                fail_job(
                    conn, job["job_id"], exc,
                    worker_id=job["worker_id"], attempt=job["attempt"],
                )
            except StaleJobClaim:
                pass
        finally:
            conn.close()


if __name__ == "__main__":
    run_forever()
