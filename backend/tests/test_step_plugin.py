"""台阶插件：profile_type / L / H；默认粗铣+倒角吃 TK；孔槽面螺纹不回退。"""
import os

import pytest

from cncflow_core.geometry.plugins import run_step
from cncflow_core.geometry.service import _unselect_step_shoulder_tops, parse_step_file
from cncflow_core.inquiries.api import _review_and_quote_features


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
HOLE_D8_STEP = os.path.join(FIXTURES, "plate_hole_d8.step")
OPEN_SLOT_STEP = os.path.join(FIXTURES, "rect_open_slot.step")
M8_STEP = os.path.join(FIXTURES, "m8x125_through_thread.step")
STEP_H8 = os.path.join(FIXTURES, "rect_step_h8.step")


def test_plain_plate_is_not_a_step():
    pytest.importorskip("cadquery")
    if not os.path.exists(HOLE_D8_STEP):
        pytest.skip("missing Ø8 fixture")
    assert run_step(HOLE_D8_STEP) == []
    result = parse_step_file(HOLE_D8_STEP)
    steps = [f for f in result["features"] if f.get("subtype") == "recognized_step"]
    assert steps == []
    holes = [f for f in result["features"] if f.get("subtype") == "recognized_hole"]
    assert holes
    assert holes[0]["diameter_mm"] == pytest.approx(8, abs=0.2)


def test_open_slot_is_not_a_step():
    pytest.importorskip("cadquery")
    if not os.path.exists(OPEN_SLOT_STEP):
        pytest.skip("missing open-slot fixture")
    result = parse_step_file(OPEN_SLOT_STEP)
    steps = [f for f in result["features"] if f.get("subtype") == "recognized_step"]
    assert steps == []
    slots = [f for f in result["features"] if f.get("subtype") == "recognized_slot"]
    assert slots
    assert slots[0]["pocket_type"] == "开放"


def test_m8_is_not_a_step():
    pytest.importorskip("cadquery")
    if not os.path.exists(M8_STEP):
        pytest.skip("missing M8 fixture")
    result = parse_step_file(M8_STEP)
    steps = [f for f in result["features"] if f.get("subtype") == "recognized_step"]
    assert steps == []
    threads = [f for f in result["features"] if f.get("subtype") == "recognized_thread"]
    assert threads


def test_l_step_emits_profile_lh():
    cadquery = pytest.importorskip("cadquery")
    import tempfile
    plate = cadquery.Workplane("XY").box(80, 60, 12, centered=(True, True, False))
    cut = cadquery.Workplane("XY").center(-20, 0).box(40, 60, 6, centered=(True, True, False)).translate((0, 0, 6))
    body = plate.cut(cut)
    fd, path = tempfile.mkstemp(suffix=".step")
    os.close(fd)
    try:
        cadquery.exporters.export(body, path)
        steps = run_step(path)
        result = parse_step_file(path)
    finally:
        os.unlink(path)
    assert steps, "expected recognized step"
    st = steps[0]
    assert st["profile_type"] == "台阶"
    assert st["length"] == pytest.approx(60, abs=2)
    assert st["height"] == pytest.approx(6, abs=1.2)
    rec = [f for f in result["features"] if f.get("subtype") == "recognized_step"]
    assert rec
    assert rec[0]["selected"] is True
    assert not any(
        f.get("subtype") == "recognized_face" and f.get("selected")
        for f in result["features"]
    )


def test_step_chain_default_rough_chamfer(client):
    resp = client.post("/api/v1/process-plan", json={
        "feature": {"type": "step", "profile_type": "台阶", "length": 60, "height": 6},
        "material": "铝合金",
    })
    assert resp.status_code == 200
    names = [s.get("name") or s.get("process") for s in resp.get_json()["process_chain"]]
    assert "粗铣" in names
    assert "倒角" in names
    assert "精铣" not in names


def test_step_quote_eats_tk(client):
    resp = client.post("/api/v1/quotes", json={
        "material": "铝合金",
        "stock_type": "板料",
        "length": 80,
        "width": 60,
        "height": 12,
        "features": [{"type": "step", "profile_type": "台阶", "length": 60, "height": 6}],
    })
    assert resp.status_code == 200
    seq = resp.get_json()["process_sequence"]
    skus = [s.get("sku") for s in seq if s.get("sku")]
    assert any(str(s).startswith("TK-") for s in skus), seq
    names = [s.get("name") for s in seq]
    assert "粗铣" in names
    assert "倒角" in names
    assert "TK-036" in skus, skus


def test_review_includes_selected_step():
    review, features = _review_and_quote_features([
        {
            "type": "step", "feature_id": "step-0", "selected": True,
            "profile_type": "台阶", "length": 60, "height": 6,
        },
    ], None, 80, 60)
    assert any(f["feature_id"] == "step-0" and f["selected"] for f in review)
    assert features[0]["type"] == "step"
    assert features[0]["length"] == 60
    assert features[0]["height"] == 6


