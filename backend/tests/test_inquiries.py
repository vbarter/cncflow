"""询价单 / 零件状态机。"""
from io import BytesIO

from cncflow_core.common.db import get_conn
from cncflow_core.ingestion.jobs import finish_job


MINIMAL_STEP = b"ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('AUTOMOTIVE_DESIGN'));\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;"




def test_inquiry_quote_confirm_readonly(client):
    r = client.post("/api/v1/inquiries", json={"customer": "华科", "project": "夹具A", "due_date": "2026-08-20"})
    assert r.status_code == 201
    iid = r.get_json()["id"]
    p = client.post(f"/api/v1/inquiries/{iid}/parts", json={
        "name": "底板", "material": "铝合金", "length": 80, "width": 60, "height": 12, "blank_type": "板料",
    })
    assert p.status_code == 201
    q = client.post(f"/api/v1/inquiries/{iid}/quote", json={})
    assert q.status_code == 200
    part = q.get_json()["parts"][0]
    assert part["status"] == "quoted"
    assert part["quote"]["quote"]["amount"] > 0
    c = client.post(f"/api/v1/parts/{part['id']}/confirm")
    assert c.status_code == 200
    assert c.get_json()["status"] == "confirmed"
    bad = client.patch(f"/api/v1/parts/{part['id']}", json={"slider": "激进"})
    assert bad.status_code == 409


def test_list_filter_customer(client):
    client.post("/api/v1/inquiries", json={"customer": "甲厂", "project": "P1"})
    items = client.get("/api/v1/inquiries?customer=甲").get_json()["items"]
    assert any(i["customer"] == "甲厂" for i in items)

def test_inquiry_auto_rfq_title(client):
    r = client.post("/api/v1/inquiries", json={"customer": "华科"})
    assert r.status_code == 201
    title = r.get_json()["title"]
    assert title.startswith("RFQ-")


def test_quote_skips_parts_without_dims(client):
    r = client.post("/api/v1/inquiries", json={"customer": "华科"})
    iid = r.get_json()["id"]
    p = client.post(f"/api/v1/inquiries/{iid}/parts", json={"name": "底板", "material": "铝合金"})
    assert p.status_code == 201
    assert p.get_json()["length"] in (None, 0)
    q = client.post(f"/api/v1/inquiries/{iid}/quote", json={})
    assert q.status_code == 200
    part = q.get_json()["parts"][0]
    assert part["status"] == "draft"
    assert part.get("quote") in (None, {})



def test_quote_uses_parse_bbox(client, seeded_db_path):
    inq = client.post("/api/v1/inquiries", json={"customer": "华科"}).get_json()
    iid = inq["id"]
    pid = client.post(f"/api/v1/inquiries/{iid}/parts", json={"name": "底板", "material": "铝合金"}).get_json()["id"]
    data = {"step_file": (BytesIO(MINIMAL_STEP), "part.step"), "part_id": pid}
    job_id = client.post("/api/v1/parse-jobs", data=data, content_type="multipart/form-data").get_json()["job_id"]
    conn = get_conn(seeded_db_path)
    finish_job(conn, job_id, {
        "geometry": {"volume_cm3": 12.5, "bounding_box_mm": {"x": 80, "y": 40, "z": 12}},
        "features": [{"type": "hole", "selected": True, "dimensions": {"diameter_mm": 6, "depth_mm": 12}}],
        "drawing": None, "warnings": [],
    })
    conn.close()
    q = client.post(f"/api/v1/inquiries/{iid}/quote", json={})
    assert q.status_code == 200, q.get_json()
    part = q.get_json()["parts"][0]
    assert part["status"] == "quoted"
    assert part["quote"]["quote"]["amount"] > 0


