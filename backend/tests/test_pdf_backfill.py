"""2D PDF 可选回填：冻结字段映射、软失败与纯 STEP 回归。"""
import json
from io import BytesIO

from cncflow_core.common.db import get_conn
from cncflow_core.ingestion.jobs import finish_job, get_job
from cncflow_core.ingestion.pdf_parser import map_tuzi_fields


MINIMAL_STEP = (
    b"ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('AUTOMOTIVE_DESIGN'));\n"
    b"ENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;"
)
MINIMAL_PDF = b"%PDF-1.4\n% pdf-backfill-test\n"


def _part_and_job(client, *, with_pdf=True):
    inquiry = client.post(
        "/api/v1/inquiries",
        json={"customer": "PDF 回填测试"},
    ).get_json()
    part = client.post(
        f"/api/v1/inquiries/{inquiry['id']}/parts",
        json={"name": "Ø8底板", "material": "铝合金", "qty": 1},
    ).get_json()
    data = {
        "step_file": (BytesIO(MINIMAL_STEP), "o8.step"),
        "part_id": part["id"],
    }
    if with_pdf:
        data["drawing_file"] = (BytesIO(MINIMAL_PDF), "o8.pdf")
    response = client.post(
        "/api/v1/parse-jobs",
        data=data,
        content_type="multipart/form-data",
    )
    assert response.status_code == 202
    return part["id"], response.get_json()["job_id"]


def _claim_specific(conn, job_id):
    conn.execute(
        "UPDATE parse_jobs SET status='running',stage='starting',attempts=1 "
        "WHERE job_id=?",
        (job_id,),
    )
    conn.commit()
    files = [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM uploaded_files WHERE job_id=?",
            (job_id,),
        )
    ]
    options = json.loads(conn.execute(
        "SELECT options_json FROM parse_jobs WHERE job_id=?",
        (job_id,),
    ).fetchone()["options_json"] or "{}")
    return {"job_id": job_id, "files": files, "options": options}


def test_mock_tuzi_json_maps_frozen_fields():
    mapped = map_tuzi_fields({
        "material": "SUS304",
        "IT": "IT7",
        "Ra": "Ra 1.6",
        "surface_treatment": "钝化",
        "threads": "M6, M8×1.25",
        "quantity": "12件",
    })

    assert mapped == {
        "material_code": "SUS304",
        "tolerance_it": 7,
        "roughness_ra": 1.6,
        "surface_finish": "钝化",
        "thread_specs": ["M6", "M8×1.25"],
        "qty": 12,
    }


def test_finish_job_persists_pdf_fields_without_feature_projection(
    client,
    seeded_db_path,
):
    part_id, job_id = _part_and_job(client)
    result = {
        "geometry": {
            "volume_cm3": 12.5,
            "bounding_box_mm": {"x": 80, "y": 40, "z": 12},
        },
        "features": [{
            "type": "hole",
            "feature_id": "o8",
            "diameter_mm": 8,
            "depth_mm": 12,
            "selected": True,
        }],
        "drawing": {
            "backfill": {
                "material_code": "SUS304",
                "tolerance_it": 7,
                "roughness_ra": 1.6,
                "surface_finish": "钝化",
                "thread_specs": ["M6", "M8×1.25"],
                "qty": 12,
            },
            "tuzi": {"provider": "tu-zi", "called": True, "ok": True},
            "warnings": [],
        },
        "warnings": [],
    }
    conn = get_conn(seeded_db_path)
    finish_job(conn, job_id, result)
    conn.close()

    part = client.get(f"/api/v1/parts/{part_id}").get_json()
    assert part["material_code"] in {"SUS304", "SUS-304", "不锈钢"}
    assert part["tolerance_it"] == 7
    assert part["roughness_ra"] == 1.6
    assert part["surface_finish"] == "钝化"
    assert part["thread_specs"] == ["M6", "M8×1.25"]
    assert part["qty"] == 12
    assert part["batch_size"] == 12
    assert part["pdf_backfill_status"] == "applied"
    assert [feature["type"] for feature in part["parsed_features"]] == ["hole"]


