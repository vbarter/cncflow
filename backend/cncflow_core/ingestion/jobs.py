"""解析任务的SQLite仓储与轻量队列操作。"""
import json
import sqlite3
import uuid


PUBLIC_FIELDS = "job_id,status,stage,progress,result_json,confirmed_json,plans_json,error,attempts,created_at,updated_at"


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
    return result


def claim_job(conn: sqlite3.Connection, worker_id: str):
    conn.execute("BEGIN IMMEDIATE")
    row = conn.execute(
        "SELECT job_id FROM parse_jobs WHERE status='queued' AND attempts<2 ORDER BY created_at LIMIT 1"
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
    return {"job_id": job_id, "files": files, "options": options}


def update_job(conn, job_id, *, stage, progress, message=None):
    conn.execute(
        "UPDATE parse_jobs SET stage=?,progress=?,heartbeat_at=datetime('now'),updated_at=datetime('now') WHERE job_id=?",
        (stage, progress, job_id),
    )
    if message:
        event(conn, job_id, stage, message)
    conn.commit()


def finish_job(conn, job_id, result):
    conn.execute(
        "UPDATE parse_jobs SET status='needs_review',stage='review',progress=100,result_json=?,"
        "updated_at=datetime('now') WHERE job_id=?",
        (json.dumps(result, ensure_ascii=False), job_id),
    )
    event(conn, job_id, "review", "解析完成，请确认识别结果")
    conn.commit()


def fail_job(conn, job_id, error):
    attempts = conn.execute("SELECT attempts FROM parse_jobs WHERE job_id=?", (job_id,)).fetchone()[0]
    status = "queued" if attempts < 2 else "failed"
    conn.execute(
        "UPDATE parse_jobs SET status=?,stage='failed',error=?,progress=100,updated_at=datetime('now') WHERE job_id=?",
        (status, str(error)[:2000], job_id),
    )
    event(conn, job_id, "failed", str(error)[:500])
    conn.commit()


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