def test_patch_material_and_unselect_hole_recalculates(client, seeded_db_path):
    inq = client.post("/api/v1/inquiries", json={"customer": "华科"}).get_json()
    iid = inq["id"]
    pid = client.post(f"/api/v1/inquiries/{iid}/parts", json={"name": "底板", "material": "铝合金"}).get_json()["id"]
    data = {"step_file": (BytesIO(MINIMAL_STEP), "part.step"), "part_id": pid}
    job_id = client.post("/api/v1/parse-jobs", data=data, content_type="multipart/form-data").get_json()["job_id"]
    conn = get_conn(seeded_db_path)
    finish_job(conn, job_id, {
        "geometry": {"volume_cm3": 12.5, "bounding_box_mm": {"x": 80, "y": 40, "z": 12}},
        "features": [
            {"type": "hole", "feature_id": "f0", "selected": True, "dimensions": {"diameter_mm": 6, "depth_mm": 12}},
            {"type": "hole", "feature_id": "f1", "selected": True, "dimensions": {"diameter_mm": 10, "depth_mm": 12}},
        ],
        "drawing": None, "warnings": [],
    })
    conn.close()
    q = client.post(f"/api/v1/inquiries/{iid}/quote", json={})
    assert q.status_code == 200, q.get_json()
    part = q.get_json()["parts"][0]
    assert part["status"] == "quoted"
    patched = client.patch(f"/api/v1/parts/{part['id']}", json={
        "material": "SUS304",
        "tolerance_it": 7,
        "roughness_ra": 1.6,
        "selected_feature_ids": ["f0"],
    })
    assert patched.status_code == 200, patched.get_json()
    part = patched.get_json()
    assert part["status"] == "quoted"
    assert part["material_code"] in {"SUS304", "SUS-304", "不锈钢"}
    assert int(part["tolerance_it"]) == 7
    assert float(part["roughness_ra"]) == 1.6
    review = (part.get("quote") or {}).get("review_features") or []
    by_id = {str(f.get("feature_id") or f.get("id")): f for f in review}
    assert by_id["f0"]["selected"] is True
    assert by_id["f1"]["selected"] is False
    assert part["quote"]["quote"]["amount"] > 0


def test_part_detail_shows_parse_job_holes_before_quote(client, seeded_db_path):
    inq = client.post("/api/v1/inquiries", json={"customer": "华科"}).get_json()
    iid = inq["id"]
    pid = client.post(f"/api/v1/inquiries/{iid}/parts", json={"name": "ZN-010", "material": "铝合金"}).get_json()["id"]
    data = {"step_file": (BytesIO(MINIMAL_STEP), "part.step"), "part_id": pid}
    job_id = client.post("/api/v1/parse-jobs", data=data, content_type="multipart/form-data").get_json()["job_id"]
    conn = get_conn(seeded_db_path)
    finish_job(conn, job_id, {
        "geometry": {"volume_cm3": 12.5, "bounding_box_mm": {"x": 50, "y": 50, "z": 44}},
        "features": [{
            "type": "hole", "feature_id": "h0", "subtype": "recognized_hole", "selected": True,
            "diameter_mm": 3.30, "depth_mm": 26, "hole_type": "through",
            "position_type": "垂直", "cut_depth_mm": 26.99,
        }],
        "drawing": None, "warnings": [],
    })
    conn.close()
    part = client.get(f"/api/v1/parts/{pid}").get_json()
    assert part["status"] == "quoted"
    q = part["quote"]
    assert q["quote"]["amount"] > 0
    assert q["quote"]["cost"] > 0
    assert "margin" in q["quote"]
    assert "hours" in q["quote"]
    assert q["hours"]["total"] == q["quote"]["hours"]
    assert "ui_cost" in q
    for key in ("material", "machining", "setup", "programming", "inspect", "toolwear", "scrap"):
        assert key in q["ui_cost"]
    assert q.get("process_sequence")
    step = q["process_sequence"][0]
    assert step.get("name")
    assert step.get("minutes") is not None
    assert step.get("amount") is not None
    assert any(s.get("sku") for s in q["process_sequence"]), q["process_sequence"]
    assert all(s.get("process") for s in q["process_sequence"])
    holes = part.get("parsed_features") or q.get("review_features") or []
    hole = next(f for f in holes if f.get("type") == "hole")
    assert hole["diameter_mm"] == 3.30
    assert hole["depth_mm"] == 26
    assert hole["hole_type"] == "through"
    assert hole["position_type"] == "垂直"
    assert hole.get("cut_depth_mm") == 26.99


def test_post_part_quote_one_click(client):
    r = client.post("/api/v1/inquiries", json={"customer": "华科"})
    iid = r.get_json()["id"]
    pid = client.post(f"/api/v1/inquiries/{iid}/parts", json={
        "name": "底板", "material": "铝合金", "length": 80, "width": 60, "height": 12, "blank_type": "板料",
    }).get_json()["id"]
    q = client.post(f"/api/v1/parts/{pid}/quote", json={})
    assert q.status_code == 200, q.get_json()
    part = q.get_json()
    assert part["status"] == "quoted"
    assert part["quote"]["quote"]["amount"] > 0
    assert part["quote"]["ui_cost"]["material"] >= 0
    # 无识别孔时本轮不出默认面工步，金额仍在
    assert part["quote"]["quote"]["amount"] > 0


