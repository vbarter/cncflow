"""一期毛坯决策与多方案报价合同。"""
import pytest

from cncflow_core.quoting import blank, blank_llm, plans


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


def test_plan_blank_llm_plate_uses_step_and_then_existing_decide(
    seeded_conn,
    monkeypatch,
    tmp_path,
):
    step_path = tmp_path / "plate.step"
    step_path.write_text(
        "ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;",
        encoding="ascii",
    )
    captured = {}

    def fake_tuzi(messages, model=None):
        captured["messages"] = messages
        captured["model"] = model
        return {
            "blank_type": "plate",
            "envelope_mm": {"length": 80, "width": 60, "height": 12},
            "rationale": "薄板投影，厚度显著小于长宽",
            "allowance_mm": 999,
            "unit_price": 999,
        }

    monkeypatch.setattr(blank_llm, "_tuzi_chat", fake_tuzi)
    result = plans.build_plan_quotes(
        _payload(),
        seeded_conn,
        "test",
        step_path=str(step_path),
    )
    decision = result["blank"]

    assert captured["model"] == "gpt-6-astra"
    assert "ISO-10303-21" in str(captured["messages"])
    assert decision["blank_type"] == "plate"
    assert decision["label"] == "板料"
    assert decision["envelope_mm"] == {
        "length": 80,
        "width": 60,
        "height": 12,
    }
    assert decision["allowance_mm"] == {
        "length_each_side": 2,
        "width_each_side": 2,
        "height_each_side": 2,
    }
    assert decision["suggested_stock_size"]["display"] == "85 × 65 × 16 mm"
    assert decision["source"] == "llm"
    assert decision["model"] == "gpt-6-astra"
    assert decision["decide_normalized_envelope"] is False
    assert decision["llm_rationale"] == "薄板投影，厚度显著小于长宽"
    assert decision["gaps"]
    assert 999 not in decision["allowance_mm"].values()


def test_blank_llm_failure_falls_back_to_geometry_decide(monkeypatch):
    def fail_tuzi(*_args, **_kwargs):
        raise TimeoutError("blank timeout")

    monkeypatch.setattr(blank_llm, "_tuzi_chat", fail_tuzi)
    decision = blank_llm.decide(_payload())

    assert decision["blank_type"] == "plate"
    assert decision["label"] == "板料"
    assert decision["source"] == "geometry"
    assert decision["model"] == "gpt-6-astra"
    assert decision["suggested_stock_size"]["display"] == "85 × 65 × 16 mm"
    assert decision["llm_error"] == "blank timeout"


def test_blank_llm_round_bar_maps_diameter_and_length(monkeypatch):
    monkeypatch.setattr(
        blank_llm,
        "_tuzi_chat",
        lambda *_args, **_kwargs: {
            "blank_type": "round_bar",
            "envelope_mm": {"diameter": 48, "length": 190},
            "rationale": "回转体长径比高",
        },
    )
    decision = blank_llm.decide(_payload())

    assert decision["blank_type"] == "round_bar"
    assert decision["label"] == "圆棒"
    assert decision["envelope_mm"] == {"length": 190, "diameter": 48}
    assert decision["allowance_mm"] == {
        "radial_each_side": 3,
        "end_each_side": 3,
    }
    assert decision["suggested_stock_size"]["display"] == "Ø55 × 200 mm"
    assert decision["source"] == "llm"
    assert decision["gaps"] == [
        "标准库存长度表缺失：length 使用现有 5 mm 向上取整启发式"
    ]


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
    assert body["quote"]["blank"]["source"] == "geometry"