def test_pdf_timeout_does_not_block_step_quote(
    client,
    seeded_db_path,
    monkeypatch,
):
    from cncflow_core.ingestion import worker

    part_id, job_id = _part_and_job(client)
    conn = get_conn(seeded_db_path)
    claimed = _claim_specific(conn, job_id)

    def fake_parse(detected_type, _path, _options):
        if detected_type == "pdf":
            raise TimeoutError("tu-zi timeout")
        return {
            "parser": "geometry-service",
            "geometry": {
                "volume_cm3": 12.5,
                "bounding_box_mm": {"x": 80, "y": 40, "z": 12},
            },
            "features": [{
                "type": "hole",
                "feature_id": "o8",
                "diameter_mm": 8,
                "depth_mm": 12,
                "selected": True,
            }],
            "warnings": [],
        }

    monkeypatch.setattr(worker, "isolated_parse", fake_parse)
    monkeypatch.setattr(worker, "step_to_glb", lambda _path: None)
    worker.process_claimed(conn, claimed)
    job = get_job(conn, job_id)
    conn.close()

    assert job["status"] == "needs_review"
    assert job["result"]["drawing"]["backfill"] == {}
    part = client.get(f"/api/v1/parts/{part_id}").get_json()
    assert part["pdf_backfill_status"] == "failed"
    assert "STEP 报价继续" in part["pdf_backfill_warning"]
    assert part["status"] == "quoted"
    assert part["quote"]["quote"]["amount"] > 0


def test_pure_step_never_enters_pdf_parser(
    client,
    seeded_db_path,
    monkeypatch,
):
    from cncflow_core.ingestion import worker

    part_id, _job_id = _part_and_job(client, with_pdf=False)
    conn = get_conn(seeded_db_path)
    claimed = _claim_specific(conn, _job_id)
    seen = []

    def fake_parse(detected_type, _path, _options):
        seen.append(detected_type)
        return {
            "parser": "geometry-service",
            "geometry": {
                "volume_cm3": 12.5,
                "bounding_box_mm": {"x": 80, "y": 40, "z": 12},
            },
            "features": [],
            "warnings": [],
        }

    monkeypatch.setattr(worker, "isolated_parse", fake_parse)
    monkeypatch.setattr(worker, "step_to_glb", lambda _path: None)
    worker.process_claimed(conn, claimed)
    conn.close()

    part = client.get(f"/api/v1/parts/{part_id}").get_json()
    assert seen == ["step"]
    assert part["pdf_backfill_status"] is None
    assert part["status"] == "quoted"
    assert part["quote"]["quote"]["amount"] > 0


def test_invalid_pdf_values_are_ignored_without_blocking_step_quote(
    client,
    seeded_db_path,
):
    part_id, job_id = _part_and_job(client)
    conn = get_conn(seeded_db_path)
    finish_job(conn, job_id, {
        "geometry": {
            "volume_cm3": 12.5,
            "bounding_box_mm": {"x": 80, "y": 40, "z": 12},
        },
        "features": [],
        "drawing": {
            "backfill": {
                "qty": 10**100,
                "tolerance_it": 99,
                "roughness_ra": float("inf"),
                "thread_specs": ["M8", 123],
            },
            "tuzi": {"provider": "tu-zi", "called": True, "ok": True},
            "warnings": [],
        },
        "warnings": [],
    })
    conn.close()

    part = client.get(f"/api/v1/parts/{part_id}").get_json()
    assert part["pdf_backfill_status"] == "failed"
    assert part["qty"] == 1
    assert part["thread_specs"] == []
    assert part["status"] == "quoted"
    assert part["quote"]["quote"]["amount"] > 0


def test_internal_thread_json_cannot_be_patched(client):
    inquiry = client.post("/api/v1/inquiries", json={"customer": "线程字段"}).get_json()
    part = client.post(
        f"/api/v1/inquiries/{inquiry['id']}/parts",
        json={"name": "底板", "length": 80, "width": 40, "height": 12},
    ).get_json()

    response = client.patch(
        f"/api/v1/parts/{part['id']}",
        json={"thread_specs_json": "invalid"},
    )

    assert response.status_code == 200
    assert response.get_json()["thread_specs"] == []
