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


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
OPEN_SLOT_STEP = os.path.join(FIXTURES, "rect_open_slot.step")
HOLE_D8_STEP = os.path.join(FIXTURES, "plate_hole_d8.step")


def test_open_slot_type_beats_keyway_ratio():
    from cncflow_core.geometry.slot import _pocket_type
    assert _pocket_type(40, 10, 3, False, True) == "开放"
    assert _pocket_type(40, 10, 4, False, False) == "键槽"
    assert _pocket_type(40, 30, 4, False, False) == "封闭"


def test_drop_fillet_holes_keeps_real_d8():
    from cncflow_core.geometry.service import _drop_slot_fillet_holes
    features = [
        {"subtype": "recognized_slot", "corner_radius": 3, "length": 40, "width": 10, "depth": 8,
         "location": {"x": 0, "y": 0, "z": 4}},
        {"subtype": "recognized_hole", "diameter_mm": 6.0, "location": {"x": 0, "y": 4, "z": 4}},
        {"subtype": "recognized_hole", "diameter_mm": 6.0, "location": {"x": 0, "y": -4, "z": 4}},
        {"subtype": "recognized_hole", "diameter_mm": 8.0, "location": {"x": -25, "y": 0, "z": 6},
         "hole_type": "through", "position_type": "垂直", "cut_depth_mm": 14.4, "depth_mm": 12},
    ]
    kept = _drop_slot_fillet_holes(features)
    holes = [f for f in kept if f.get("subtype") == "recognized_hole"]
    assert [h["diameter_mm"] for h in holes] == [8.0]


def test_open_slot_not_keyway_no_fillet_holes():
    pytest.importorskip("cadquery")
    if not os.path.exists(OPEN_SLOT_STEP):
        pytest.skip("missing open-slot fixture")
    slots = run_slot(OPEN_SLOT_STEP)
    assert slots, "expected open slot"
    slot = slots[0]
    assert slot["pocket_type"] == "开放", slot
    assert slot["length"] == pytest.approx(40, abs=1.5)
    assert slot["width"] == pytest.approx(10, abs=1.5)
    assert slot["depth"] == pytest.approx(8, abs=1.5)
    assert slot["corner_radius"] == pytest.approx(3, abs=0.6)
    result = parse_step_file(OPEN_SLOT_STEP)
    holes = [f for f in result["features"] if f.get("subtype") == "recognized_hole"]
    fake = [h for h in holes if abs((h.get("diameter_mm") or 0) - 6) < 0.6]
    assert fake == [], fake
    pockets = [f for f in result["features"] if f.get("subtype") == "recognized_slot"]
    assert pockets[0]["pocket_type"] == "开放"
    assert pockets[0]["length"] == pytest.approx(40, abs=1.5)


def test_d8_hole_fixture_five_fields_hold():
    pytest.importorskip("cadquery")
    if not os.path.exists(HOLE_D8_STEP):
        pytest.skip("missing Ø8 fixture")
    result = parse_step_file(HOLE_D8_STEP)
    holes = [f for f in result["features"] if f.get("subtype") == "recognized_hole"]
    assert holes
    assert holes[0]["diameter_mm"] == pytest.approx(8, abs=0.2)
    for name in ("diameter_mm", "depth_mm", "hole_type", "position_type", "cut_depth_mm"):
        assert name in holes[0]
