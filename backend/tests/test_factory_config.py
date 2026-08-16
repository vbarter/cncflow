"""工厂配置 GET/PUT 与费率缺省。"""


def test_get_seeds_rate_table(client):
    resp = client.get("/api/v1/factory-config")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["settings"]["profit_pct"] == 15
    assert body["settings"]["ignore_available_machines"] is False
    types = {row["equipment_type"]: row for row in body["rate_table"]}
    assert types["3轴立式加工中心"]["hourly_rate"] == 120
    assert types["5轴联动加工中心"]["programming_fee_new"] == 800


def test_put_roundtrip(client):
    payload = {
        "settings": {"profit_pct": 18, "ignore_available_machines": True, "inspect_fee": 80},
        "machines": [{"id": "vm850", "type": "3轴立式加工中心", "axes": 3, "enabled": True}],
        "material_prices": [{"material_code": "AL-6061", "price_per_kg": 28, "scrap_price_per_kg": 8}],
        "rate_table": [{"equipment_type": "3轴立式加工中心", "hourly_rate": 130, "setup_fee": 200, "programming_fee_new": 300}],
    }
    resp = client.put("/api/v1/factory-config", json=payload)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["settings"]["profit_pct"] == 18
    assert body["settings"]["ignore_available_machines"] is True
    assert body["machines"][0]["id"] == "vm850"
    rates = {r["equipment_type"]: r for r in body["rate_table"]}
    assert rates["3轴立式加工中心"]["hourly_rate"] == 130
    again = client.get("/api/v1/factory-config").get_json()
    assert again["settings"]["ignore_available_machines"] is True
