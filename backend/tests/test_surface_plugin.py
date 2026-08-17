"""曲面插件：surface_type / R / position；R>1 不强制高风险；工时默认可 0。"""
import os

import pytest

from cncflow_core.geometry.plugins import run_surface
from cncflow_core.geometry.service import parse_step_file
from cncflow_core.inquiries.api import _review_and_quote_features


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
HOLE_D8_STEP = os.path.join(FIXTURES, "plate_hole_d8.step")
OPEN_SLOT_STEP = os.path.join(FIXTURES, "rect_open_slot.step")
M8_STEP = os.path.join(FIXTURES, "m8x125_through_thread.step")
STEP_H8 = os.path.join(FIXTURES, "rect_step_h8.step")
CONVEX = os.path.join(FIXTURES, "convex_r20.step")


def test_plain_plate_is_not_a_surface():
    pytest.importorskip("cadquery")
    if not os.path.exists(HOLE_D8_STEP):
        pytest.skip("missing Ø8 fixture")
    result = parse_step_file(HOLE_D8_STEP)
    surfaces = [f for f in result["features"] if f.get("subtype") == "recognized_surface"]
    assert surfaces == []
    holes = [f for f in result["features"] if f.get("subtype") == "recognized_hole"]
    assert holes
    assert holes[0]["diameter_mm"] == pytest.approx(8, abs=0.2)


def test_open_slot_is_not_a_surface():
    pytest.importorskip("cadquery")
    if not os.path.exists(OPEN_SLOT_STEP):
        pytest.skip("missing open-slot fixture")
    result = parse_step_file(OPEN_SLOT_STEP)
    surfaces = [f for f in result["features"] if f.get("subtype") == "recognized_surface"]
    assert surfaces == []
    slots = [f for f in result["features"] if f.get("subtype") == "recognized_slot"]
    assert slots
    assert slots[0]["pocket_type"] == "开放"


def test_m8_is_not_a_surface():
    pytest.importorskip("cadquery")
    if not os.path.exists(M8_STEP):
        pytest.skip("missing M8 fixture")
    result = parse_step_file(M8_STEP)
    surfaces = [f for f in result["features"] if f.get("subtype") == "recognized_surface"]
    assert surfaces == []
    threads = [f for f in result["features"] if f.get("subtype") == "recognized_thread"]
    assert threads


def test_step_is_not_a_surface():
    pytest.importorskip("cadquery")
    if not os.path.exists(STEP_H8):
        pytest.skip("missing rect_step_h8 fixture")
    result = parse_step_file(STEP_H8)
    surfaces = [f for f in result["features"] if f.get("subtype") == "recognized_surface"]
    assert surfaces == []
    steps = [f for f in result["features"] if f.get("subtype") == "recognized_step"]
    assert steps


def test_fillet_is_not_a_surface():
    cadquery = pytest.importorskip("cadquery")
    import tempfile
    part = cadquery.Workplane("XY").box(40, 30, 10).edges("|Z").fillet(2)
    fd, path = tempfile.mkstemp(suffix=".step")
    os.close(fd)
    try:
        cadquery.exporters.export(part, path)
        surfaces = run_surface(path)
        result = parse_step_file(path)
    finally:
        os.unlink(path)
    assert surfaces == []
    rec = [f for f in result["features"] if f.get("subtype") == "recognized_surface"]
    assert rec == []


def test_convex_r20_emits_type_and_r():
    pytest.importorskip("cadquery")
    if not os.path.exists(CONVEX):
        pytest.skip("missing convex_r20 fixture")
    result = parse_step_file(CONVEX)
    surfaces = [f for f in result["features"] if f.get("subtype") == "recognized_surface"]
    assert surfaces, result.get("features")
    surf = surfaces[0]
    assert surf["surface_type"] == "凸面"
    assert surf["selected"] is True
    assert surf["curvature_radius"] == pytest.approx(20, abs=1.5)


def test_surface_risk_low_when_r_gt_1(client):
    resp = client.post("/api/v1/process-plan", json={
        "feature": {"type": "surface", "surface_type": "凸面", "curvature_radius": 20},
        "material": "铝合金",
    })
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["risk_level"] == "低"
    assert "需补五轴工时" not in (body.get("risk_tags") or [])
    assert body["manual_hours"] == 0
    assert body["process_chain"] == []


def test_surface_risk_high_when_freeform_or_small_r(client):
    resp = client.post("/api/v1/process-plan", json={
        "feature": {"type": "surface", "surface_type": "自由曲面", "curvature_radius": 8},
        "material": "铝合金",
    })
    assert resp.status_code == 200
    assert "需补五轴工时" in resp.get_json()["risk_tags"]
    resp = client.post("/api/v1/process-plan", json={
        "feature": {"type": "surface", "surface_type": "凸面", "curvature_radius": 0.6},
        "material": "铝合金",
    })
    assert resp.status_code == 200
    assert "需补五轴工时" in resp.get_json()["risk_tags"]


def test_surface_quote_hours_default_zero_and_patch(client):
    payload = {
        "material": "铝合金",
        "stock_type": "板料",
        "length": 60,
        "width": 40,
        "height": 10,
        "features": [{"type": "surface", "surface_type": "凸面", "curvature_radius": 20}],
    }
    resp = client.post("/api/v1/quotes", json=payload)
    assert resp.status_code == 200
    body = resp.get_json()
    assert "需补五轴工时" not in (body.get("risk_tags") or [])
    names = [s.get("name") for s in body.get("process_sequence") or []]
    assert "倒角" not in names
    payload["features"] = [{
        "type": "surface", "surface_type": "凸面", "curvature_radius": 20, "manual_hours": 0.5,
    }]
    patched = client.post("/api/v1/quotes", json=payload)
    assert patched.status_code == 200
    assert patched.get_json()["quote"] != body["quote"] or patched.get_json() != body


def test_review_includes_selected_surface():
    review, features = _review_and_quote_features([
        {
            "type": "surface", "feature_id": "surface-0", "selected": True,
            "surface_type": "凸面", "curvature_radius": 20, "position": "顶面",
        },
    ], None, 60, 40)
    assert any(f["feature_id"] == "surface-0" and f["selected"] for f in review)
    assert features[0]["type"] == "surface"
    assert features[0]["surface_type"] == "凸面"
    assert features[0]["curvature_radius"] == 20
    assert features[0]["manual_hours"] == 0


def test_factory_seeds_unchanged(client):
    body = client.get("/api/v1/factory-config").get_json()
    assert len(body["machines"]) == 23
    skus = {t["sku"] for t in body["tools"]}
    assert {f"TK-{i:03d}" for i in range(1, 40)} <= skus
