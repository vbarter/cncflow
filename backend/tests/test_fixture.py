"""夹具 F1–F5 first-match。不可装夹仍 200。"""
import pytest


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
    body = resp.get_json()
    assert body["is_fixture_needed"] is False
    assert body["fixture_count"] == 0
    assert body["fixture_material_cost"] == 0
    assert body["fixture_processing_cost"] == 0
    assert body["fixture_cost_per_piece"] == 0


def test_four_axis_quote_uses_same_frozen_fixture_processing_as_plan(client):
    resp = client.post("/api/v1/quotes", json={
        "material": "铝合金",
        "stock_type": "板材",
        "length": 63.5,
        "width": 63.5,
        "height": 17,
        "batch_size": 1,
        "slider": "激进",
        "features": [{
            "type": "surface",
            "feature_id": "surface-0",
            "selected": True,
            "surface_type": "凸面",
            "curvature_radius": 20,
        }],
    })
    assert resp.status_code == 200
    quote = resp.get_json()
    body = quote["fixture"]
    items = {item["code"]: item["amount"] for item in quote["cost_items"]}
    plan = post(client, {
        "feature": {
            "type": "fixture",
            "length": 63.5,
            "width": 63.5,
            "depth": 17,
            "features": [{
                "type": "surface",
                "selected": True,
                "surface_type": "凸面",
                "curvature_radius": 20,
            }],
        },
        "material": "铝合金",
    }).get_json()

    assert quote["equipment"]["axes"] == 4
    assert quote["equipment"]["hourly_rate"] == 150
    assert body["is_fixture_needed"] is True
    assert body["fixture_material"] == "铝合金"
    assert body["fixture_count"] == 1
    assert (
        body["fixture_block_L"],
        body["fixture_block_W"],
        body["fixture_block_H"],
    ) == pytest.approx((103.5, 103.5, 47), abs=0.05)
    assert body["fixture_material_cost"] == pytest.approx(40.78, abs=0.02)
    assert body["fixture_processing_cost"] == pytest.approx(1.72, abs=0.01)
    assert body["fixture_processing_cost"] == plan["fixture_processing_cost"]
    assert items["FIX"] == pytest.approx(42.50, abs=0.01)
    assert items["FIX"] < 210


@pytest.mark.parametrize(
    ("sample", "features"),
    [
        (
            "Ø8",
            [
                {"type": "hole", "feature_id": "hole-0", "selected": True},
                {"type": "face", "feature_id": "face-1", "selected": True},
            ],
        ),
        (
            "开口槽",
            [
                {"type": "slot", "feature_id": "slot-0", "selected": True},
                {"type": "face", "feature_id": "face-0", "selected": True},
            ],
        ),
        (
            "M8",
            [
                {"type": "thread", "feature_id": "thread-0", "selected": True},
                {"type": "face", "feature_id": "face-2", "selected": True},
            ],
        ),
    ],
)
def test_pinned_vise_samples_keep_zero_fixture_cost(client, sample, features):
    body = post(client, {
        "feature": {
            "type": "fixture",
            "length": 80,
            "width": 60,
            "depth": 12,
            "features": features,
        },
        "material": "铝合金",
    }).get_json()

    assert body["fixture_method"] == "平口钳", sample
    assert body["is_fixture_needed"] is False, sample
    assert body["fixture_material_cost"] == 0, sample
    assert body["fixture_processing_cost"] == 0, sample
    assert body["fixture_cost_per_piece"] == 0, sample


def test_missing_clamping_face_still_defaults_to_present(client):
    body = post(client, {
        "feature": {
            "type": "fixture",
            "length": 80,
            "width": 60,
            "depth": 12,
            "features": [{"type": "face", "selected": True}],
        },
        "material": "铝合金",
    }).get_json()

    assert body["fixture_method"] == "平口钳"
    assert body["is_fixture_needed"] is False


def test_unselected_convex_surface_does_not_require_fixture(client):
    body = post(client, {
        "feature": {
            "type": "fixture",
            "length": 80,
            "width": 60,
            "depth": 12,
            "features": [
                {
                    "type": "surface",
                    "feature_id": "surface-0",
                    "selected": False,
                    "surface_type": "凸面",
                },
                {"type": "face", "feature_id": "face-0", "selected": True},
            ],
        },
        "material": "铝合金",
    }).get_json()

    assert body["fixture_method"] == "平口钳"
    assert body["is_fixture_needed"] is False
    assert body["fixture_material_cost"] == 0
