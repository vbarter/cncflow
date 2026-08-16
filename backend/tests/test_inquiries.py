"""询价单 / 零件状态机。"""


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
