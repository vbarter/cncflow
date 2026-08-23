"""冻结 MVP：孔钻、槽铣刀按目录刀径全等优先，无全等时显式就近。"""

import pytest

from cncflow_core.factory.defaults import TOOL_SEEDS


def _quote(client, features):
    response = client.post("/api/v1/quotes", json={
        "material": "铝合金",
        "stock_type": "板料",
        "length": 80,
        "width": 60,
        "height": 12,
        "features": features,
    })
    assert response.status_code == 200
    return response.get_json()


def _step(body, process):
    return next(step for step in body["process_sequence"] if step["process"] == process)


def test_o8_hole_uses_nearest_tk003_with_explicit_risk(client):
    catalog_drills = [
        tool for tool in TOOL_SEEDS
        if tool["category"] == "钻头" and tool["in_stock"]
    ]
    assert not any(tool["diameter_mm"] == 8 for tool in catalog_drills)

    body = _quote(client, [{
        "type": "hole",
        "feature_id": "hole-o8",
        "diameter_mm": 8,
        "depth_mm": 12,
        "hole_type": "through",
    }])
    drill = _step(body, "drill")

    assert drill["sku"] == "TK-003"
    assert drill["match_status"] == "nearest"
    assert drill["selection_target_diameter_mm"] == pytest.approx(8)
    assert drill["tool_diameter_mm"] == pytest.approx(6)
    assert "库存无 Ø8mm 全等刀具" in drill["match_reason"]
    assert "刀径非全等，需工艺确认" in drill["risk_tags"]
    assert "刀径非全等，需工艺确认" in body["risk"]["tags"]

    plan = next(item["plan"] for item in body["features"] if item["feature_id"] == "hole-o8")
    selected = next(step for step in plan["tool_chain"] if step["process"] == "drill")["selected_candidate"]
    assert selected["candidate_id"] == "TK-003"
    assert selected["match_status"] == "nearest"


def test_open_slot_w10_uses_tk022_below_seventy_percent_width(client):
    body = _quote(client, [{
        "type": "slot",
        "feature_id": "slot-w10",
        "length": 40,
        "width": 10,
        "depth": 8,
        "corner_radius": 3,
        "pocket_type": "开放",
    }])
    slot = _step(body, "rough_pocket")

    assert slot["sku"] == "TK-022"
    assert slot["match_status"] == "nearest"
    assert slot["selection_target_diameter_mm"] == pytest.approx(7)
    assert slot["tool_diameter_mm"] == pytest.approx(6)
    assert slot["tool_diameter_mm"] <= 10 * 0.7


def test_m8_tap_exact_and_pilot_nearest_tk003(client):
    body = _quote(client, [{
        "type": "thread",
        "feature_id": "thread-m8",
        "nominal_d": 8,
        "pitch": 1.25,
        "thread_length": 12,
    }])
    pilot = _step(body, "drill")
    tap = _step(body, "tap")

    assert pilot["selection_target_diameter_mm"] == pytest.approx(6.8)
    assert pilot["tool_diameter_mm"] == pytest.approx(6)
    assert pilot["sku"] == "TK-003"
    assert pilot["match_status"] == "nearest"
    assert tap["selection_target_diameter_mm"] == pytest.approx(8)
    assert tap["tool_diameter_mm"] == pytest.approx(8)
    assert tap["sku"] == "TK-033"
    assert tap["match_status"] == "exact"


def test_exact_hole_diameter_prefers_exact_catalog_sku(client):
    body = _quote(client, [{
        "type": "hole",
        "feature_id": "hole-o6",
        "diameter_mm": 6,
        "depth_mm": 12,
        "hole_type": "through",
    }])
    drill = _step(body, "drill")

    assert drill["sku"] == "TK-003"
    assert drill["match_status"] == "exact"
    assert drill["selection_target_diameter_mm"] == pytest.approx(6)
    assert drill["tool_diameter_mm"] == pytest.approx(6)
    assert "刀径非全等，需工艺确认" not in body["risk"]["tags"]
