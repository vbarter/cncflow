"""台阶插件：profile_type / L / H；默认粗铣+倒角吃 TK；孔槽面螺纹不回退。"""
import os
from io import BytesIO

import pytest

from cncflow_core.common.db import get_conn
from cncflow_core.geometry.plugins import run_step
from cncflow_core.geometry.service import (
    _covers_stock_lw,
    _unselect_step_shoulder_tops,
    apply_quote_default_selection,
    parse_step_file,
)
from cncflow_core.ingestion.jobs import finish_job
from cncflow_core.inquiries.api import _review_and_quote_features


MINIMAL_STEP = (
    b"ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('AUTOMOTIVE_DESIGN'));\n"
    b"ENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;"
)


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
    assert len(steps) == 1, result.get("features")
    st = steps[0]
    assert st["feature_id"] == "step-0"
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


def test_covers_stock_lw_keeps_plate_rejects_shoulder():
    assert _covers_stock_lw(80, 60, 80, 60) is True
    assert _covers_stock_lw(80, 50, 80, 50) is True
    assert _covers_stock_lw(80, 25, 80, 50) is False


def test_quote_default_unselects_shoulder_even_if_selected_true():
    """POST /quote 默认路径不信存储 selected=True，肩顶仍摘掉。"""
    feats = [
        {
            "type": "step", "feature_id": "step-0", "subtype": "recognized_step",
            "selected": True, "profile_type": "台阶", "length": 80, "width": 25, "height": 8,
        },
        {
            "type": "face", "feature_id": "face-0", "subtype": "recognized_face",
            "selected": True, "length": 80, "width": 25, "face_position": "水平",
        },
    ]
    out = apply_quote_default_selection([dict(f) for f in feats], 80, 50)
    by_id = {f["feature_id"]: f for f in out}
    assert by_id["step-0"]["selected"] is True
    assert by_id["face-0"]["selected"] is False
    review, quoted = _review_and_quote_features(feats, None, 80, 50)
    by_id = {f["feature_id"]: f for f in review}
    assert by_id["step-0"]["selected"] is True
    assert by_id["face-0"]["selected"] is False
    assert [f["type"] for f in quoted] == ["step"]


def _seed_quoted_part(client, seeded_db_path, features, box, name="零件"):
    inq = client.post("/api/v1/inquiries", json={"customer": "华科"}).get_json()
    iid = inq["id"]
    pid = client.post(f"/api/v1/inquiries/{iid}/parts", json={
        "name": name, "material": "铝合金",
        "length": box[0], "width": box[1], "height": box[2],
    }).get_json()["id"]
    data = {"step_file": (BytesIO(MINIMAL_STEP), "part.step"), "part_id": pid}
    job_id = client.post("/api/v1/parse-jobs", data=data, content_type="multipart/form-data").get_json()["job_id"]
    conn = get_conn(seeded_db_path)
    finish_job(conn, job_id, {
        "geometry": {"volume_cm3": 50, "bounding_box_mm": {"x": box[0], "y": box[1], "z": box[2]}},
        "features": features,
        "drawing": None, "warnings": [],
    })
    conn.close()
    return iid, pid


def _rect_step_feats(face_selected=True):
    return [
        {
            "type": "step", "feature_id": "step-0", "subtype": "recognized_step",
            "selected": True, "profile_type": "台阶",
            "length": 80, "width": 25, "height": 8,
            "dimensions": {"length": 80, "width": 25, "height": 8, "profile_type": "台阶"},
        },
        {
            "type": "face", "feature_id": "face-0", "subtype": "recognized_face",
            "selected": face_selected, "length": 80, "width": 25, "face_position": "水平",
            "dimensions": {"length": 80, "width": 25, "face_position": "水平"},
        },
    ]


def _d8_feats():
    return [
        {
            "type": "hole", "feature_id": "hole-0", "subtype": "recognized_hole",
            "selected": True, "diameter_mm": 8, "depth_mm": 12,
            "hole_type": "through", "position_type": "垂直", "cut_depth_mm": 14.4,
            "dimensions": {"diameter_mm": 8, "depth_mm": 12},
        },
        {
            "type": "face", "feature_id": "face-1", "subtype": "recognized_face",
            "selected": True, "length": 80, "width": 60, "face_position": "水平",
            "dimensions": {"length": 80, "width": 60, "face_position": "水平"},
        },
    ]


def _selected_ids(part):
    review = (part.get("quote") or {}).get("review_features") or []
    return [f["feature_id"] for f in review if f.get("selected")]


def _skus(part):
    return [s.get("sku") for s in (part.get("quote") or {}).get("process_sequence") or []]


