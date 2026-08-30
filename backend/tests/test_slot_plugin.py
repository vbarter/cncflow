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
NUC_PLATE_STEP = os.path.join(FIXTURES, "nuc_plate_windows.step")


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


def test_nuc_windows_do_not_steal_mounting_hole_radius():
    pytest.importorskip("cadquery")
    slots = run_slot(NUC_PLATE_STEP)
    radii = [round(slot.get("corner_radius") or 0, 3) for slot in slots]
    assert 1.25 not in radii, radii

    result = parse_step_file(NUC_PLATE_STEP)
    holes = [
        feature
        for feature in result["features"]
        if feature.get("subtype") == "recognized_hole"
    ]
    assert len(holes) == 18, [feature.get("diameter_mm") for feature in holes]
    assert all(feature["selected"] is True for feature in holes)
    assert all(
        feature["diameter_mm"] == pytest.approx(2.5, abs=0.15)
        for feature in holes
    )


def test_nuc_windows_are_not_slots():
    """Analysis Situs: over-width enclosed windows are contours, not slots.

    NUC fixture has four one-sided window pockets (W=16–28, H≈1.75 on a 3.5
    plate). Those are not mill slots and must not default-select.
    """
    pytest.importorskip("cadquery")
    slots = run_slot(NUC_PLATE_STEP)
    assert slots == [], [
        (s.get("pocket_type"), s.get("length"), s.get("width"), s.get("depth"))
        for s in slots
    ]
    result = parse_step_file(NUC_PLATE_STEP)
    pockets = [f for f in result["features"] if f.get("subtype") == "recognized_slot"]
    assert pockets == [], [
        (f.get("feature_id"), f.get("pocket_type"), f.get("width"), f.get("depth"))
        for f in pockets
    ]
    holes = [f for f in result["features"] if f.get("subtype") == "recognized_hole"]
    assert len(holes) == 18
    assert all(f["selected"] is True for f in holes)


def test_sharp_through_window_is_not_a_slot():
    """Through-cut window with no floor: wall-as-bottom swaps W↔H. Not a slot."""
    cadquery = pytest.importorskip("cadquery")
    part = (
        cadquery.Workplane("XY").box(120, 80, 3.5)
        .faces(">Z").workplane().rect(55, 30).cutThruAll()
    )
    path = _export_step(part)
    try:
        slots = run_slot(path)
        assert slots == [], [
            (s.get("length"), s.get("width"), s.get("depth"), s.get("pocket_type"))
            for s in slots
        ]
        result = parse_step_file(path)
        pockets = [f for f in result["features"] if f.get("subtype") == "recognized_slot"]
        assert pockets == [], pockets
        holes = [f for f in result["features"] if f.get("subtype") == "recognized_hole"]
        assert holes == []
    finally:
        os.unlink(path)


def test_wide_closed_pocket_stays_closed_not_keyway():
    cadquery = pytest.importorskip("cadquery")
    part = (
        cadquery.Workplane("XY").box(80, 60, 20, centered=(True, True, False))
        .faces(">Z").workplane().rect(40, 30).cutBlind(-8)
    )
    path = _export_step(part)
    try:
        slots = run_slot(path)
        assert slots, "wide enclosed pocket is still a pocket"
        assert slots[0]["pocket_type"] == "封闭"
        assert slots[0]["length"] == pytest.approx(40, abs=1.5)
        assert slots[0]["width"] == pytest.approx(30, abs=1.5)
        assert slots[0]["depth"] == pytest.approx(8, abs=1.5)
        result = parse_step_file(path)
        steps = [f for f in result["features"] if f.get("subtype") == "recognized_step"]
        assert steps == [], "slot absorbs the matching step shoulder"
        pockets = [f for f in result["features"] if f.get("subtype") == "recognized_slot"]
        assert len(pockets) == 1
        assert pockets[0]["pocket_type"] == "封闭"
    finally:
        os.unlink(path)


def test_step_plus_hole_keeps_hole_and_step():
    """Hole rim on a step floor is an inner wire, not a slot corner (D=2R steal)."""
    cadquery = pytest.importorskip("cadquery")
    plate = cadquery.Workplane("XY").box(80, 60, 12, centered=(True, True, False))
    cut = (
        cadquery.Workplane("XY").center(-20, 0)
        .box(40, 60, 6, centered=(True, True, False))
        .translate((0, 0, 6))
    )
    part = plate.cut(cut).faces(">Z").workplane().hole(8)
    path = _export_step(part)
    try:
        result = parse_step_file(path)
        holes = [f for f in result["features"] if f.get("subtype") == "recognized_hole"]
        assert holes, "Ø8 on the high face must survive"
        assert holes[0]["diameter_mm"] == pytest.approx(8, abs=0.2)
        assert holes[0]["selected"] is True
        steps = [f for f in result["features"] if f.get("subtype") == "recognized_step"]
        assert steps, "2-level step must survive"
        assert steps[0]["selected"] is True
        slots = [f for f in result["features"] if f.get("subtype") == "recognized_slot"]
        stolen = [
            s for s in slots
            if abs((s.get("corner_radius") or 0) - 4) < 0.6
        ]
        assert stolen == [], stolen
        surfaces = [f for f in result["features"] if f.get("subtype") == "recognized_surface"]
        hole_walls = [
            s for s in surfaces
            if s.get("curvature_radius") and abs(s["curvature_radius"] - 4) < 0.6
        ]
        assert hole_walls == [], hole_walls
    finally:
        os.unlink(path)


def test_window_not_slot_predicate():
    from cncflow_core.geometry.slot import _is_window_not_slot

    class BBox:
        def __init__(self, x, y, z):
            self.xlen, self.ylen, self.zlen = x, y, z

    nuc = BBox(160, 100, 3.5)
    bottom_z = {"n": (0.0, 0.0, 1.0)}
    walls4 = [0, 1, 2, 3]
    assert _is_window_not_slot(bottom_z, walls4, 42, 28, 1.75, nuc, False) is True
    assert _is_window_not_slot(bottom_z, walls4, 40, 12, 8, BBox(80, 50, 20), False) is False
    sharp = BBox(120, 80, 3.5)
    bottom_x = {"n": (1.0, 0.0, 0.0)}
    assert _is_window_not_slot(bottom_x, [0, 1, 2], 55, 3.5, 30, sharp, True) is True
    assert _is_window_not_slot(bottom_z, [0, 1], 40, 10, 8, BBox(80, 60, 12), True) is False


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
