"""一期毛坯决策与多方案报价合同。"""
import pytest

from cncflow_core.quoting import blank, plans


def _payload(**overrides):
    payload = {
        "material": "铝合金",
        "length": 80,
        "width": 60,
        "height": 12,
        "features": [{"type": "face", "length": 80, "width": 60}],
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    ("overrides", "blank_type"),
    [
        ({"stock_type": "板料"}, "plate"),
        ({"stock_type": "方料", "height": 40}, "square_bar"),
        (
            {
                "stock_type": "棒料",
                "length": 200,
                "width": None,
                "height": None,
                "diameter": 50,
            },
            "round_bar",
        ),
    ],
)
def test_blank_decision_types_and_allowance(overrides, blank_type):
    result = blank.decide(_payload(**overrides))

    assert result["blank_type"] == blank_type
    assert result["suggested_stock_size"]["display"].endswith(" mm")
    assert all(value > 0 for value in result["allowance_mm"].values())


def test_plan_endpoint_pins_user_candidate_first_and_quotes_every_plan(
    client,
    monkeypatch,
):
    monkeypatch.delenv("TUZI_API_KEY", raising=False)
    response = client.post("/api/v1/quotes/plans", json=_payload(
        user_process_plan={
            "machine": "3轴立式加工中心",
            "setups": 2,
            "operations": ["先面后孔"],
            "process_chain_ref": ["face-pipeline", "hole-pipeline"],
        },
    ))

    assert response.status_code == 200
    body = response.get_json()
    assert body["candidates"][0]["source"] == "user"
    assert body["candidates"][0]["label"] == "用户给定"
    assert len(body["candidates"]) >= 2
    assert len(body["comparison"]) == len(body["candidates"])
    assert body["warnings"]
    for row in body["comparison"]:
        assert row["total_cost"] > 0
        assert row["quoted_amount"] >= row["total_cost"]
        assert row["machining_time_hours"] >= 0
        assert row["setup_count"] >= 1


def test_comparison_amounts_are_taken_from_one_engine_call_per_candidate(
    seeded_conn,
    monkeypatch,
):
    monkeypatch.delenv("TUZI_API_KEY", raising=False)
    calls = []

    def fake_quote(payload, conn, rules_version=""):
        calls.append(payload)
        index = len(calls)
        return {
            "quote": {"cost": 100 + index, "amount": 120 + index},
            "ui_cost": {"machining": 10 + index, "setup": 5},
            "hours": {"total": index / 10},
            "fixture": {"setup_count": index},
        }

    monkeypatch.setattr(plans, "quote", fake_quote)
    result = plans.build_plan_quotes(_payload(), seeded_conn, "test")

    assert len(result["candidates"]) >= 2
    assert len(calls) == len(result["candidates"])
    assert [row["total_cost"] for row in result["comparison"]] == [
        101,
        102,
    ]
    assert [row["quoted_amount"] for row in result["comparison"]] == [
        121,
        122,
    ]


def test_inquiry_part_persists_user_plan_and_embeds_comparison(
    client,
    monkeypatch,
):
    monkeypatch.delenv("TUZI_API_KEY", raising=False)
    inquiry = client.post("/api/v1/inquiries", json={"customer": "一期验收"}).get_json()
    part = client.post(
        f"/api/v1/inquiries/{inquiry['id']}/parts",
        json={
            **_payload(),
            "name": "用户工艺底板",
            "user_process_plan": "先粗铣外形，再加工孔系",
        },
    ).get_json()

    assert part["user_process_plan"] == "先粗铣外形，再加工孔系"
    quoted = client.post(f"/api/v1/parts/{part['id']}/quote", json={})
    assert quoted.status_code == 200
    body = quoted.get_json()
    assert body["quote"]["candidates"][0]["label"] == "用户给定"
    assert len(body["quote"]["comparison"]) >= 2
    assert body["quote"]["blank"]["blank_type"] == "plate"