def test_factory_seeds_unchanged(client):
    body = client.get("/api/v1/factory-config").get_json()
    assert len(body["machines"]) == 23
    skus = {t["sku"] for t in body["tools"]}
    assert {f"TK-{i:03d}" for i in range(1, 40)} <= skus


def test_rect_step_h8_sample_emits_lh():
    pytest.importorskip("cadquery")
    if not os.path.exists(STEP_H8):
        pytest.skip("missing rect_step_h8 fixture")
    result = parse_step_file(STEP_H8)
    steps = [f for f in result["features"] if f.get("subtype") == "recognized_step"]
    assert steps, result.get("features")
    st = steps[0]
    assert st["profile_type"] == "台阶"
    assert st["selected"] is True
    assert st["height"] == pytest.approx(8, abs=1.5)
    assert st["length"] == pytest.approx(80, abs=3)


def test_unselect_step_shoulder_drops_80x25_keeps_d8_top():
    plate = [
        {
            "type": "face", "feature_id": "face-0", "subtype": "recognized_face",
            "selected": True, "length": 80, "width": 60, "face_position": "水平",
        },
        {
            "type": "hole", "feature_id": "hole-0", "selected": True, "diameter_mm": 8,
        },
    ]
    kept = _unselect_step_shoulder_tops(plate)
    assert kept[0]["selected"] is True
    step_part = [
        {
            "type": "step", "feature_id": "step-0", "subtype": "recognized_step",
            "selected": True, "profile_type": "台阶", "length": 80, "width": 25, "height": 8,
        },
        {
            "type": "face", "feature_id": "face-0", "subtype": "recognized_face",
            "selected": True, "length": 80, "width": 25, "face_position": "水平",
        },
    ]
    out = _unselect_step_shoulder_tops(step_part)
    by_id = {f["feature_id"]: f for f in out}
    assert by_id["step-0"]["selected"] is True
    assert by_id["face-0"]["selected"] is False


def test_review_rect_step_default_only_step(client):
    review, quoted = _review_and_quote_features([
        {
            "type": "step", "feature_id": "step-0", "selected": True,
            "profile_type": "台阶", "length": 80, "height": 8, "width": 25,
        },
        {
            "type": "face", "feature_id": "face-0", "selected": False,
            "length": 80, "width": 25, "face_position": "水平",
        },
    ], None, 80, 50)
    by_id = {f["feature_id"]: f for f in review}
    assert by_id["step-0"]["selected"] is True
    assert by_id["face-0"]["selected"] is False
    assert [f["type"] for f in quoted] == ["step"]
    resp = client.post("/api/v1/quotes", json={
        "material": "铝合金",
        "stock_type": "板料",
        "length": 80, "width": 50, "height": 16,
        "features": quoted,
    })
    assert resp.status_code == 200
    seq = resp.get_json()["process_sequence"]
    assert len(seq) == 2, seq
    assert [s.get("sku") for s in seq] == ["TK-026", "TK-036"]


def test_review_rect_step_manual_check_shoulder():
    review, quoted = _review_and_quote_features([
        {
            "type": "step", "feature_id": "step-0", "selected": True,
            "profile_type": "台阶", "length": 80, "height": 8, "width": 25,
        },
        {
            "type": "face", "feature_id": "face-0", "selected": False,
            "length": 80, "width": 25, "face_position": "水平",
        },
    ], ["step-0", "face-0"], 80, 50)
    by_id = {f["feature_id"]: f for f in review}
    assert by_id["face-0"]["selected"] is True
    assert by_id["step-0"]["selected"] is True
    assert {f["type"] for f in quoted} == {"step", "face"}


def test_rect_step_h8_default_only_step_selected():
    """78d9038e / rect_step_h8：默认只勾 step-0，肩顶 face 80×25 不自动勾。"""
    pytest.importorskip("cadquery")
    if not os.path.exists(STEP_H8):
        pytest.skip("missing rect_step_h8 fixture")
    result = parse_step_file(STEP_H8)
    selected = [f for f in result["features"] if f.get("selected")]
    assert [f.get("feature_id") for f in selected] == ["step-0"], selected
    faces = [f for f in result["features"] if f.get("subtype") == "recognized_face"]
    shoulder = [
        f for f in faces
        if abs((f.get("length") or 0) - 80) < 2 and abs((f.get("width") or 0) - 25) < 2
    ]
    assert shoulder, faces
    assert all(f.get("selected") is False for f in shoulder)
    review, quoted = _review_and_quote_features(result["features"], None, 80, 50)
    assert any(f["feature_id"] == "step-0" and f["selected"] for f in review)
    assert all(not (f.get("type") == "face" and f.get("selected")) for f in review)
    assert [f["type"] for f in quoted] == ["step"]
