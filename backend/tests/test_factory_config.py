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
    assert any(m["id"] == "VMC850E" for m in body["machines"])
    rates = {r["equipment_type"]: r for r in body["rate_table"]}
    assert rates["3轴立式加工中心"]["hourly_rate"] == 130
    again = client.get("/api/v1/factory-config").get_json()
    assert again["settings"]["ignore_available_machines"] is True
    skus = [t["sku"] for t in again["tools"]]
    assert any(s == "TK-001" for s in skus)


def test_get_seeds_machines_and_material_prices(client, seeded_db_path):
    from cncflow_core.common.db import get_conn
    conn = get_conn(seeded_db_path)
    conn.execute("DELETE FROM machines")
    conn.execute("DELETE FROM factory_material_prices")
    conn.commit()
    conn.close()
    body = client.get("/api/v1/factory-config").get_json()
    ids = {m["id"] for m in body["machines"]}
    assert "VMC850E" in ids
    assert "VM-3AX" not in ids
    prices = {r["material_code"]: r["price_per_kg"] for r in body["material_prices"]}
    assert prices["AL-01"] == 22
    assert prices["ST-01"] == 5.5
    assert prices["铝合金"] == 22
    assert prices["钢"] == 5.5
    assert {p["material_code"] for p in body["material_prices"] if p.get("tier") == "common"} >= {
        "AL-01", "AL-02", "ST-01", "ST-02", "SS-01", "SS-02", "TI-01", "CU-01", "CU-02", "FE-01"
    }



def test_get_machines_seed_travel_and_power(client, seeded_db_path):
    from cncflow_core.common.db import get_conn
    conn = get_conn(seeded_db_path)
    conn.execute("DELETE FROM machines")
    conn.commit()
    conn.close()
    body = client.get("/api/v1/factory-config").get_json()
    ids = {m["id"] for m in body["machines"]}
    assert {"VMC850E", "VMC1813", "TV855S", "U600", "HWC500", "GMC2012", "GF-C30", "CK6150"} <= ids
    assert "VM-3AX" not in ids
    assert "WEDM-1" not in ids
    machines = {m["id"]: m for m in body["machines"]}
    assert machines["VMC850E"]["travel_x"] == 850
    assert machines["VMC850E"]["torque_nm"] == 70
    assert machines["VMC850E"]["hourly_rate"] == 120
    assert machines["CK6150"]["swing_d"] == 520
    assert machines["CK6150"]["setup_fee"] == 150


def test_get_tools_from_tools_catalog(client):
    body = client.get("/api/v1/factory-config").get_json()
    skus = [t["sku"] for t in body["tools"]]
    assert "TK-001" in skus
    assert "TK-038" in skus
    assert "TK-039" in skus
    assert not any(s.startswith("SKU-") for s in skus)
    assert not any(t.get("is_mock") for t in body["tools"])
    tk001 = next(t for t in body["tools"] if t["sku"] == "TK-001")
    assert tk001["tool_type"] == "麻花钻"
    assert tk001["spec"] == "Ø3"
    assert tk001["flutes"] == 2


def test_put_material_density_roundtrip(client):
    resp = client.put("/api/v1/factory-config", json={
        "material_prices": [
            {"material_code": "AL-01", "display_name": "6061-T6铝合金", "price_per_kg": 28, "scrap_price_per_kg": 8, "density_g_cm3": 2.71, "recycle_rate": 0.8, "enabled": 1},
        ],
    })
    assert resp.status_code == 200
    again = client.get("/api/v1/factory-config").get_json()
    got = next(p for p in again["material_prices"] if p["material_code"] == "AL-01")
    assert got["density_g_cm3"] == 2.71
    assert got["recycle_rate"] == 0.8
    assert got["display_name"] == "6061-T6铝合金"


def test_put_add_tool_and_delete_machine_persists(client):
    from cncflow_core.factory.defaults import MACHINE_SEEDS
    body = client.get("/api/v1/factory-config").get_json()
    machines = [dict(m) for m in MACHINE_SEEDS if m["id"] != "HWC500"]
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
    assert "HMC-1" not in ids
    assert "VMC850E" in ids
    assert "VM-3AX" not in ids
    assert "UI-DR-09900" in {t["sku"] for t in again["tools"]}


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
    assert machine_types <= types
    families = {p.get("family") for p in body["material_prices"]}
    assert "铝合金" in families
    assert "普通碳钢" in families
    assert "工程塑料" in families
    steel = next(p for p in body["material_prices"] if p["material_code"] == "钢")
    assert steel["family"] == "普通碳钢"
    assert steel.get("alias_of") == "ST-01"
    ext = [p for p in body["material_prices"] if p.get("tier") == "extended"]
    assert len(ext) == 8
    assert all(p.get("warning") == "报价前确认" for p in ext)


def test_0815_catalog_and_tk_quote_sku(client):
    body = client.get("/api/v1/factory-config").get_json()
    assert len([m for m in body["machines"] if m["id"] in {
        "VMC850E", "VMC1160", "VMC1370", "VMC1580", "VMC1813",
        "VMC850E+HRV160A", "VMC1160+HRV210A", "TV855S",
        "U600", "MU-S600", "DMU65",
        "HWC500", "HWC630", "HWC800",
        "GMC2012", "GMC3018", "GMC4022",
        "GF-C30", "Sodick-ALN40S", "EDS40S",
        "CK6150", "CK6180", "CTX1250",
    }]) == 23
    common = [p for p in body["material_prices"] if p.get("tier") == "common"]
    assert {p["material_code"] for p in common} == {
        "AL-01", "AL-02", "ST-01", "ST-02", "SS-01", "SS-02", "TI-01", "CU-01", "CU-02", "FE-01"
    }
    skus = {t["sku"] for t in body["tools"]}
    assert {f"TK-{i:03d}" for i in range(1, 40)} <= skus
    assert not any(s.startswith("SKU-") for s in skus)


def test_steel_alias_resolves_to_st01_price(client):
    from cncflow_core.factory.store import resolve_material_code
    from cncflow_core.quoting.engine import _price
    assert resolve_material_code("钢") == "ST-01"
    assert resolve_material_code("铝合金") == "AL-01"
    body = client.get("/api/v1/factory-config").get_json()
    price, scrap, eta = _price("钢", body, {"material_code": "钢"})
    assert price == 5.5
    assert scrap == 1.8
    assert eta == 0.90
