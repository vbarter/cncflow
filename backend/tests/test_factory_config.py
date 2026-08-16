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
    assert any(m["id"] == "vm850" for m in body["machines"])
    assert {m["type"] for m in body["machines"] if m["type"] == "3轴立式加工中心"}
    rates = {r["equipment_type"]: r for r in body["rate_table"]}
    assert rates["3轴立式加工中心"]["hourly_rate"] == 130
    again = client.get("/api/v1/factory-config").get_json()
    assert again["settings"]["ignore_available_machines"] is True
    skus = [t["sku"] for t in again["tools"]]
    assert any("DR-00300" in s for s in skus)


def test_get_seeds_machines_and_material_prices(client, seeded_db_path):
    from cncflow_core.common.db import get_conn
    conn = get_conn(seeded_db_path)
    conn.execute("DELETE FROM machines")
    conn.execute("DELETE FROM factory_material_prices")
    conn.commit()
    conn.close()
    body = client.get("/api/v1/factory-config").get_json()
    ids = {m["id"] for m in body["machines"]}
    assert "VM-3AX" in ids
    prices = {r["material_code"]: r["price_per_kg"] for r in body["material_prices"]}
    assert prices["AL6061-T6"] == 28
    assert prices["铝合金"] == 25



def test_get_machines_seed_travel_and_power(client, seeded_db_path):
    from cncflow_core.common.db import get_conn
    conn = get_conn(seeded_db_path)
    conn.execute("DELETE FROM machines")
    conn.commit()
    conn.close()
    body = client.get("/api/v1/factory-config").get_json()
    assert len(body["machines"]) == 12
    machines = {m["id"]: m for m in body["machines"]}
    assert machines["VM-3AX"]["travel_x"] == 850
    assert machines["VM-3AX"]["power_kw"] == 11
    conn = get_conn(seeded_db_path)
    conn.execute("UPDATE machines SET travel_x=NULL, power_kw=NULL WHERE id='VM-3AX'")
    conn.commit()
    conn.close()
    body = client.get("/api/v1/factory-config").get_json()
    machines = {m["id"]: m for m in body["machines"]}
    assert machines["VM-3AX"]["travel_x"] == 850
    assert machines["VM-3AX"]["power_kw"] == 11


def test_get_tools_from_tools_catalog(client):
    body = client.get("/api/v1/factory-config").get_json()
    skus = [t["sku"] for t in body["tools"]]
    assert any("DR-00300" in s for s in skus)
    assert any("DR-00800" in s for s in skus)


def test_put_material_density_roundtrip(client):
    resp = client.put("/api/v1/factory-config", json={
        "material_prices": [
            {"material_code": "AL6061-T6", "price_per_kg": 28, "scrap_price_per_kg": 8, "density_g_cm3": 2.71, "enabled": 1},
        ],
    })
    assert resp.status_code == 200
    again = client.get("/api/v1/factory-config").get_json()
    got = next(p for p in again["material_prices"] if p["material_code"] == "AL6061-T6")
    assert got["density_g_cm3"] == 2.71


def test_put_add_tool_and_delete_machine_persists(client):
    from cncflow_core.factory.defaults import MACHINE_SEEDS
    body = client.get("/api/v1/factory-config").get_json()
    machines = [dict(m) for m in MACHINE_SEEDS if m["id"] != "HMC-1"]
    tools = list(body["tools"])
    tools.append({
        "sku": "UI-DR-09900",
        "category": "钻头",
        "diameter_mm": 9.9,
        "structure": "标准",
        "base_material": "硬质合金",
        "coating": "无涂层",
        "precision_grade": "普通",
        "in_stock": 1,
    })
    resp = client.put("/api/v1/factory-config", json={"machines": machines, "tools": tools})
    assert resp.status_code == 200
    again = client.get("/api/v1/factory-config").get_json()
    ids = {m["id"] for m in again["machines"]}
    assert "VM-3AX" in ids
    assert "UI-DR-09900" in {t["sku"] for t in again["tools"]}
    assert {m["type"] for m in again["machines"]} >= {"3轴立式加工中心", "龙门加工中心", "车削中心CNC车"}


def test_catalog_groups_rate_types_and_material_family(client, seeded_db_path):
    from cncflow_core.common.db import get_conn
    from cncflow_core.factory.defaults import RATE_TABLE
    conn = get_conn(seeded_db_path)
    conn.execute("DELETE FROM factory_material_prices")
    conn.commit()
    conn.close()
    body = client.get("/api/v1/factory-config").get_json()
    types = {r["equipment_type"] for r in body["rate_table"]}
    assert types == {r["equipment_type"] for r in RATE_TABLE}
    assert len(types) == 12
    machine_types = {m["type"] for m in body["machines"]}
    assert machine_types == types
    by_type = {m["type"]: m for m in body["machines"]}
    assert by_type["龙门加工中心"]["hourly_rate"] == 220
    assert by_type["龙门加工中心"]["setup_fee"] == 600
    assert by_type["精密坐标镗床"]["hourly_rate"] == 350
    assert by_type["电火花线切割WEDM"]["hourly_rate"] == 60
    assert by_type["车削中心CNC车"]["setup_fee"] == 150
    families = {p.get("family") for p in body["material_prices"]}
    assert "铝合金" in families
    assert "普通碳钢" in families
    assert "工程塑料" in families
    steel = next(p for p in body["material_prices"] if p["material_code"] == "钢")
    assert steel["family"] == "普通碳钢"
