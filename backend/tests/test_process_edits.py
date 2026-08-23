"""详情第 5 段：工步改序/改参后重算并持久化。"""
from io import BytesIO

import pytest

from cncflow_core.common.db import get_conn
from cncflow_core.ingestion.jobs import finish_job


MINIMAL_STEP = (
    b"ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('AUTOMOTIVE_DESIGN'));\n"
    b"ENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;"
)
MID_PARAMS = ("formula", "n", "f", "cut", "passes", "t_min", "t_max", "status")


def _create_o8_part(client, db_path):
    inquiry = client.post("/api/v1/inquiries", json={"customer": "验收", "project": "Ø8"}).get_json()
    part = client.post(
        f"/api/v1/inquiries/{inquiry['id']}/parts",
        json={"name": "Ø8通孔板", "material": "铝合金"},
    ).get_json()
    upload = client.post(
        "/api/v1/parse-jobs",
        data={"step_file": (BytesIO(MINIMAL_STEP), "plate_hole_d8.step"), "part_id": part["id"]},
        content_type="multipart/form-data",
    ).get_json()
    conn = get_conn(db_path)
    finish_job(conn, upload["job_id"], {
        "geometry": {"volume_cm3": 50.0, "bounding_box_mm": {"x": 80, "y": 60, "z": 12}},
        "features": [
            {
                "type": "hole", "feature_id": "hole-0", "selected": True,
                "diameter_mm": 8, "depth_mm": 12, "hole_type": "through",
                "position_type": "垂直", "cut_depth_mm": 14.4,
            },
            {
                "type": "face", "feature_id": "face-1", "selected": True,
                "length": 80, "width": 60,
            },
        ],
        "drawing": None,
        "warnings": [],
    })
    conn.close()
    return client.get(f"/api/v1/parts/{part['id']}").get_json()


def _sequence(part):
    return part["quote"]["process_sequence"]


def test_reorder_chamfer_before_drill_recalculates_persists_and_resets(client, seeded_db_path):
    part = _create_o8_part(client, seeded_db_path)
    pid = part["id"]
    baseline_amount = part["quote"]["quote"]["amount"]
    assert baseline_amount == pytest.approx(694.4, abs=0.01)
    assert part["quote"]["confidence"] == 90

    sequence = _sequence(part)
    face = next(step for step in sequence if step["process"] == "rough_face")
    drill = next(step for step in sequence if step["process"] == "drill")
    chamfer = next(step for step in sequence if step["process"] == "chamfer")
    response = client.patch(f"/api/v1/parts/{pid}/process-sequence", json={"steps": [
        {"step_id": face["step_id"], "order": 1},
        {"step_id": chamfer["step_id"], "order": 2},
        {"step_id": drill["step_id"], "order": 3},
    ]})
    assert response.status_code == 200, response.get_json()
    edited = response.get_json()
    assert [step["process"] for step in _sequence(edited)] == ["rough_face", "chamfer", "drill"]
    assert edited["quote"]["sequence_adjustment_minutes"] == 0.5
    assert edited["quote"]["quote"]["amount"] != baseline_amount
    assert edited["quote"]["confidence"] == 90
    assert len([item for item in edited["quote"]["deductions"] if item["rule_id"] == "D1-1"]) == 2

    refreshed = client.get(f"/api/v1/parts/{pid}").get_json()
    assert [step["process"] for step in _sequence(refreshed)] == ["rough_face", "chamfer", "drill"]

    reset = client.patch(f"/api/v1/parts/{pid}/process-sequence", json={"reset": True})
    assert reset.status_code == 200, reset.get_json()
    reverted = reset.get_json()
    assert [step["process"] for step in _sequence(reverted)] == ["rough_face", "drill", "chamfer"]
    assert reverted["quote"]["quote"]["amount"] == pytest.approx(694.4, abs=0.01)
    assert reverted["quote"]["confidence"] == 90
    assert reverted["quote"]["process_overrides"] == []


def test_edit_minutes_recalculates_amount_deductions_and_mid_params(client, seeded_db_path):
    part = _create_o8_part(client, seeded_db_path)
    before = part["quote"]["quote"]["amount"]
    drill = next(step for step in _sequence(part) if step["process"] == "drill")

    response = client.patch(
        f"/api/v1/parts/{part['id']}/process-sequence",
        json={"steps": [{"step_id": drill["step_id"], "minutes": 2}]},
    )
    assert response.status_code == 200, response.get_json()
    edited = response.get_json()
    drill_after = next(step for step in _sequence(edited) if step["step_id"] == drill["step_id"])
    assert drill_after["minutes"] == 2
    assert edited["quote"]["quote"]["amount"] != before
    assert drill_after["status"] == "ok"
    assert edited["quote"]["confidence"] == 95
    assert all(key in drill_after for key in MID_PARAMS)
    assert edited["quote"]["validation"]["items"][0]["process"] == "rough_face"
    assert {"material", "fixture"} <= edited["quote"]["ui_cost"].keys()


def test_edit_formula_param_clears_minutes_override_and_recalculates(client, seeded_db_path):
    part = _create_o8_part(client, seeded_db_path)
    drill = next(step for step in _sequence(part) if step["process"] == "drill")
    first = client.patch(
        f"/api/v1/parts/{part['id']}/process-sequence",
        json={"steps": [{"step_id": drill["step_id"], "minutes": 2}]},
    ).get_json()
    amount_with_minutes = first["quote"]["quote"]["amount"]

    response = client.patch(
        f"/api/v1/parts/{part['id']}/process-sequence",
        json={"steps": [{"step_id": drill["step_id"], "f": drill["f"] / 2}]},
    )
    assert response.status_code == 200, response.get_json()
    edited = response.get_json()
    drill_after = next(step for step in _sequence(edited) if step["step_id"] == drill["step_id"])
    override = next(item for item in edited["quote"]["process_overrides"] if item["step_id"] == drill["step_id"])
    assert "minutes" not in override
    assert drill_after["f"] == pytest.approx(drill["f"] / 2)
    assert drill_after["minutes"] != 2
    assert edited["quote"]["quote"]["amount"] != amount_with_minutes
