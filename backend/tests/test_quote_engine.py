"""报价引擎：体积公式、始终出价、滑轴、翻单。"""
import math

from cncflow_core.quoting.engine import suggested_lead_time_days


def quote(client, payload):
    return client.post("/api/v1/quotes", json=payload)


def test_bar_stock_volume_example(client):
    resp = quote(client, {
        "material": "铝合金",
        "stock_type": "棒料",
        "length": 200,
        "diameter": 50,
        "features": [],
    })
    assert resp.status_code == 200
    vol = resp.get_json()["volume"]
    assert vol["part_class"] == "轴类"
    assert abs(vol["v_blank_mm3"] - 467205) < 50
    assert abs(vol["v_part_mm3"] - 188496) < 50
    assert abs(vol["utilization_pct"] - 40.4) < 0.2


def test_always_quotes_out_of_bound_hole(client):
    resp = quote(client, {
        "material": "铝合金",
        "stock_type": "棒料",
        "length": 80,
        "diameter": 20,
        "features": [{"type": "hole", "diameter_mm": 0.8, "depth_mm": 30}],
    })
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "quoted"
    assert body["quote"]["amount"] > 0
    assert "confidence" in body
    assert isinstance(body["risk"]["customer_forbidden"], bool)


def test_repeat_order_zeros_prog_and_fixture(client):
    payload = {
        "material": "铝合金",
        "stock_type": "板材",
        "length": 80, "width": 60, "height": 20,
        "features": [{"type": "face", "length": 80, "width": 60, "depth": 1}],
        "is_repeat_order": True,
    }
    body = quote(client, payload).get_json()
    items = {i["code"]: i["amount"] for i in body["cost_items"]}
    assert items["PROG"] == 0
    assert items["FIX"] == 0
    assert body["fixture"]["is_fixture_needed"] is False
    assert body["fixture"]["fixture_count"] == 0
    assert body["fixture"]["fixture_material_cost"] == 0
    assert body["fixture"]["fixture_processing_cost"] == 0


def test_empty_features_take_vise_short_circuit(client):
    body = quote(client, {
        "material": "铝合金",
        "stock_type": "板材",
        "length": 80,
        "width": 60,
        "height": 12,
        "features": [],
    }).get_json()
    items = {i["code"]: i["amount"] for i in body["cost_items"]}

    assert body["fixture"]["method"] == "平口钳"
    assert body["fixture"]["is_fixture_needed"] is False
    assert body["fixture"]["fixture_count"] == 0
    assert body["fixture"]["fixture_material_cost"] == 0
    assert body["fixture"]["fixture_processing_cost"] == 0
    assert items["FIX"] == 0


def test_slider_changes_machining(client):
    base = {
        "material": "铝合金",
        "stock_type": "板材",
        "length": 80, "width": 60, "height": 12,
        "features": [{"type": "face", "length": 80, "width": 60, "depth": 1}],
    }
    conservative = quote(client, {**base, "slider": "保守"}).get_json()
    aggressive = quote(client, {**base, "slider": "激进"}).get_json()
    assert conservative["ui_cost"]["machining"] > aggressive["ui_cost"]["machining"]
    assert conservative["slider"]["effective_level"] == "保守"
    assert aggressive["slider"]["scrap_rate"] > conservative["slider"]["scrap_rate"]


def test_floor_applied(client):
    body = quote(client, {
        "material": "铝合金",
        "stock_type": "棒料",
        "length": 30, "diameter": 10,
        "features": [],
        "floor_charge": 99999,
        "profit_pct": 15,
    }).get_json()
    assert body["quote"]["floor_applied"] is True
    assert body["quote"]["amount"] == 99999


def test_surface_risk_tag(client):
    body = quote(client, {
        "material": "铝合金",
        "stock_type": "板材",
        "length": 80, "width": 60, "height": 20,
        "features": [{"type": "surface", "manual_hours": 0}],
    }).get_json()
    assert "需补五轴工时" in body["risk"]["tags"]


def test_hours_is_cut_toolchg_setup_rapid_not_machine_setup(client):
    body = quote(client, {
        "material": "铝合金",
        "stock_type": "板材",
        "length": 80, "width": 60, "height": 12,
        "features": [{"type": "face", "length": 80, "width": 60, "depth": 1}],
    }).get_json()
    h = body["hours"]
    assert body["quote"]["hours"] == h["total"]
    assert isinstance(h["total"], float)
    assert abs(h["total"] - round(h["cut"] + h["toolchg"] + h["setup"] + h["rapid"], 1)) < 0.15
    items = {i["code"]: i["amount"] for i in body["cost_items"]}
    assert items["MACHINE_SETUP"] > 0
    # 调机费不进 hours：hours 应远小于把 MACHINE_SETUP 折成小时
    hourly = body["equipment"]["hourly_rate"]
    if hourly:
        assert h["total"] < items["MACHINE_SETUP"] / hourly


def test_suggested_days_batch_adds_ceil_log10(client):
    payload = {
        "material": "铝合金",
        "stock_type": "板材",
        "length": 80, "width": 60, "height": 12,
        "features": [{"type": "face", "length": 80, "width": 60}],
    }
    single = quote(client, {**payload, "batch_size": 1}).get_json()
    batch = 101
    bulk = quote(client, {**payload, "batch_size": batch}).get_json()

    assert bulk["hours"]["total"] == single["hours"]["total"]
    assert bulk["fixture"]["setup_count"] == single["fixture"]["setup_count"]
    assert bulk["suggested_days"] == single["suggested_days"] + math.ceil(math.log10(batch))


def test_suggested_days_hours_setup_edges_minimum_one():
    assert suggested_lead_time_days(0, 0, 1) == 1
    assert suggested_lead_time_days(0, 1, 1) == 1
    assert suggested_lead_time_days(0.1, 1, 1) == 2
    assert suggested_lead_time_days(8, 2, 1) == 3