def test_steel_alias_quotes_hole_with_sku(client, seeded_db_path):
    inq = client.post("/api/v1/inquiries", json={"customer": "华科"}).get_json()
    pid = client.post(f"/api/v1/inquiries/{inq['id']}/parts", json={"name": "ZN-010", "material": "钢"}).get_json()["id"]
    data = {"step_file": (BytesIO(MINIMAL_STEP), "part.step"), "part_id": pid}
    job_id = client.post("/api/v1/parse-jobs", data=data, content_type="multipart/form-data").get_json()["job_id"]
    conn = get_conn(seeded_db_path)
    finish_job(conn, job_id, {
        "geometry": {"volume_cm3": 12.5, "bounding_box_mm": {"x": 50, "y": 50, "z": 44}},
        "features": [{
            "type": "hole", "feature_id": "h0", "subtype": "recognized_hole", "selected": True,
            "diameter_mm": 8.0, "depth_mm": 12, "hole_type": "through",
            "position_type": "垂直", "cut_depth_mm": 14.4,
        }],
        "drawing": None, "warnings": [],
    })
    conn.close()
    part = client.get(f"/api/v1/parts/{pid}").get_json()
    assert part["status"] == "quoted"
    seq = part["quote"]["process_sequence"]
    assert seq, part["quote"].get("features")
    assert any(s.get("sku") for s in seq), seq
    skus = [s.get("sku") for s in seq if s.get("sku")]
    assert skus
    assert all(not str(s).startswith("SKU-") and not str(s).startswith("DOC") for s in skus), seq
    assert any(str(s).startswith("TK-") for s in skus), seq
    assert not any((f.get("plan") or {}).get("error") for f in part["quote"].get("features") or [])


def test_nonstandard_d33_picks_nearest_sku(client, seeded_db_path):
    inq = client.post("/api/v1/inquiries", json={"customer": "华科"}).get_json()
    pid = client.post(f"/api/v1/inquiries/{inq['id']}/parts", json={"name": "ZN-010", "material": "钢"}).get_json()["id"]
    data = {"step_file": (BytesIO(MINIMAL_STEP), "part.step"), "part_id": pid}
    job_id = client.post("/api/v1/parse-jobs", data=data, content_type="multipart/form-data").get_json()["job_id"]
    conn = get_conn(seeded_db_path)
    finish_job(conn, job_id, {
        "geometry": {"volume_cm3": 12.5, "bounding_box_mm": {"x": 50, "y": 50, "z": 44}},
        "features": [{
            "type": "hole", "feature_id": "h0", "subtype": "recognized_hole", "selected": True,
            "diameter_mm": 3.30, "depth_mm": 26, "hole_type": "through",
            "position_type": "垂直", "cut_depth_mm": 26.99,
        }],
        "drawing": None, "warnings": [],
    })
    conn.close()
    part = client.get(f"/api/v1/parts/{pid}").get_json()
    assert part["status"] == "quoted"
    seq = part["quote"]["process_sequence"]
    assert seq
    assert all(s.get("sku") for s in seq), seq
    assert any(s.get("process") == "drill" for s in seq)


def test_zn010_deep_hole_risk_and_double_chamfer(client, seeded_db_path):
    inq = client.post("/api/v1/inquiries", json={"customer": "华科"}).get_json()
    pid = client.post(f"/api/v1/inquiries/{inq['id']}/parts", json={"name": "ZN-010", "material": "钢"}).get_json()["id"]
    data = {"step_file": (BytesIO(MINIMAL_STEP), "part.step"), "part_id": pid}
    job_id = client.post("/api/v1/parse-jobs", data=data, content_type="multipart/form-data").get_json()["job_id"]
    conn = get_conn(seeded_db_path)
    finish_job(conn, job_id, {
        "geometry": {"volume_cm3": 12.5, "bounding_box_mm": {"x": 50, "y": 50, "z": 44}},
        "features": [{
            "type": "hole", "feature_id": "h0", "subtype": "recognized_hole", "selected": True,
            "diameter_mm": 3.30, "depth_mm": 26, "hole_type": "through",
            "position_type": "垂直", "cut_depth_mm": 26.99,
        }],
        "drawing": None, "warnings": [],
    })
    conn.close()
    part = client.get(f"/api/v1/parts/{pid}").get_json()
    q = part["quote"]
    tags = (q.get("risk") or {}).get("tags") or []
    assert "深孔高风险" in tags
    assert q["risk"]["level"] == "high"
    plan = next(f["plan"] for f in q["features"] if f["type"] == "hole")
    chain = plan.get("tool_chain") or plan.get("process_chain") or []
    assert [s.get("name") for s in chain if s.get("process") == "chamfer"] == ["入口倒角", "出口倒角"]
    ch = [s for s in q["process_sequence"] if s.get("process") == "chamfer"]
    assert len(ch) == 1
    assert ch[0].get("name") == "倒角"
