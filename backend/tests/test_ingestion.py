"""工程文件上传任务、解析队列与确认接口测试。"""
from io import BytesIO
from pathlib import Path

import pytest

from cncflow_core.common.db import get_conn
from cncflow_core.ingestion.jobs import claim_job, finish_job, get_job


MINIMAL_STEP = b"ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('AUTOMOTIVE_DESIGN'));\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;"
MINIMAL_PDF = b"%PDF-1.4\n% ingestion-test\n"


@pytest.fixture(autouse=True)
def local_storage(monkeypatch, tmp_path):
    monkeypatch.setenv("CNCFLOW_FILE_STORAGE", str(tmp_path / "files"))


def upload(client, **files):
    data = {key: (BytesIO(content), name) for key, (content, name) in files.items()}
    return client.post("/api/v1/parse-jobs", data=data, content_type="multipart/form-data")


def test_upload_step_creates_async_job(client, seeded_db_path):
    response = upload(client, step_file=(MINIMAL_STEP, "part.step"))
    assert response.status_code == 202
    body = response.get_json()
    status = client.get(body["status_url"]).get_json()
    assert status["status"] == "queued"
    assert status["files"][0]["detected_type"] == "step"
    conn = get_conn(seeded_db_path)
    claimed = claim_job(conn, "test-worker")
    assert claimed["job_id"] == body["job_id"]
    conn.close()


def test_upload_step_and_pdf(client):
    response = upload(client, step_file=(MINIMAL_STEP, "part.stp"), drawing_file=(MINIMAL_PDF, "part.pdf"))
    assert response.status_code == 202
    status = client.get(response.get_json()["status_url"]).get_json()
    assert {item["detected_type"] for item in status["files"]} == {"step", "pdf"}


def test_rejects_spoofed_extension(client):
    response = upload(client, step_file=(b"not a step file", "fake.step"))
    assert response.status_code == 400
    assert "不匹配" in response.get_json()["error"]


def test_requires_supported_file(client):
    response = client.post("/api/v1/parse-jobs", data={}, content_type="multipart/form-data")
    assert response.status_code == 400


def test_confirmed_hole_runs_existing_pipeline(client, seeded_db_path):
    response = upload(client, step_file=(MINIMAL_STEP, "part.step"))
    job_id = response.get_json()["job_id"]
    conn = get_conn(seeded_db_path)
    finish_job(conn, job_id, {"geometry": {"volume_cm3": 2}, "features": [{
        "feature_id": "hole-1", "type": "hole", "selected": True,
        "dimensions": {"diameter_mm": 10, "depth_mm": 20}, "confidence": .9,
    }], "drawing": None, "warnings": []})
    conn.close()
    confirmed = client.post(f"/api/v1/parse-jobs/{job_id}/confirm", json={
        "holes": [{"feature_id": "hole-1", "diameter_mm": 10, "depth_mm": 20}],
        "material_code": "AL-6061-T6", "tolerance_it": 7, "roughness_ra": 1.6,
    })
    assert confirmed.status_code == 200
    body = confirmed.get_json()
    assert body["status"] == "completed"
    assert body["plans"][0]["plan"]["tool_chain"]


def test_capabilities(client):
    body = client.get("/api/v1/parse-capabilities").get_json()
    assert body["formats"] == ["step", "stp", "pdf"]
    assert body["confirmation_required"] is True


def test_parse_job_binds_part_id(client, seeded_db_path):
    inq = client.post("/api/v1/inquiries", json={"customer": "华科", "project": "夹具A"})
    assert inq.status_code == 201
    pid = client.post(f"/api/v1/inquiries/{inq.get_json()['id']}/parts", json={"name": "底板"}).get_json()["id"]
    data = {"step_file": (BytesIO(MINIMAL_STEP), "part.step"), "part_id": pid}
    response = client.post("/api/v1/parse-jobs", data=data, content_type="multipart/form-data")
    assert response.status_code == 202
    body = response.get_json()
    assert body["part_id"] == pid
    conn = get_conn(seeded_db_path)
    row = conn.execute("SELECT parse_job_id, status FROM parts WHERE id=?", (pid,)).fetchone()
    conn.close()
    assert row["parse_job_id"] == body["job_id"]
    assert row["status"] == "parsing"


