"""平面插件：识别最小集 + 手册链 + TK 面铣。"""
import os

import pytest

from cncflow_core.geometry.face import _face_position
from cncflow_core.geometry.plugins import run_face
from cncflow_core.geometry.service import parse_step_file
from cncflow_core.inquiries.api import _review_and_quote_features


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
HOLE_D8_STEP = os.path.join(FIXTURES, "plate_hole_d8.step")
OPEN_SLOT_STEP = os.path.join(FIXTURES, "rect_open_slot.step")


class _BBox:
    def __init__(self, xmin, xmax, ymin, ymax, zmin, zmax):
        self.xmin, self.xmax = xmin, xmax
        self.ymin, self.ymax = ymin, ymax
        self.zmin, self.zmax = zmin, zmax


def test_face_position_horizontal_vertical_tilt():
    bbox = _BBox(-40, 40, -30, 30, -6, 6)
    assert _face_position((0, 0, 1), (0, 0, 6), bbox, 2) == "水平"
    assert _face_position((0, 0, -1), (0, 0, -6), bbox, 2) == "水平"
    assert _face_position((1, 0, 0), (40, 0, 0), bbox, 2) == "垂直"
    n = (0.6, 0.0, 0.8)
    mag = (0.6 ** 2 + 0.8 ** 2) ** 0.5
    assert _face_position((0.6 / mag, 0, 0.8 / mag), (0, 0, 4), bbox, 2) == "倾斜"


def test_run_face_plain_box_has_top():
    cadquery = pytest.importorskip("cadquery")
    import tempfile
    part = cadquery.Workplane("XY").box(80, 60, 12)
    fd, path = tempfile.mkstemp(suffix=".step")
    os.close(fd)
    try:
        cadquery.exporters.export(part, path)
        faces = run_face(path)
    finally:
        os.unlink(path)
    assert faces, "expected outer faces"
    tops = [f for f in faces if f["face_position"] == "水平" and f.get("selected")]
    assert tops
    top = tops[0]
    assert top["type"] == "face"
    assert top["subtype"] == "recognized_face"
    assert top["selected"] is True
    assert top["length"] == pytest.approx(80, abs=1.5)
    assert top["width"] == pytest.approx(60, abs=1.5)
    assert set(top["dimensions"]) >= {"length", "width", "face_position"}


def test_run_face_skips_inner_pocket_bottom():
    cadquery = pytest.importorskip("cadquery")
    import tempfile
    part = cadquery.Workplane("XY").box(80, 50, 20).faces(">Z").workplane().rect(40, 12).cutBlind(-8)
    fd, path = tempfile.mkstemp(suffix=".step")
    os.close(fd)
    try:
        cadquery.exporters.export(part, path)
        faces = run_face(path)
        result = parse_step_file(path)
    finally:
        os.unlink(path)
    inner = [f for f in faces if abs((f.get("length") or 0) - 40) < 1.5 and abs((f.get("width") or 0) - 12) < 1.5]
    assert inner == [], inner
    slots = [f for f in result["features"] if f.get("subtype") == "recognized_slot"]
    assert slots, "slot must still be recognized"


def test_d8_plate_face_and_hole_five_fields():
    pytest.importorskip("cadquery")
    if not os.path.exists(HOLE_D8_STEP):
        pytest.skip("missing Ø8 fixture")
    result = parse_step_file(HOLE_D8_STEP)
    holes = [f for f in result["features"] if f.get("subtype") == "recognized_hole"]
    assert holes
    assert holes[0]["diameter_mm"] == pytest.approx(8, abs=0.2)
    for name in ("diameter_mm", "depth_mm", "hole_type", "position_type", "cut_depth_mm"):
        assert name in holes[0]
    faces = [f for f in result["features"] if f.get("subtype") == "recognized_face"]
    assert faces
    top = next(f for f in faces if f.get("selected"))
    assert top["face_position"] == "水平"
    assert top["length"] == pytest.approx(80, abs=2)
    assert top["width"] == pytest.approx(60, abs=2)


def test_open_slot_still_open_no_fillet_holes():
    pytest.importorskip("cadquery")
    if not os.path.exists(OPEN_SLOT_STEP):
        pytest.skip("missing open-slot fixture")
    result = parse_step_file(OPEN_SLOT_STEP)
    slots = [f for f in result["features"] if f.get("subtype") == "recognized_slot"]
    assert slots
    assert slots[0]["pocket_type"] == "开放"
    assert slots[0]["length"] == pytest.approx(40, abs=1.5)
    holes = [f for f in result["features"] if f.get("subtype") == "recognized_hole"]
    fake = [h for h in holes if abs((h.get("diameter_mm") or 0) - 6) < 0.6]
    assert fake == [], fake


def test_face_chain_rough_only_default(client):
    resp = client.post("/api/v1/process-plan", json={
        "feature": {"type": "face", "length": 80, "width": 60, "face_position": "水平"},
        "material": "铝合金",
        "tolerance_it": 10,
        "roughness_ra": 3.2,
    })
    assert resp.status_code == 200
    body = resp.get_json()
    names = [s.get("name") or s.get("process") for s in body["process_chain"]]
    assert "粗铣" in names
    assert "倒角" in names
    assert "半精铣" not in names
    assert "精铣" not in names


def test_face_quote_eats_tk_facemill(client):
    resp = client.post("/api/v1/quotes", json={
        "material": "铝合金",
        "stock_type": "板料",
        "length": 80,
        "width": 60,
        "height": 12,
        "features": [{"type": "face", "length": 80, "width": 60, "face_position": "水平"}],
    })
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "quoted"
    seq = body["process_sequence"]
    assert seq
    skus = [s.get("sku") for s in seq if s.get("sku")]
    assert any(str(s).startswith("TK-") for s in skus), seq
    names = [s.get("name") for s in seq]
    assert "粗铣" in names
    assert "倒角" in names
    assert "TK-028" in skus, skus
    chamfer = next(s for s in seq if s.get("name") == "倒角" or s.get("process") == "chamfer")
    assert chamfer.get("sku") == "TK-036"


def test_face_quote_narrow_uses_027(client):
    resp = client.post("/api/v1/quotes", json={
        "material": "铝合金",
        "stock_type": "板料",
        "length": 80,
        "width": 40,
        "height": 12,
        "features": [{"type": "face", "length": 80, "width": 40, "face_position": "水平"}],
    })
    assert resp.status_code == 200
    skus = [s.get("sku") for s in resp.get_json()["process_sequence"] if s.get("sku")]
    assert "TK-027" in skus, skus
    assert "TK-036" in skus, skus


def test_review_includes_selected_face():
    review, features = _review_and_quote_features([
        {
            "type": "face", "feature_id": "face-0", "selected": True,
            "length": 80, "width": 60, "face_position": "水平",
        },
        {
            "type": "hole", "feature_id": "hole-0", "selected": False,
            "diameter_mm": 8, "depth_mm": 12, "hole_type": "through",
        },
    ], None, 80, 60)
    assert any(f["feature_id"] == "face-0" and f["selected"] for f in review)
    assert len(features) == 1
    assert features[0]["type"] == "face"
    assert features[0]["length"] == 80
    assert features[0]["width"] == 60
    assert features[0]["face_position"] == "水平"


def test_factory_seeds_unchanged(client):
    body = client.get("/api/v1/factory-config").get_json()
    assert len(body["machines"]) == 23
    skus = {t["sku"] for t in body["tools"]}
    assert {f"TK-{i:03d}" for i in range(1, 40)} <= skus
