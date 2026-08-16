"""螺纹插件：有螺旋才出 D/P/L；没有当孔；吃 TK 丝锥/螺纹铣。"""
import os

import pytest

from cncflow_core.geometry.plugins import run_thread
from cncflow_core.geometry.service import parse_step_file
from cncflow_core.geometry.thread import infer_pitch, major_from_minor
from cncflow_core.inquiries.api import _review_and_quote_features


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
HOLE_D8_STEP = os.path.join(FIXTURES, "plate_hole_d8.step")
OPEN_SLOT_STEP = os.path.join(FIXTURES, "rect_open_slot.step")
M8_STEP = os.path.join(FIXTURES, "m8x125_through_thread.step")


def test_infer_pitch_metric():
    assert infer_pitch(8) == 1.25
    assert infer_pitch(10) == 1.5
    assert infer_pitch(3.3) is None


def test_major_from_minor_m8():
    assert major_from_minor(6.8) == (8.0, 1.25)
    assert major_from_minor(8.0) == (None, None)
    assert major_from_minor(6.0) == (None, None)  # 开口槽 R3 圆柱不是底孔
    assert major_from_minor(3.3) == (4.0, 0.7)  # 底孔碰巧是 M4，无牙面不当螺纹


def test_m8_sample_emits_dpl():
    pytest.importorskip("cadquery")
    if not os.path.exists(M8_STEP):
        pytest.skip("missing M8 fixture")
    threads = run_thread(M8_STEP)
    assert threads, "expected recognized thread"
    th = threads[0]
    assert th["diameter_mm"] == pytest.approx(8, abs=0.3)
    assert th["pitch"] == pytest.approx(1.25, abs=0.05)
    assert th["thread_length"] == pytest.approx(12, abs=1.5)
    result = parse_step_file(M8_STEP)
    rec = [f for f in result["features"] if f.get("subtype") == "recognized_thread"]
    assert rec
    assert rec[0]["selected"] is True
    holes = [f for f in result["features"] if f.get("subtype") == "recognized_hole" and f.get("selected")]
    fake = [h for h in holes if abs((h.get("diameter_mm") or 0) - 6.8) < 0.3]
    assert fake == [], fake


def test_plain_hole_is_not_a_thread():
    pytest.importorskip("cadquery")
    if not os.path.exists(HOLE_D8_STEP):
        pytest.skip("missing Ø8 fixture")
    assert run_thread(HOLE_D8_STEP) == []
    result = parse_step_file(HOLE_D8_STEP)
    threads = [f for f in result["features"] if f.get("subtype") == "recognized_thread"]
    assert threads == []
    holes = [f for f in result["features"] if f.get("subtype") == "recognized_hole"]
    assert holes
    assert holes[0]["diameter_mm"] == pytest.approx(8, abs=0.2)
    for name in ("diameter_mm", "depth_mm", "hole_type", "position_type", "cut_depth_mm"):
        assert name in holes[0]


def test_open_slot_unchanged():
    pytest.importorskip("cadquery")
    if not os.path.exists(OPEN_SLOT_STEP):
        pytest.skip("missing open-slot fixture")
    result = parse_step_file(OPEN_SLOT_STEP)
    slots = [f for f in result["features"] if f.get("subtype") == "recognized_slot"]
    assert slots
    assert slots[0]["pocket_type"] == "开放"
    assert slots[0]["length"] == pytest.approx(40, abs=1.5)
    threads = [f for f in result["features"] if f.get("subtype") == "recognized_thread"]
    assert threads == []


def test_thread_chain_m8_taps(client):
    resp = client.post("/api/v1/process-plan", json={
        "feature": {"type": "thread", "diameter_mm": 8, "pitch": 1.25, "thread_length": 12},
        "material": "铝合金",
    })
    assert resp.status_code == 200
    names = [s.get("name") or s.get("process") for s in resp.get_json()["process_chain"]]
    assert "钻孔" in names
    assert "攻牙" in names
    assert "螺纹铣" not in names


def test_thread_quote_eats_tk_tap(client):
    resp = client.post("/api/v1/quotes", json={
        "material": "铝合金",
        "stock_type": "板料",
        "length": 80,
        "width": 60,
        "height": 12,
        "features": [{"type": "thread", "diameter_mm": 8, "pitch": 1.25, "thread_length": 12}],
    })
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "quoted"
    skus = [s.get("sku") for s in body["process_sequence"] if s.get("sku")]
    names = [s.get("name") for s in body["process_sequence"]]
    assert "攻牙" in names
    assert "TK-033" in skus, skus


def test_thread_quote_stainless_uses_mill(client):
    resp = client.post("/api/v1/quotes", json={
        "material": "不锈钢",
        "stock_type": "板料",
        "length": 80,
        "width": 60,
        "height": 20,
        "features": [{"type": "thread", "diameter_mm": 8, "pitch": 1.25, "thread_length": 12}],
    })
    assert resp.status_code == 200
    skus = [s.get("sku") for s in resp.get_json()["process_sequence"] if s.get("sku")]
    names = [s.get("name") for s in resp.get_json()["process_sequence"]]
    assert "螺纹铣" in names
    assert "TK-035" in skus, skus


def test_review_includes_selected_thread():
    review, features = _review_and_quote_features([
        {
            "type": "thread", "feature_id": "thread-0", "selected": True,
            "diameter_mm": 8, "pitch": 1.25, "thread_length": 12,
        },
        {
            "type": "hole", "feature_id": "hole-0", "selected": False,
            "diameter_mm": 8, "depth_mm": 12, "hole_type": "through",
        },
    ], None, 80, 60)
    assert any(f["feature_id"] == "thread-0" and f["selected"] for f in review)
    assert len(features) == 1
    assert features[0]["type"] == "thread"
    assert features[0]["diameter_mm"] == 8
    assert features[0]["pitch"] == 1.25
    assert features[0]["thread_length"] == 12


def test_factory_seeds_unchanged(client):
    body = client.get("/api/v1/factory-config").get_json()
    assert len(body["machines"]) == 23
    skus = {t["sku"] for t in body["tools"]}
    assert {f"TK-{i:03d}" for i in range(1, 40)} <= skus
    assert "TK-033" in skus and "TK-035" in skus
