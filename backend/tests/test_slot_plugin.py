"""槽腔插件：识别最小集 + 手册链 + TK 立铣/倒角。"""
import os
import tempfile

import pytest

from cncflow_core.geometry.plugins import run_slot
from cncflow_core.geometry.service import parse_step_file
from cncflow_core.inquiries.api import _review_and_quote_features


def _export_step(workplane):
    import cadquery as cq
    fd, path = tempfile.mkstemp(suffix=".step")
    os.close(fd)
    cq.exporters.export(workplane, path)
    return path


def test_run_slot_plain_box_has_no_pocket():
    cadquery = pytest.importorskip("cadquery")
    path = _export_step(cadquery.Workplane("XY").box(80, 50, 20))
    try:
        assert run_slot(path) == []
    finally:
        os.unlink(path)


def test_run_slot_hole_only_plate_no_invented_slot():
    cadquery = pytest.importorskip("cadquery")
    part = cadquery.Workplane("XY").box(80, 60, 12).faces(">Z").workplane().hole(8)
    path = _export_step(part)
    try:
        slots = run_slot(path)
        assert slots == [], slots
        result = parse_step_file(path)
        holes = [f for f in result["features"] if f.get("subtype") == "recognized_hole"]
        assert holes
        assert holes[0]["diameter_mm"] == pytest.approx(8, abs=0.2)
        for name in ("diameter_mm", "depth_mm", "hole_type", "position_type", "cut_depth_mm"):
            assert name in holes[0]
    finally:
        os.unlink(path)


def test_run_slot_rectangular_pocket_min_fields():
    cadquery = pytest.importorskip("cadquery")
    part = cadquery.Workplane("XY").box(80, 50, 20).faces(">Z").workplane().rect(40, 12).cutBlind(-8)
    path = _export_step(part)
    try:
        slots = run_slot(path)
        assert slots, "expected a recognized pocket"
        slot = slots[0]
        assert slot["type"] == "pocket"
        assert slot["subtype"] == "recognized_slot"
        assert slot["selected"] is True
        assert slot["pocket_type"] in {"开放", "封闭", "键槽", "T型"}
        assert slot["length"] == pytest.approx(40, abs=1.5)
        assert slot["width"] == pytest.approx(12, abs=1.5)
        assert slot["depth"] == pytest.approx(8, abs=1.5)
        assert slot["corner_radius"] is not None
    finally:
        os.unlink(path)


def test_pocket_chain_rough_clear_chamfer(client):
    resp = client.post("/api/v1/process-plan", json={
        "feature": {
            "type": "pocket", "length": 40, "width": 12, "depth": 8,
            "corner_radius": 1, "pocket_type": "封闭",
        },
        "material": "铝合金",
        "tolerance_it": 10,
        "roughness_ra": 3.2,
    })
    assert resp.status_code == 200
    body = resp.get_json()
    names = [s.get("name") or s.get("process") for s in body["process_chain"]]
    assert "粗铣" in names
    assert "清角" in names
    assert "倒角" in names


def test_pocket_quote_eats_tk_endmill_and_chamfer(client):
    resp = client.post("/api/v1/quotes", json={
        "material": "铝合金",
        "stock_type": "板料",
        "length": 80,
        "width": 50,
        "height": 20,
        "features": [{
            "type": "pocket", "length": 40, "width": 12, "depth": 8,
            "corner_radius": 1, "pocket_type": "封闭",
        }],
    })
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "quoted"
    seq = body["process_sequence"]
    assert seq
    skus = [s.get("sku") for s in seq if s.get("sku")]
    assert skus, seq
    assert any(str(s).startswith("TK-") for s in skus)
    names = [s.get("name") for s in seq]
    assert "粗铣" in names
    assert "倒角" in names
    chamfer = next(s for s in seq if s.get("name") == "倒角" or s.get("process") == "chamfer")
    assert chamfer.get("sku") == "TK-036"
    endmills = {"TK-022", "TK-023", "TK-024", "TK-025", "TK-026"}
    assert any(s in endmills for s in skus), skus


def test_review_includes_selected_pocket():
    review, features = _review_and_quote_features([
        {
            "type": "pocket", "feature_id": "slot-0", "selected": True,
            "pocket_type": "封闭", "length": 40, "width": 12, "depth": 8, "corner_radius": 1,
        },
        {
            "type": "hole", "feature_id": "hole-0", "selected": False,
            "diameter_mm": 8, "depth_mm": 12, "hole_type": "through",
        },
    ], None, 80, 50)
    assert any(f["feature_id"] == "slot-0" and f["selected"] for f in review)
    assert len(features) == 1
    assert features[0]["type"] == "pocket"
    assert features[0]["length"] == 40
    assert features[0]["width"] == 12
    assert features[0]["depth"] == 8
    assert features[0]["corner_radius"] == 1


def test_review_flattens_slot_dimensions():
    review, features = _review_and_quote_features([
        {
            "type": "slot", "feature_id": "slot-1", "selected": True,
            "dimensions": {"length": 40, "width": 12, "depth": 8, "corner_radius": 1, "pocket_type": "键槽"},
        },
    ], None, 80, 50)
    assert features[0]["type"] == "pocket"
    assert features[0]["length"] == 40
    assert features[0]["pocket_type"] == "键槽"
    assert review[0]["selected"] is True


def test_factory_seeds_unchanged(client):
    body = client.get("/api/v1/factory-config").get_json()
    assert len(body["machines"]) == 23
    skus = {t["sku"] for t in body["tools"]}
    assert {f"TK-{i:03d}" for i in range(1, 40)} <= skus