def test_quote_refresh_rect_step_keeps_shoulder_unselected(client, seeded_db_path):
    """78d9038e POST /quote：刷新后仍只勾 step-0，工序 TK-026+TK-036。"""
    iid, pid = _seed_quoted_part(
        client, seeded_db_path, _rect_step_feats(face_selected=True), (80, 50, 16), "台阶",
    )
    review_part = client.get(f"/api/v1/parts/{pid}").get_json()
    assert _selected_ids(review_part) == ["step-0"], review_part.get("quote")
    quoted = client.post(f"/api/v1/inquiries/{iid}/quote", json={})
    assert quoted.status_code == 200, quoted.get_json()
    part = next(p for p in quoted.get_json()["parts"] if p["id"] == pid)
    assert _selected_ids(part) == ["step-0"], part.get("quote")
    assert _skus(part) == ["TK-026", "TK-036"], part.get("quote", {}).get("process_sequence")
    again = client.post(f"/api/v1/parts/{pid}/quote", json={})
    assert again.status_code == 200, again.get_json()
    part = again.get_json()
    assert _selected_ids(part) == ["step-0"]
    assert _skus(part) == ["TK-026", "TK-036"], part.get("quote", {}).get("process_sequence")


def test_quote_refresh_rect_step_sanitizes_previous_quote_features(client, seeded_db_path):
    """连续刷新携带上次报价 features 时，隐式选择仍须重跑台阶默认规则。"""
    iid, pid = _seed_quoted_part(
        client, seeded_db_path, _rect_step_feats(face_selected=True), (80, 50, 16), "台阶",
    )
    stale_features = [
        {
            "type": "step", "feature_id": "step-0", "profile_type": "台阶",
            "selected": True, "length": 80, "height": 8,
        },
        {
            "type": "face", "feature_id": "face-0",
            "selected": True, "length": 80, "width": 25, "face_position": "水平",
        },
    ]
    first = client.post(
        f"/api/v1/inquiries/{iid}/quote",
        json={"features": stale_features, "selected_feature_ids": []},
    )
    assert first.status_code == 200, first.get_json()
    first_part = next(p for p in first.get_json()["parts"] if p["id"] == pid)

    second = client.post(
        f"/api/v1/inquiries/{iid}/quote",
        json={"features": first_part["quote"]["features"]},
    )
    assert second.status_code == 200, second.get_json()
    part = next(p for p in second.get_json()["parts"] if p["id"] == pid)
    assert _selected_ids(first_part) == ["step-0"], first_part.get("quote")
    assert _skus(first_part) == ["TK-026", "TK-036"], first_part.get("quote", {}).get("process_sequence")
    assert _selected_ids(part) == ["step-0"], part.get("quote")
    assert _skus(part) == ["TK-026", "TK-036"], part.get("quote", {}).get("process_sequence")


def test_quote_refresh_d8_keeps_hole_and_top(client, seeded_db_path):
    """Ø8 回归：再报价仍 hole-0 + face-1。"""
    iid, pid = _seed_quoted_part(client, seeded_db_path, _d8_feats(), (80, 60, 12), "Ø8")
    first = client.get(f"/api/v1/parts/{pid}").get_json()
    assert _selected_ids(first) == ["hole-0", "face-1"], first.get("quote")
    quoted = client.post(f"/api/v1/inquiries/{iid}/quote", json={})
    assert quoted.status_code == 200, quoted.get_json()
    part = next(p for p in quoted.get_json()["parts"] if p["id"] == pid)
    assert _selected_ids(part) == ["hole-0", "face-1"], part.get("quote")
    again = client.post(f"/api/v1/parts/{pid}/quote", json={})
    assert again.status_code == 200, again.get_json()
    assert _selected_ids(again.get_json()) == ["hole-0", "face-1"]


def test_quote_refresh_rect_step_manual_check_shoulder(client, seeded_db_path):
    iid, pid = _seed_quoted_part(
        client, seeded_db_path, _rect_step_feats(face_selected=False), (80, 50, 16), "台阶",
    )
    patched = client.patch(f"/api/v1/parts/{pid}", json={"selected_feature_ids": ["step-0", "face-0"]})
    assert patched.status_code == 200, patched.get_json()
    part = patched.get_json()
    assert set(_selected_ids(part)) == {"step-0", "face-0"}
    types = {f["type"] for f in (part.get("quote") or {}).get("features") or []}
    assert types == {"step"}
    assert _skus(part) == ["TK-026", "TK-036"]
    inquiry_quote = client.post(
        f"/api/v1/inquiries/{iid}/quote",
        json={"selected_feature_ids": ["step-0", "face-0"]},
    )
    assert inquiry_quote.status_code == 200, inquiry_quote.get_json()
    inquiry_part = next(p for p in inquiry_quote.get_json()["parts"] if p["id"] == pid)
    assert set(_selected_ids(inquiry_part)) == {"step-0", "face-0"}
    assert _skus(inquiry_part) == ["TK-026", "TK-036"]
    quoted = client.post(
        f"/api/v1/parts/{pid}/quote",
        json={"selected_feature_ids": ["step-0", "face-0"]},
    )
    assert quoted.status_code == 200, quoted.get_json()
    part = quoted.get_json()
    assert set(_selected_ids(part)) == {"step-0", "face-0"}
    assert _skus(part) == ["TK-026", "TK-036"]
