"""把 SQLite 检查点备份到 R2。Cloudflare Containers 磁盘是临时的。"""
from __future__ import annotations

import os
import signal
import sqlite3
import sys
import time
from pathlib import Path

from cncflow_core.ingestion import r2

DB_OBJECT_KEY = os.environ.get("CNCFLOW_DB_R2_KEY", "db/cncflow.db")


def db_path() -> Path:
    return Path(os.environ.get("CNCFLOW_DB_PATH") or "/data/cncflow.db")


def restore_db() -> bool:
    """启动时从 R2 拉回最近一次检查点。没有对象则返回 False。"""
    if not r2.configured():
        return False
    dest = db_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        payload = r2.get_object(DB_OBJECT_KEY)
    except FileNotFoundError:
        return False
    dest.write_bytes(payload)
    return True


def backup_db() -> bool:
    if not r2.configured():
        return False
    src = db_path()
    if not src.exists():
        return False
    tmp = src.with_suffix(".snapshot")
    source = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    try:
        dest = sqlite3.connect(tmp)
        try:
            source.backup(dest)
        finally:
            dest.close()
    finally:
        source.close()
    r2.put_object(DB_OBJECT_KEY, tmp.read_bytes(), content_type="application/vnd.sqlite3")
    tmp.unlink(missing_ok=True)
    return True


def run_loop(interval: int | None = None) -> None:
    seconds = interval if interval is not None else int(os.environ.get("CNCFLOW_DB_BACKUP_SECONDS", "60"))

    def _flush(_signum=None, _frame=None):
        try:
            backup_db()
        finally:
            if _signum is not None:
                sys.exit(0)

    signal.signal(signal.SIGTERM, _flush)
    signal.signal(signal.SIGINT, _flush)
    while True:
        time.sleep(seconds)
        try:
            backup_db()
        except Exception as exc:  # noqa: BLE001 — 后台循环不能因一次失败退出
            print(f"sqlite R2 backup failed: {exc}", file=sys.stderr)


if __name__ == "__main__":
    run_loop()
