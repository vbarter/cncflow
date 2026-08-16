"""Geometry feature service: plugin registry, HTTP parse, worker events."""
from io import BytesIO

import pytest

from cncflow_core.common.db import get_conn
from cncflow_core.geometry.plugins import (
    FEATURE_SCHEMA,
    HOLE_PLUGIN_VERSION,
    PLUGINS,
    plugin_names,
    plugin_summaries,
    recognize_faces,
    recognize_slots,
)
from cncflow_core.ingestion.jobs import claim_job, get_job


MINIMAL_STEP = (
    b"ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('AUTOMOTIVE_DESIGN'));\n"
    b"ENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;"
)


@pytest.fixture(autouse=True)
def local_storage(monkeypatch, tmp_path):
    monkeypatch.setenv("CNCFLOW_FILE_STORAGE", str(tmp_path / "files"))


def test_plugin_registry_hole_slot_face():
    assert plugin_names() == ["hole", "slot", "face"]
    assert FEATURE_SCHEMA == "hole-v3"
    assert HOLE_PLUGIN_VERSION == "hole-v3"
    assert recognize_slots("unused.step") == []
    assert recognize_faces("unused.step") == []
    by_name = {plugin["name"]: plugin for plugin in PLUGINS}
    assert by_name["hole"]["accepted"] is True
    assert by_name["hole"]["version"] == "hole-v3"
    assert by_name["slot"]["accepted"] is False
    assert by_name["face"]["accepted"] is False
    summaries = plugin_summaries()
    assert [item["name"] for item in summaries] == ["hole", "slot", "face"]


def test_hole_plugin_delegates_to_parse_step(monkeypatch):
    from cncflow_core.ingestion import step_parser
    from cncflow_core.geometry.plugins import recognize_holes

    called = {}

    def fake_parse(path):
        called["path"] = path
        return {
            "parser": "cadquery-occ",
            "parser_version": "test",
            "feature_schema": "hole-v3",
            "geometry": {"volume_cm3": 1},
            "features": [{"type": "hole", "subtype": "recognized_hole"}],
            "warnings": [],
        }

    monkeypatch.setattr(step_parser, "parse_step", fake_parse)
    out = recognize_holes("/tmp/plate.step")
    assert called["path"] == "/tmp/plate.step"
    assert out["features"][0]["subtype"] == "recognized_hole"


def test_parse_step_file_merges_plugins(monkeypatch, tmp_path):
    from cncflow_core.ingestion import step_parser
    from cncflow_core.geometry.service import parse_step_file

    monkeypatch.setattr(step_parser, "parse_step", lambda path: {
        "parser": "cadquery-occ",
        "parser_version": "2.5",
        "feature_schema": "hole-v3",
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
    assert result["parser_version"] == "hole-v3"
    assert result["feature_schema"] == "hole-v3"
    names = [plugin["name"] for plugin in result["plugins"]]
    assert names == ["hole", "slot", "face"]
    by_name = {plugin["name"]: plugin for plugin in result["plugins"]}
    assert by_name["hole"]["accepted"] is True
    assert by_name["hole"]["feature_count"] == 1
    assert by_name["slot"]["accepted"] is False
    assert by_name["slot"]["feature_count"] == 0
    assert by_name["face"]["accepted"] is False
    assert by_name["face"]["feature_count"] == 0
    hole = result["features"][0]
    assert hole["diameter_mm"] == 8
    assert hole["depth_mm"] == 12
    assert hole["hole_type"] == "through"
    assert hole["position_type"] == "垂直"
    assert hole["cut_depth_mm"] == 14.4


def _plugin_names(body):
    plugins = body.get("plugins") or []
    return [item["name"] if isinstance(item, dict) else item for item in plugins]


def test_geometry_parse_api_plugins_no_500(client):
    data = {"step_file": (BytesIO(MINIMAL_STEP), "part.step")}
    resp = client.post("/api/v1/geometry/parse", data=data, content_type="multipart/form-data")
    assert resp.status_code != 500, resp.get_data(as_text=True)
    body = resp.get_json()
    assert _plugin_names(body) == ["hole", "slot", "face"]
    assert body.get("feature_schema") == "hole-v3"
    by_name = {item["name"]: item for item in body["plugins"] if isinstance(item, dict)}
    assert by_name["slot"]["accepted"] is False
    assert by_name["face"]["accepted"] is False
    if "feature_count" in by_name["slot"]:
        assert by_name["slot"]["feature_count"] == 0
        assert by_name["face"]["feature_count"] == 0


def test_geometry_parse_api_missing_file(client):
    resp = client.post("/api/v1/geometry/parse", data={}, content_type="multipart/form-data")
    assert resp.status_code == 400
    body = resp.get_json()
    assert _plugin_names(body) == ["hole", "slot", "face"]


def test_geometry_parse_rejects_spoofed_extension(client):
    resp = client.post(
        "/api/v1/geometry/parse",
        data={"step_file": (BytesIO(b"not a step file"), "fake.step")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    assert resp.status_code != 500
    assert "不匹配" in resp.get_json()["error"]


def test_process_claimed_emits_geometry_parse_event(client, seeded_db_path, monkeypatch):
    from cncflow_core.ingestion import worker as worker_mod

    data = {"step_file": (BytesIO(MINIMAL_STEP), "part.step")}
    job_id = client.post("/api/v1/parse-jobs", data=data, content_type="multipart/form-data").get_json()["job_id"]
    conn = get_conn(seeded_db_path)
    claimed = claim_job(conn, "test-worker")

    def fake_parse(path):
        return {
            "parser": "geometry-service",
            "parser_version": "hole-v3",
            "feature_schema": "hole-v3",
            "geometry": {"volume_cm3": 1, "bounding_box_mm": {"x": 80, "y": 60, "z": 12}},
            "features": [{
                "type": "hole", "feature_id": "hole-0", "subtype": "recognized_hole",
                "selected": True, "diameter_mm": 8, "depth_mm": 12,
            }],
            "warnings": [],
            "plugins": [
                {"name": "hole", "version": "hole-v3", "accepted": True, "feature_count": 1},
                {"name": "slot", "version": "stub", "accepted": False, "feature_count": 0},
                {"name": "face", "version": "stub", "accepted": False, "feature_count": 0},
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
    assert "hole-v3" in message
    assert "hole" in message and "slot" in message and "face" in message
    assert job["stage"] == "review"
    assert job["result"]["parser"] == "geometry-service"
    assert job["result"]["feature_schema"] == "hole-v3"
    names = [plugin["name"] for plugin in job["result"]["plugins"]]
    assert names == ["hole", "slot", "face"]


def test_service_o8_plate_no_regress():
    cadquery = pytest.importorskip("cadquery")
    import os
    import tempfile

    from cncflow_core.geometry.service import parse_step_file

    part = cadquery.Workplane("XY").box(80, 60, 12).faces(">Z").workplane().hole(8)
    fd, path = tempfile.mkstemp(suffix=".step")
    os.close(fd)
    try:
        cadquery.exporters.export(part, path)
        result = parse_step_file(path)
    finally:
        os.unlink(path)
    assert result["feature_schema"] == "hole-v3"
    names = [plugin["name"] for plugin in result["plugins"]]
    assert names == ["hole", "slot", "face"]
    by_name = {plugin["name"]: plugin for plugin in result["plugins"]}
    assert by_name["slot"]["feature_count"] == 0
    assert by_name["face"]["feature_count"] == 0
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
