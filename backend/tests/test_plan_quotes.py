"""一期毛坯决策与多方案报价合同。"""
import json
import time

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
        use_blank_llm=True,
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
    assert decision["pending"] is False
    assert decision["cache_hit"] is False
    assert decision["decide_normalized_envelope"] is False
    assert decision["llm_rationale"] == "薄板投影，厚度显著小于长宽"
    assert decision["gaps"]
    assert 999 not in decision["allowance_mm"].values()


def test_plan_quotes_default_never_calls_blank_llm(seeded_conn, monkeypatch):
    def unexpected_tuzi(*_args, **_kwargs):
        pytest.fail("默认报价不应调用 blank LLM")

    monkeypatch.setattr(blank_llm, "_tuzi_chat", unexpected_tuzi)
    result = plans.build_plan_quotes(_payload(), seeded_conn, "test")

    assert result["blank"]["source"] == "geometry"
    assert result["blank"]["model"] is None
    assert result["blank"]["pending"] is False
    assert result["blank"]["blank_type"] == "plate"
    assert result["blank"]["suggested_stock_size"]["display"] == "85 × 65 × 16 mm"
    assert result["blank"]["gaps"]


def test_forced_blank_llm_cache_hit_skips_second_tuzi_call(
    seeded_conn,
    monkeypatch,
):
    calls = []

    def fake_tuzi(*_args, **_kwargs):
        calls.append(True)
        return {
            "blank_type": "plate",
            "envelope_mm": {"length": 81, "width": 61, "height": 12},
            "rationale": "缓存测试",
        }

    monkeypatch.setattr(blank_llm, "_tuzi_chat", fake_tuzi)
    payload = _payload(length=81, width=61)
    kwargs = {
        "use_blank_llm": True,
        "step_text": "ISO-10303-21;CACHE-TEST;END-ISO-10303-21;",
    }

    first = plans.build_plan_quotes(payload, seeded_conn, "test", **kwargs)
    second = plans.build_plan_quotes(payload, seeded_conn, "test", **kwargs)

    assert len(calls) == 1
    assert first["blank"]["source"] == "llm"
    assert first["blank"]["cache_hit"] is False
    assert second["blank"]["source"] == "llm"
    assert second["blank"]["cache_hit"] is True
    assert second["blank"]["model"] == "gpt-6-astra"


def test_blank_llm_failure_falls_back_to_geometry_decide(monkeypatch):
    def fail_tuzi(*_args, **_kwargs):
        raise TimeoutError("blank timeout")

    monkeypatch.setattr(blank_llm, "_tuzi_chat", fail_tuzi)
    decision = blank_llm.decide(_payload())

    assert decision["blank_type"] == "plate"
    assert decision["label"] == "板料"
    assert decision["source"] == "geometry"
    assert decision["model"] == "gpt-6-astra"
    assert decision["pending"] is False
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


def test_plan_endpoint_force_blank_llm_uses_explicit_body_flag(
    client,
    monkeypatch,
):
    monkeypatch.delenv("TUZI_API_KEY", raising=False)
    monkeypatch.setattr(
        blank_llm,
        "_tuzi_chat",
        lambda *_args, **_kwargs: {
            "blank_type": "square_bar",
            "envelope_mm": {"length": 84, "width": 60, "height": 30},
            "rationale": "显式刷新测试",
        },
    )

    response = client.post(
        "/api/v1/quotes/plans",
        json={
            **_payload(length=84, height=30),
            "force_blank_llm": True,
        },
    )

    assert response.status_code == 200
    blank_result = response.get_json()["blank"]
    assert blank_result["source"] == "llm"
    assert blank_result["model"] == "gpt-6-astra"
    assert blank_result["pending"] is False


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


def test_forced_llm_blank_does_not_change_comparison_geometry_stock(
    seeded_conn,
    monkeypatch,
):
    monkeypatch.delenv("TUZI_API_KEY", raising=False)
    monkeypatch.setattr(
        blank_llm,
        "_tuzi_chat",
        lambda *_args, **_kwargs: {
            "blank_type": "round_bar",
            "envelope_mm": {"diameter": 60, "length": 82},
            "rationale": "LLM 识别为圆棒",
        },
    )
    quote_payloads = []

    def fake_quote(payload, conn, rules_version=""):
        quote_payloads.append(payload)
        return {
            "quote": {"cost": 100, "amount": 120},
            "ui_cost": {"machining": 10, "setup": 5},
            "hours": {"total": 0.1},
            "fixture": {"setup_count": 1},
        }

    monkeypatch.setattr(plans, "quote", fake_quote)
    result = plans.build_plan_quotes(
        _payload(length=82),
        seeded_conn,
        "test",
        use_blank_llm=True,
        step_text="ISO-10303-21;COMPARISON-ISOLATION;END-ISO-10303-21;",
    )

    assert result["blank"]["blank_type"] == "round_bar"
    assert all(payload["stock_type"] == "板料" for payload in quote_payloads)


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
    assert body["quote"]["blank"]["model"] is None
    assert body["quote"]["blank"]["pending"] is False


def test_part_quote_force_blank_llm_persists_llm_blank(client, monkeypatch):
    monkeypatch.delenv("TUZI_API_KEY", raising=False)
    monkeypatch.setattr(
        blank_llm,
        "_tuzi_chat",
        lambda *_args, **_kwargs: {
            "blank_type": "square_bar",
            "envelope_mm": {"length": 86, "width": 60, "height": 30},
            "rationale": "零件显式刷新",
        },
    )
    inquiry = client.post(
        "/api/v1/inquiries",
        json={"customer": "毛坯刷新"},
    ).get_json()
    part = client.post(
        f"/api/v1/inquiries/{inquiry['id']}/parts",
        json={**_payload(length=86, height=30), "name": "显式刷新件"},
    ).get_json()

    response = client.post(
        f"/api/v1/parts/{part['id']}/quote",
        json={"force_blank_llm": True},
    )

    assert response.status_code == 200
    blank_result = response.get_json()["quote"]["blank"]
    assert blank_result["source"] == "llm"
    assert blank_result["model"] == "gpt-6-astra"
    assert blank_result["pending"] is False


