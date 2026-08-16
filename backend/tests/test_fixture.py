"""夹具 F1–F5 first-match。不可装夹仍 200。"""


def post(client, payload):
    return client.post("/api/v1/process-plan", json=payload)


def test_square_stock_is_f1_vise(client):
    resp = post(client, {
        "feature": {"type": "fixture", "length": 80, "width": 60, "depth": 30},
        "material": "铝合金", "tolerance_it": 11,
    })
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["fixture_type"] == "F1"
    assert body["fixture_method"] == "平口钳"
    assert body["is_machinable"] is True


def test_shaft_is_f5(client):
    resp = post(client, {
        "feature": {
            "type": "fixture", "length": 20, "width": 20, "depth": 120,
            "features": [{"surface_type": "回转面"}],
        },
        "material": "钢",
    })
    assert resp.status_code == 200
    assert resp.get_json()["fixture_type"] == "F5"


def test_freeform_is_f3(client):
    resp = post(client, {
        "feature": {
            "type": "fixture", "length": 80, "width": 60, "depth": 40,
            "features": [{"surface_type": "自由曲面"}],
        },
        "material": "铝合金",
    })
    assert resp.status_code == 200
    assert resp.get_json()["fixture_type"] == "F3"


def test_hardened_steel_is_f3(client):
    resp = post(client, {
        "feature": {"type": "fixture", "length": 80, "width": 60, "depth": 30},
        "material": "淬硬钢",
    })
    assert resp.status_code == 200
    assert resp.get_json()["fixture_type"] == "F3"


def test_unmachinable_still_200(client):
    resp = post(client, {
        "feature": {
            "type": "fixture", "length": 80, "width": 60, "depth": 30,
            "features": [{"position_type": "曲面", "surface_type": "自由曲面"}],
        },
        "material": "铝合金",
        "machine_axes": 3,
    })
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["is_machinable"] is False
    assert body["fixture_type"]  # 仍给出夹具建议
    assert any("高风险" in t or "不可" in t for t in body["risk_tags"])


def test_repeat_order_zero_fixture_cost(client):
    resp = post(client, {
        "feature": {
            "type": "fixture", "length": 80, "width": 60, "depth": 40,
            "features": [{"surface_type": "自由曲面"}],
        },
        "material": "铝合金",
        "is_repeat_order": True,
    })
    assert resp.get_json()["fixture_cost_per_piece"] == 0
