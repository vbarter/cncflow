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
