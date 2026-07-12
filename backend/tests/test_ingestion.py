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
