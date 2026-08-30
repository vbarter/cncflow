"""设备选定：包络 ∩ 0815，三件落 VMC850E，费率走表。"""


def _plate(features, **extra):
    body = {
        "material": "铝合金",
        "stock_type": "板材",
        "length": 80, "width": 60, "height": 12,
        "features": features,
    }
    body.update(extra)
    return body


def test_o8_picks_vmc850e(client):
    body = client.post("/api/v1/quotes", json=_plate([
        {"type": "hole", "feature_id": "hole-0", "diameter_mm": 8, "depth_mm": 12, "hole_type": "through"},
        {"type": "face", "feature_id": "face-1", "length": 80, "width": 60},
    ])).get_json()
    eq = body["equipment"]
    assert eq["model"] == "VMC850E"
    assert eq["type"] == "3轴立式加工中心"
    assert eq["hourly_rate"] == 120
    names = [s["name"] for s in body["process_sequence"]]
    assert names == ["面粗", "钻孔", "倒角"]
    drill = next(s for s in body["process_sequence"] if s["process"] == "drill")
    assert abs(drill["time"]["cut"] - 14.4) < 0.05
    assert "设备不匹配" not in (body.get("risk") or {}).get("tags", [])


def test_open_slot_picks_vmc850e(client):
    body = client.post("/api/v1/quotes", json=_plate([
        {"type": "slot", "feature_id": "slot-0", "length": 40, "width": 10, "depth": 8, "corner_radius": 3, "pocket_type": "开放"},
        {"type": "face", "feature_id": "face-0", "length": 80, "width": 60},
    ])).get_json()
    eq = body["equipment"]
    assert eq["model"] == "VMC850E"
    assert eq["type"] == "3轴立式加工中心"
    assert eq["hourly_rate"] == 120
    assert [s["name"] for s in body["process_sequence"]] == ["槽粗", "面粗", "倒角"]


def test_m8_picks_vmc850e(client):
    body = client.post("/api/v1/quotes", json={
        "material": "铝合金",
        "stock_type": "板材",
        "length": 40, "width": 40, "height": 12,
        "features": [
            {"type": "face", "feature_id": "face-2", "length": 40, "width": 40},
            {"type": "thread", "feature_id": "thread-0", "nominal_d": 8, "pitch": 1.25, "thread_length": 12},
        ],
    }).get_json()
    eq = body["equipment"]
    assert eq["model"] == "VMC850E"
    assert eq["type"] == "3轴立式加工中心"
    assert eq["hourly_rate"] == 120
    assert [s["name"] for s in body["process_sequence"]] == ["面粗", "底孔", "攻牙", "倒角"]


def test_rate_follows_table_not_hardcode(client):
    cfg = client.get("/api/v1/factory-config").get_json()
    rates = []
    for row in cfg["rate_table"]:
        item = dict(row)
        if item["equipment_type"] == "3轴立式加工中心":
            item["hourly_rate"] = 133
        rates.append(item)
    orig = cfg["rate_table"]
    client.put("/api/v1/factory-config", json={"rate_table": rates})
    try:
        body = client.post("/api/v1/quotes", json=_plate([
            {"type": "face", "feature_id": "face-1", "length": 80, "width": 60},
        ])).get_json()
        assert body["equipment"]["model"] == "VMC850E"
        assert body["equipment"]["hourly_rate"] == 133
    finally:
        client.put("/api/v1/factory-config", json={"rate_table": orig})


def test_no_match_still_quotes(client):
    body = client.post("/api/v1/quotes", json=_plate([
        {"type": "hole", "feature_id": "h0", "diameter_mm": 0.3, "depth_mm": 12, "hole_type": "through"},
    ])).get_json()
    assert body["status"] == "quoted"
    assert body["quote"]["amount"] > 0
    assert "设备不匹配" in body["risk"]["tags"]
    d4 = [item for item in body["deductions"] if item["rule_id"] == "D4-1"]
    assert len(d4) == 1
    assert d4[0]["deduction"] == 10
    d8 = [item for item in body["deductions"] if item["rule_id"] == "D8-1"]
    assert len(d8) == 1
    assert d8[0]["missing_equipment_fields"] == ["model"]
    assert body["equipment"]["type"]
    assert body["equipment"]["hourly_rate"] is not None
