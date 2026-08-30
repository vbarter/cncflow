"""Geometry service wiring: in-process parse-jobs, hole-v4, slot/face stubs."""
from io import BytesIO

import pytest

from cncflow_core.common.db import get_conn
from cncflow_core.geometry import FEATURE_SCHEMA, HOLE_FEATURE_FIELDS
from cncflow_core.geometry.plugins import plugin_names, run_face, run_slot, run_step, run_surface, run_thread
from cncflow_core.geometry.service import parse_step_file
from cncflow_core.ingestion.jobs import get_job


MINIMAL_STEP = (
    b"ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('AUTOMOTIVE_DESIGN'));\n"
    b"ENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;"
)


@pytest.fixture(autouse=True)
def local_storage(monkeypatch, tmp_path):
    monkeypatch.setenv("CNCFLOW_FILE_STORAGE", str(tmp_path / "files"))


def test_plugin_registry_hole_slot_face():
    assert plugin_names() == ["hole", "slot", "face", "thread", "step", "surface"]
    assert FEATURE_SCHEMA == "hole-v4"
    assert list(HOLE_FEATURE_FIELDS) == [
        "diameter_mm", "depth_mm", "hole_type", "position_type", "cut_depth_mm",
    ]
    assert run_slot("unused.step") == []
    assert run_face("unused.step") == []
    assert run_thread("unused.step") == []
    assert run_step("unused.step") == []
    assert run_surface("unused.step") == []
    from cncflow_core.geometry.plugins import list_plugins
    assert list_plugins()[1]["status"] == "active"


def test_parse_step_file_uses_hole_v4_and_stubs(monkeypatch, tmp_path):
    from cncflow_core.ingestion import step_parser

    monkeypatch.setattr(step_parser, "parse_step", lambda path: {
        "geometry": {"volume_cm3": 55.0},
        "features": [{
            "type": "hole", "feature_id": "hole-0", "subtype": "recognized_hole",
            "selected": True, "diameter_mm": 8, "depth_mm": 12,
            "hole_type": "through", "position_type": "垂直", "cut_depth_mm": 14.4,
        }],
        "warnings": [],
    })
    step = tmp_path / "plate.step"
    step.write_bytes(MINIMAL_STEP)
    result = parse_step_file(str(step))
    assert result["parser"] == "geometry-service"
    assert result["parser_version"] == "hole-v4"
    assert result["feature_schema"] == "hole-v4"
    ids = [plugin["id"] for plugin in result["plugins"]]
    assert ids == ["hole", "slot", "face", "thread", "step", "surface"]
    assert result["plugins"][0]["status"] == "active"
    assert result["plugins"][1]["status"] == "active"
    assert result["plugins"][2]["status"] == "active"
    hole = result["features"][0]
    for name in HOLE_FEATURE_FIELDS:
        assert name in hole
    assert hole["diameter_mm"] == 8
    assert hole["depth_mm"] == 12
    assert hole["hole_type"] == "through"
    assert hole["position_type"] == "垂直"
    assert hole["cut_depth_mm"] == 14.4
    types = {feat.get("type") for feat in result["features"]}
    assert "slot" not in types
    assert "face" not in types


def test_process_claimed_emits_geometry_parse_event(client, seeded_db_path, monkeypatch):
    import json
    from cncflow_core.ingestion import worker as worker_mod

    data = {"step_file": (BytesIO(MINIMAL_STEP), "part.step")}
    job_id = client.post("/api/v1/parse-jobs", data=data, content_type="multipart/form-data").get_json()["job_id"]
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
            "parser_version": "hole-v4",
            "feature_schema": "hole-v4",
            "geometry": {"volume_cm3": 1, "bounding_box_mm": {"x": 80, "y": 60, "z": 12}},
            "features": [{
                "type": "hole", "feature_id": "hole-0", "subtype": "recognized_hole",
                "selected": True, "diameter_mm": 8, "depth_mm": 12,
                "hole_type": "through", "position_type": "垂直", "cut_depth_mm": 14.4,
            }],
            "warnings": [],
            "plugins": [
                {"id": "hole", "status": "active", "version": "hole-v4"},
                {"id": "slot", "status": "active", "version": "slot-v1"},
                {"id": "face", "status": "active", "version": "face-v1"},
                {"id": "thread", "status": "active", "version": "thread-v1"},
                {"id": "step", "status": "active", "version": "step-v1"},
                {"id": "surface", "status": "active", "version": "surface-v1"},
            ],
        }

    monkeypatch.setattr(worker_mod, "parse_step_file", fake_parse)
    monkeypatch.setenv("CNCFLOW_PARSE_INLINE", "1")
    worker_mod.process_claimed(conn, claimed)
    job = get_job(conn, job_id)
    conn.close()
    geo_events = [event for event in job["events"] if event["stage"] == "geometry_parse"]
    assert geo_events, job["events"]
    message = geo_events[0]["message"]
    assert "geometry-service" in message
    assert "hole-v4" in message
    assert "hole" in message and "slot" in message and "face" in message
    assert job["stage"] == "review"
    assert job["result"]["parser"] == "geometry-service"
    assert job["result"]["feature_schema"] == "hole-v4"
    ids = [plugin["id"] for plugin in job["result"]["plugins"]]
    assert ids == ["hole", "slot", "face", "thread", "step", "surface"]


def test_service_o8_plate_no_regress():
    cadquery = pytest.importorskip("cadquery")
    import os
    import tempfile

    part = cadquery.Workplane("XY").box(80, 60, 12).faces(">Z").workplane().hole(8)
    fd, path = tempfile.mkstemp(suffix=".step")
    os.close(fd)
    try:
        cadquery.exporters.export(part, path)
        result = parse_step_file(path)
    finally:
        os.unlink(path)
    assert result["feature_schema"] == "hole-v4"
    ids = [plugin["id"] for plugin in result["plugins"]]
    assert ids == ["hole", "slot", "face", "thread", "step", "surface"]
    holes = [feat for feat in result["features"] if feat.get("subtype") == "recognized_hole"]
    assert holes, result["features"]
    hole = holes[0]
    assert hole["diameter_mm"] == pytest.approx(8, abs=0.2)
    assert hole["depth_mm"] == pytest.approx(12, abs=0.6)
    assert hole["hole_type"] == "through"
    assert hole["position_type"] in {"垂直", "侧向"}
    assert hole["cut_depth_mm"] == pytest.approx(14.4, abs=0.3)
    ods = [feat for feat in result["features"] if feat.get("type") == "outer_cylinder"]
    assert not any(feat.get("selected") for feat in ods)