def test_retry_failed_job_requeues_same_upload(client, seeded_db_path):
    inq = client.post("/api/v1/inquiries", json={"customer": "华科"}).get_json()
    pid = client.post(
        f"/api/v1/inquiries/{inq['id']}/parts",
        json={"name": "底板"},
    ).get_json()["id"]
    data = {"step_file": (BytesIO(MINIMAL_STEP), "part.step"), "part_id": pid}
    job_id = client.post(
        "/api/v1/parse-jobs",
        data=data,
        content_type="multipart/form-data",
    ).get_json()["job_id"]

    conn = get_conn(seeded_db_path)
    conn.execute(
        "UPDATE parse_jobs SET status='failed',stage='failed',progress=100,"
        "attempts=2,error='STEP bad' WHERE job_id=?",
        (job_id,),
    )
    conn.execute("UPDATE parts SET status='parse_failed' WHERE id=?", (pid,))
    conn.commit()
    conn.close()

    response = client.post(f"/api/v1/parse-jobs/{job_id}/retry")
    assert response.status_code == 202
    body = response.get_json()
    assert body["job_id"] == job_id
    assert body["status"] == "queued"
    assert body["stage"] == "queued"
    assert body["progress"] == 0
    assert body["attempts"] == 0
    assert body["error"] is None
    assert body["files"][0]["original_name"] == "part.step"
    assert body["events"][-1]["message"] == "用户重试解析"

    conn = get_conn(seeded_db_path)
    part_status = conn.execute("SELECT status FROM parts WHERE id=?", (pid,)).fetchone()["status"]
    conn.close()
    assert part_status == "parsing"


def test_retry_rejects_active_job(client):
    job_id = upload(client, step_file=(MINIMAL_STEP, "part.step")).get_json()["job_id"]
    response = client.post(f"/api/v1/parse-jobs/{job_id}/retry")
    assert response.status_code == 409
    assert "无需重试" in response.get_json()["error"]


def test_finish_job_writes_bbox_to_part(client, seeded_db_path):
    inq = client.post("/api/v1/inquiries", json={"customer": "华科"}).get_json()
    pid = client.post(f"/api/v1/inquiries/{inq['id']}/parts", json={"name": "底板"}).get_json()["id"]
    data = {"step_file": (BytesIO(MINIMAL_STEP), "part.step"), "part_id": pid}
    job_id = client.post("/api/v1/parse-jobs", data=data, content_type="multipart/form-data").get_json()["job_id"]
    conn = get_conn(seeded_db_path)
    finish_job(conn, job_id, {
        "geometry": {"volume_cm3": 12.5, "bounding_box_mm": {"x": 80, "y": 40, "z": 12}},
        "features": [{"type": "hole", "selected": True, "dimensions": {"diameter_mm": 6, "depth_mm": 12}}],
        "drawing": None, "warnings": [],
    })
    conn.close()
    part = client.get(f"/api/v1/parts/{pid}").get_json()
    assert part["status"] == "quoted"
    assert part["quote"]["quote"]["amount"] > 0
    assert sorted([part["length"], part["width"], part["height"]], reverse=True) == [80, 40, 12]


def test_isolated_parse_inline(monkeypatch, tmp_path):
    from cncflow_core.ingestion import worker
    monkeypatch.setenv("CNCFLOW_PARSE_INLINE", "1")
    step = tmp_path / "part.step"
    step.write_bytes(MINIMAL_STEP)
    def fake_step(path):
        return {"geometry": {"ok": True}, "features": [], "warnings": [path]}
    monkeypatch.setattr(worker, "parse_step_file", fake_step)
    out = worker.isolated_parse("step", str(step), {})
    assert out["geometry"]["ok"] is True
    assert str(step) in out["warnings"]


def test_process_claimed_geometry_parse_event(client, seeded_db_path, monkeypatch):
    import json
    from cncflow_core.ingestion import worker as worker_mod
    from cncflow_core.ingestion.jobs import get_job

    job_id = upload(client, step_file=(MINIMAL_STEP, "part.step")).get_json()["job_id"]
    conn = get_conn(seeded_db_path)
    conn.execute(
        "UPDATE parse_jobs SET status='running',stage='starting' WHERE job_id=?",
        (job_id,),
    )
    files = [dict(r) for r in conn.execute("SELECT * FROM uploaded_files WHERE job_id=?", (job_id,))]
    options = json.loads(conn.execute("SELECT options_json FROM parse_jobs WHERE job_id=?", (job_id,)).fetchone()[0] or "{}")
    claimed = {"job_id": job_id, "files": files, "options": options}

    def fake_parse(path):
        return {
            "parser": "geometry-service",
            "parser_version": "hole-v3",
            "feature_schema": "hole-v3",
            "geometry": {"volume_cm3": 1},
            "features": [],
            "warnings": [],
            "plugins": [
                {"id": "hole", "status": "active", "version": "hole-v3"},
                {"id": "slot", "status": "stub", "version": None},
                {"id": "face", "status": "stub", "version": None},
            ],
        }

    monkeypatch.setattr(worker_mod, "parse_step_file", fake_parse)
    monkeypatch.setenv("CNCFLOW_PARSE_INLINE", "1")
    worker_mod.process_claimed(conn, claimed)
    job = get_job(conn, job_id)
    conn.close()
    geo = [event for event in job["events"] if event["stage"] == "geometry_parse"]
    assert geo, job["events"]
    message = geo[0]["message"]
    assert "geometry-service" in message
    assert "hole-v3" in message
    assert "hole" in message and "slot" in message and "face" in message