def test_plan_llm_default_model_and_enriched_step_feature_prompt(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return json.dumps({
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "candidates": [{
                                "machine": "3轴立式加工中心",
                                "setups": 2,
                                "operations": ["粗铣基准面", "钻孔"],
                                "process_chain_ref": [
                                    "face-pipeline",
                                    "hole-pipeline",
                                ],
                                "label": "三轴通用",
                                "rationale": "通用设备两次装夹",
                            }],
                        }),
                    },
                }],
            }).encode()

    def fake_urlopen(req, timeout):
        captured["body"] = json.loads(req.data.decode())
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setenv("TUZI_API_KEY", "test-key")
    monkeypatch.delenv("TUZI_PLAN_MODEL", raising=False)
    monkeypatch.setattr(plans.request, "urlopen", fake_urlopen)
    result = plans._request_llm_candidates(
        _payload(features=[
            {
                "type": "hole",
                "feature_id": "hole-0",
                "diameter_mm": 8,
                "depth_mm": 12,
                "position_type": "侧向",
                "axis": {"x": 1, "y": 0, "z": 0},
            },
        ]),
        step_text="ISO-10303-21;PLAN-ROUTE;END-ISO-10303-21;",
        geometry={"bounding_box_mm": {"x": 80, "y": 60, "z": 12}},
    )

    body = captured["body"]
    prompt = body["messages"][1]["content"]
    assert body["model"] == "gpt-6-astra"
    assert captured["timeout"] == plans.PLAN_TIMEOUT_SECONDS_DEFAULT
    assert captured["timeout"] <= 8
    assert "ISO-10303-21;PLAN-ROUTE" in prompt
    assert '"reviewed_features"' in prompt
    assert '"diameter_mm": 8' in prompt
    assert '"depth_mm": 12' in prompt
    assert '"position_type": "侧向"' in prompt
    assert '"setup_hints"' in prompt
    assert '"geometry_bbox_mm": {"x": 80, "y": 60, "z": 12}' in prompt
    assert result[0]["rationale"] == "通用设备两次装夹"


def test_plan_llm_filters_same_route_skin_variants(monkeypatch):
    monkeypatch.setenv("TUZI_API_KEY", "test-key")
    monkeypatch.setattr(
        plans,
        "_bounded_llm_request",
        lambda *_args, **_kwargs: [
            {
                "machine": "3轴立式加工中心",
                "setups": 2,
                "operations": ["粗铣 基准面", "钻孔"],
                "process_chain_ref": ["face-pipeline", "hole-pipeline"],
                "label": "经济方案",
                "rationale": "第一版文案",
            },
            {
                "machine": "3轴立式加工中心",
                "setups": 2,
                "operations": ["粗铣基准面", "钻孔"],
                "process_chain_ref": ["face_pipeline", "hole pipeline"],
                "label": "稳妥方案",
                "rationale": "只是换皮文案",
            },
            {
                "machine": "4轴立式加工中心",
                "setups": 1,
                "operations": ["四轴联动粗铣", "钻孔"],
                "process_chain_ref": ["4axis-face", "hole-pipeline"],
                "label": "少装夹",
                "rationale": "回转轴减少翻面",
            },
        ],
    )

    candidates, warnings = plans.generate_candidates(_payload())

    assert len(candidates) == 2
    assert [candidate["source"] for candidate in candidates] == ["llm", "llm"]
    assert [candidate["label"] for candidate in candidates] == [
        "经济方案",
        "少装夹",
    ]
    assert all(candidate["model"] == "gpt-6-astra" for candidate in candidates)
    assert any("重复路线" in warning for warning in warnings)


def test_plan_llm_failure_returns_rule_fallback(monkeypatch):
    monkeypatch.setenv("TUZI_API_KEY", "test-key")

    def fail(*_args, **_kwargs):
        raise RuntimeError("upstream unavailable")

    monkeypatch.setattr(plans, "_bounded_llm_request", fail)
    candidates, warnings = plans.generate_candidates(_payload())

    assert len(candidates) >= 2
    assert all(candidate["source"] == "rule" for candidate in candidates)
    assert all(candidate["model"] is None for candidate in candidates)
    assert "upstream unavailable" in " ".join(warnings)


def test_plan_slow_llm_hits_short_timeout_and_keeps_user_first(monkeypatch):
    monkeypatch.setenv("TUZI_API_KEY", "test-key")
    monkeypatch.setenv("TUZI_PLAN_TIMEOUT_SECONDS", "0.03")

    def slow(*_args, **_kwargs):
        time.sleep(0.3)
        return []

    monkeypatch.setattr(plans, "_request_llm_candidates", slow)
    started = time.monotonic()
    candidates, warnings = plans.generate_candidates(_payload(
        user_process_plan={
            "machine": "3轴立式加工中心",
            "setups": 2,
            "operations": ["先面后孔"],
            "process_chain_ref": ["face-pipeline", "hole-pipeline"],
        },
    ))
    elapsed = time.monotonic() - started

    assert elapsed < 0.15
    assert len(candidates) >= 2
    assert candidates[0]["source"] == "user"
    assert candidates[0]["model"] is None
    assert any("超时" in warning for warning in warnings)
