"""R2 存储 URI、物化本地缓存、SQLite 检查点。"""
from io import BytesIO
from pathlib import Path

from werkzeug.datastructures import FileStorage

from cncflow_core.common import persist
from cncflow_core.ingestion import r2, storage


MINIMAL_STEP = b"ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('AUTOMOTIVE_DESIGN'));\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;"


def _r2_env(monkeypatch, objects: dict):
    monkeypatch.setenv("CNCFLOW_R2_ACCOUNT_ID", "acct")
    monkeypatch.setenv("CNCFLOW_R2_ACCESS_KEY_ID", "key")
    monkeypatch.setenv("CNCFLOW_R2_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("CNCFLOW_R2_BUCKET", "cncflow-files")

    def put_object(key, body, content_type="application/octet-stream"):
        objects[key] = body

    def get_object(key):
        if key not in objects:
            raise FileNotFoundError(key)
        return objects[key]

    monkeypatch.setattr(r2, "put_object", put_object)
    monkeypatch.setattr(r2, "get_object", get_object)


def test_store_upload_uses_r2_uri(monkeypatch, tmp_path):
    objects = {}
    _r2_env(monkeypatch, objects)
    monkeypatch.setenv("CNCFLOW_FILE_STORAGE", str(tmp_path / "files"))
    upload = FileStorage(stream=BytesIO(MINIMAL_STEP), filename="part.stp", content_type="application/octet-stream")
    stored = storage.store_upload(upload, "job1", "step")
    assert stored["storage_path"].startswith("r2://cncflow-files/")
    assert stored["sha256"] in stored["storage_path"]
    assert objects[f"{stored['sha256'][:2]}/{stored['sha256']}"] == MINIMAL_STEP


def test_materialize_downloads_missing_cache(monkeypatch, tmp_path):
    objects = {"ab/abcd": b"payload"}
    _r2_env(monkeypatch, objects)
    monkeypatch.setenv("CNCFLOW_FILE_STORAGE", str(tmp_path / "files"))
    path = storage.materialize("r2://cncflow-files/ab/abcd")
    assert Path(path).read_bytes() == b"payload"
    assert storage.materialize("r2://cncflow-files/ab/abcd") == path


def test_sqlite_checkpoint_roundtrip(monkeypatch, tmp_path):
    objects = {}
    _r2_env(monkeypatch, objects)
    db = tmp_path / "cncflow.db"
    monkeypatch.setenv("CNCFLOW_DB_PATH", str(db))
    import sqlite3
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE ping(x INTEGER)")
    conn.execute("INSERT INTO ping VALUES (7)")
    conn.commit()
    conn.close()
    assert persist.backup_db() is True
    db.unlink()
    assert persist.restore_db() is True
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT x FROM ping").fetchone()[0] == 7
    conn.close()


def test_local_path_unchanged_without_r2(monkeypatch, tmp_path):
    monkeypatch.setenv("CNCFLOW_FILE_STORAGE", str(tmp_path / "files"))
    for key in ("CNCFLOW_R2_ACCOUNT_ID", "CNCFLOW_R2_ACCESS_KEY_ID", "CNCFLOW_R2_SECRET_ACCESS_KEY", "CNCFLOW_R2_BUCKET"):
        monkeypatch.delenv(key, raising=False)
    upload = FileStorage(stream=BytesIO(MINIMAL_STEP), filename="part.stp")
    stored = storage.store_upload(upload, "job2", "step")
    assert stored["storage_path"].startswith(str(tmp_path))
    assert not stored["storage_path"].startswith("r2://")


def test_materialize_adds_step_suffix(monkeypatch, tmp_path):
    monkeypatch.setenv("CNCFLOW_FILE_STORAGE", str(tmp_path / "files"))
    for key in ("CNCFLOW_R2_ACCOUNT_ID", "CNCFLOW_R2_ACCESS_KEY_ID", "CNCFLOW_R2_SECRET_ACCESS_KEY", "CNCFLOW_R2_BUCKET"):
        monkeypatch.delenv(key, raising=False)
    dest = tmp_path / "files" / "ab" / ("a" * 64)
    dest.parent.mkdir(parents=True)
    dest.write_bytes(MINIMAL_STEP)
    path = storage.materialize(str(dest), suffix=".step")
    assert path.endswith(".step")
    assert Path(path).read_bytes() == MINIMAL_STEP


def test_materialize_local_miss_falls_back_to_r2(monkeypatch, tmp_path):
    digest = "ab" + "cd" * 31
    objects = {f"{digest[:2]}/{digest}": MINIMAL_STEP}
    _r2_env(monkeypatch, objects)
    monkeypatch.setenv("CNCFLOW_FILE_STORAGE", str(tmp_path / "files"))
    missing = tmp_path / "files" / digest[:2] / digest
    path = storage.materialize(str(missing), suffix=".step")
    assert Path(path).read_bytes() == MINIMAL_STEP
    assert path.endswith(".step")


def test_materialize_missing_without_r2_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("CNCFLOW_FILE_STORAGE", str(tmp_path / "files"))
    for key in ("CNCFLOW_R2_ACCOUNT_ID", "CNCFLOW_R2_ACCESS_KEY_ID", "CNCFLOW_R2_SECRET_ACCESS_KEY", "CNCFLOW_R2_BUCKET"):
        monkeypatch.delenv(key, raising=False)
    try:
        storage.materialize(str(tmp_path / "nope"))
    except FileNotFoundError as exc:
        assert "解析文件不存在" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError")


def test_backup_records_last_ok(monkeypatch, tmp_path):
    objects = {}
    _r2_env(monkeypatch, objects)
    db = tmp_path / "cncflow.db"
    monkeypatch.setenv("CNCFLOW_DB_PATH", str(db))
    assert persist.last_backup_ok() is None
    assert persist.backup_db() is False
    assert persist.last_backup_ok() is False
    import sqlite3
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE ping(x INTEGER)")
    conn.commit()
    conn.close()
    assert persist.backup_db() is True
    assert persist.last_backup_ok() is True
    snap = persist.health_snapshot()
    assert snap["r2"] is True
    assert snap["db_exists"] is True
    assert snap["last_backup_ok"] is True


def test_run_loop_backups_immediately(monkeypatch):
    calls = []

    def fake_backup():
        calls.append("backup")
        return True

    monkeypatch.setattr(persist, "backup_db", fake_backup)

    def boom(_seconds):
        raise SystemExit

    monkeypatch.setattr(persist.time, "sleep", boom)
    try:
        persist.run_loop(interval=60)
    except SystemExit:
        pass
    assert calls == ["backup"]


def test_finish_and_fail_job_checkpoint(monkeypatch, tmp_path):
    from cncflow_core.common.db import get_conn, init_schema
    from cncflow_core.ingestion.jobs import create_job, fail_job, finish_job, get_job

    called = []
    monkeypatch.setattr(persist, "try_backup_db", lambda: called.append("ok") or True)
    db = tmp_path / "jobs.db"
    conn = get_conn(db)
    init_schema(conn)
    job_id = create_job(conn, [], {})
    finish_job(conn, job_id, {"geometry": None, "features": [], "warnings": []})
    assert called == ["ok"]
    assert get_job(conn, job_id)["status"] == "needs_review"

    called.clear()
    job_id2 = create_job(conn, [], {})
    fail_job(conn, job_id2, "parse exploded")
    assert called == ["ok"]
    conn.close()


def test_finish_job_survives_backup_error(monkeypatch, tmp_path):
    from cncflow_core.common.db import get_conn, init_schema
    from cncflow_core.ingestion.jobs import create_job, finish_job, get_job

    def boom():
        raise RuntimeError("r2 down")

    monkeypatch.setattr(persist, "backup_db", boom)
    db = tmp_path / "jobs.db"
    conn = get_conn(db)
    init_schema(conn)
    job_id = create_job(conn, [], {})
    finish_job(conn, job_id, {"geometry": None, "features": [], "warnings": []})
    assert get_job(conn, job_id)["status"] == "needs_review"
    conn.close()

