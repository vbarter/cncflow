"""解析任务的SQLite仓储与轻量队列操作。"""
import json
import sqlite3
import uuid

from cncflow_core.common import persist


PUBLIC_FIELDS = "job_id,status,stage,progress,result_json,confirmed_json,plans_json,error,attempts,created_at,updated_at"


class StaleJobClaim(RuntimeError):
    """Worker claim 已被超时恢复或用户重试取代。"""


def create_job(conn: sqlite3.Connection, files: list, options: dict) -> str:
    job_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO parse_jobs(job_id,options_json) VALUES(?,?)",
        (job_id, json.dumps(options, ensure_ascii=False)),
    )
    conn.executemany(
        "INSERT INTO uploaded_files(job_id,role,original_name,storage_path,sha256,size_bytes,detected_type) "
        "VALUES(?,?,?,?,?,?,?)",
        [(job_id, f["role"], f["original_name"], f["storage_path"], f["sha256"],
          f["size_bytes"], f["detected_type"]) for f in files],
    )
    event(conn, job_id, "queued", "文件已安全保存，等待解析")
    conn.commit()
    return job_id


def event(conn, job_id: str, stage: str, message: str):
    conn.execute("INSERT INTO parser_events(job_id,stage,message) VALUES(?,?,?)", (job_id, stage, message))


def get_job(conn: sqlite3.Connection, job_id: str) -> dict:
    row = conn.execute(f"SELECT {PUBLIC_FIELDS} FROM parse_jobs WHERE job_id=?", (job_id,)).fetchone()
    if row is None:
        raise KeyError(job_id)
    result = dict(row)
    for key in ("result_json", "confirmed_json", "plans_json"):
        public_key = key.removesuffix("_json")
        result[public_key] = json.loads(result.pop(key) or "null")
    result["files"] = [dict(r) for r in conn.execute(
        "SELECT role,original_name,sha256,size_bytes,detected_type FROM uploaded_files WHERE job_id=? ORDER BY role",
        (job_id,),
    )]
    result["events"] = [dict(r) for r in conn.execute(
        "SELECT stage,message,created_at FROM parser_events WHERE job_id=? ORDER BY id", (job_id,),
    )]
    options = json.loads(conn.execute("SELECT options_json FROM parse_jobs WHERE job_id=?", (job_id,)).fetchone()["options_json"] or "{}")
    result["part_id"] = options.get("part_id")
    return result


def claim_job(conn: sqlite3.Connection, worker_id: str):
    conn.execute("BEGIN IMMEDIATE")
    row = conn.execute(
        "SELECT job_id,attempts FROM parse_jobs WHERE status='queued' AND attempts<2 ORDER BY created_at LIMIT 1"
    ).fetchone()
    if row is None:
        conn.rollback()
        return None
    job_id = row["job_id"]
    conn.execute(
        "UPDATE parse_jobs SET status='running',stage='starting',progress=5,attempts=attempts+1,worker_id=?,"
        "started_at=datetime('now'),heartbeat_at=datetime('now'),updated_at=datetime('now') WHERE job_id=?",
        (worker_id, job_id),
    )
    event(conn, job_id, "starting", f"解析Worker {worker_id} 已领取任务")
    conn.commit()
    files = [dict(r) for r in conn.execute("SELECT * FROM uploaded_files WHERE job_id=?", (job_id,))]
    options = json.loads(conn.execute("SELECT options_json FROM parse_jobs WHERE job_id=?", (job_id,)).fetchone()[0] or "{}")
    return {
        "job_id": job_id,
        "files": files,
        "options": options,
        "worker_id": worker_id,
        "attempt": row["attempts"] + 1,
    }


def update_job(
    conn, job_id, *, stage, progress, message=None, worker_id=None, attempt=None,
):
    if worker_id is None or attempt is None:
        cursor = conn.execute(
            "UPDATE parse_jobs SET stage=?,progress=?,heartbeat_at=datetime('now'),"
            "updated_at=datetime('now') WHERE job_id=?",
            (stage, progress, job_id),
        )
    else:
        cursor = conn.execute(
            "UPDATE parse_jobs SET stage=?,progress=?,heartbeat_at=datetime('now'),"
            "updated_at=datetime('now') WHERE job_id=? AND status='running' "
            "AND worker_id=? AND attempts=?",
            (stage, progress, job_id, worker_id, attempt),
        )
    if cursor.rowcount != 1:
        conn.rollback()
        raise StaleJobClaim(job_id)
    if message:
        event(conn, job_id, stage, message)
    conn.commit()


def _part_id(conn, job_id):
    row = conn.execute("SELECT options_json FROM parse_jobs WHERE job_id=?", (job_id,)).fetchone()
    if row is None:
        return None
    return (json.loads(row["options_json"] or "{}") or {}).get("part_id")


def _current_part_id(conn, job_id):
    part_id = _part_id(conn, job_id)
    if not part_id:
        return None
    row = conn.execute(
        "SELECT id FROM parts WHERE id=? AND parse_job_id=?",
        (part_id, job_id),
    ).fetchone()
    return row["id"] if row else None


def _apply_bbox(conn, part_id, result):
    box = ((result or {}).get("geometry") or {}).get("bounding_box_mm") or {}
    vals = [box.get("x"), box.get("y"), box.get("z")]
    nums = [float(v) for v in vals if v is not None]
    if len(nums) >= 3:
        length, width, height = sorted(nums, reverse=True)
        conn.execute(
            "UPDATE parts SET length=?, width=?, height=?, status='need_params', updated_at=datetime('now') WHERE id=?",
            (length, width, height, part_id),
        )
    else:
        conn.execute(
            "UPDATE parts SET status='need_params', updated_at=datetime('now') WHERE id=?",
            (part_id,),
        )


def _apply_pdf_backfill(conn, job_id, part_id, result):
    drawing = (result or {}).get("drawing")
    if not isinstance(drawing, dict):
        return
    backfill = drawing.get("backfill")
    if not isinstance(backfill, dict):
        backfill = {}
    tuzi = drawing.get("tuzi") if isinstance(drawing.get("tuzi"), dict) else {}
    sets, values = [], []
    for field in (
        "material_code",
        "tolerance_it",
        "roughness_ra",
        "surface_finish",
        "qty",
    ):
        if backfill.get(field) not in (None, ""):
            sets.append(f"{field}=?")
            values.append(backfill[field])
    if isinstance(backfill.get("thread_specs"), list):
        sets.append("thread_specs_json=?")
        values.append(json.dumps(backfill["thread_specs"], ensure_ascii=False))

    status = "applied" if sets else "failed"
    warning = None if sets else (
        tuzi.get("warning")
        or next(iter(drawing.get("warnings") or []), None)
        or "tu-zi 未返回可回填字段"
    )
    sets.extend(["pdf_backfill_status=?", "pdf_backfill_warning=?"])
    values.extend([status, warning])
    values.append(part_id)
    conn.execute(
        f"UPDATE parts SET {', '.join(sets)}, updated_at=datetime('now') WHERE id=?",
        values,
    )
    if sets and status == "applied":
        names = [label for field, label in BACKFILL_EVENT_FIELDS.items() if field in backfill]
        event(conn, job_id, "pdf_backfill", f"PDF 已回填：{', '.join(names)}")
    else:
        event(conn, job_id, "pdf_backfill", f"PDF 未回填：{warning}")


BACKFILL_EVENT_FIELDS = {
    "material_code": "材料",
    "tolerance_it": "IT",
    "roughness_ra": "Ra",
    "surface_finish": "表面处理",
    "thread_specs": "螺纹规格",
    "qty": "数量",
}


def _checkpoint_db():
    """解析落库后立刻打检查点；备份失败不影响任务状态。"""
    persist.try_backup_db()


def finish_job(conn, job_id, result, *, worker_id=None, attempt=None):
    params = [json.dumps(result, ensure_ascii=False), job_id]
    claim_where = ""
    if worker_id is not None and attempt is not None:
        claim_where = " AND status='running' AND worker_id=? AND attempts=?"
        params.extend([worker_id, attempt])
    cursor = conn.execute(
        "UPDATE parse_jobs SET status='needs_review',stage='review',progress=100,result_json=?,"
        f"updated_at=datetime('now') WHERE job_id=?{claim_where}",
        params,
    )
    if cursor.rowcount != 1:
        conn.rollback()
        raise StaleJobClaim(job_id)
    event(conn, job_id, "review", "解析完成，请确认识别结果")
    pid = _current_part_id(conn, job_id)
    if pid:
        _apply_pdf_backfill(conn, job_id, pid, result)
        _apply_bbox(conn, pid, result)
    conn.commit()
    if pid:
        try:
            from ..inquiries import store as inquiry_store
            from ..inquiries.api import _maybe_quote
            part = inquiry_store.get_part(conn, pid)
            _maybe_quote(conn, part)
        except Exception:
            pass
    _checkpoint_db()


def fail_job(conn, job_id, error, *, worker_id=None, attempt=None):
    row = conn.execute(
        "SELECT attempts FROM parse_jobs WHERE job_id=?",
        (job_id,),
    ).fetchone()
    if row is None:
        raise KeyError(job_id)
    attempts = row["attempts"]
    status = "queued" if attempts < 2 else "failed"
    params = [status, str(error)[:2000], job_id]
    claim_where = ""
    if worker_id is not None and attempt is not None:
        claim_where = " AND status='running' AND worker_id=? AND attempts=?"
        params.extend([worker_id, attempt])
    cursor = conn.execute(
        "UPDATE parse_jobs SET status=?,stage='failed',error=?,progress=100,worker_id=NULL,"
        f"heartbeat_at=NULL,updated_at=datetime('now') WHERE job_id=?{claim_where}",
        params,
    )
    if cursor.rowcount != 1:
        conn.rollback()
        raise StaleJobClaim(job_id)
    event(conn, job_id, "failed", str(error)[:500])
    pid = _current_part_id(conn, job_id)
    if pid and status == "failed":
        conn.execute(
            "UPDATE parts SET status='parse_failed', updated_at=datetime('now') WHERE id=?",
            (pid,),
        )
    conn.commit()
    _checkpoint_db()


def retry_job(conn, job_id):
    conn.execute("BEGIN IMMEDIATE")
    row = conn.execute(
        "SELECT status,options_json FROM parse_jobs WHERE job_id=?",
        (job_id,),
    ).fetchone()
    if row is None:
        conn.rollback()
        raise KeyError(job_id)
    if row["status"] != "failed":
        conn.rollback()
        raise ValueError(f"任务状态 {row['status']} 无需重试")

    conn.execute(
        "UPDATE parse_jobs SET status='queued',stage='queued',progress=0,error=NULL,attempts=0,"
        "worker_id=NULL,started_at=NULL,heartbeat_at=NULL,result_json=NULL,confirmed_json=NULL,"
        "plans_json=NULL,updated_at=datetime('now') WHERE job_id=? AND status='failed'",
        (job_id,),
    )
    options = json.loads(row["options_json"] or "{}")
    part_id = options.get("part_id")
    if part_id:
        part = conn.execute(
            "SELECT parse_job_id FROM parts WHERE id=?",
            (part_id,),
        ).fetchone()
        if part is None or part["parse_job_id"] != job_id:
            conn.rollback()
            raise ValueError("解析任务已被新上传替换")
        conn.execute(
            "UPDATE parts SET status='parsing', updated_at=datetime('now') "
            "WHERE id=? AND parse_job_id=?",
            (part_id, job_id),
        )
    event(conn, job_id, "queued", "用户重试解析")
    conn.commit()
    return get_job(conn, job_id)


def recover_stale(conn):
    conn.execute(
        "UPDATE parse_jobs SET status='queued',stage='queued',worker_id=NULL,error='Worker超时，自动重试' "
        "WHERE status='running' AND heartbeat_at < datetime('now','-10 minutes') AND attempts<2"
    )
    conn.execute(
        "UPDATE parse_jobs SET status='failed',stage='failed',error='Worker连续超时' "
        "WHERE status='running' AND heartbeat_at < datetime('now','-10 minutes') AND attempts>=2"
    )
    conn.commit()
