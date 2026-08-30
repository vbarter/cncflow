"""九维风险 D2–D8 的冻结规则边界。"""

import pytest

from cncflow_core.quoting import risk_dimensions


@pytest.mark.parametrize(
    ("removed_mm3", "cut_minutes"),
    [
        (12_000_001, 1),  # > 200,000 mm³/s
        (0.59, 1),  # < 0.01 mm³/s
    ],
)
def test_d2_mrr_outside_frozen_band_deducts(removed_mm3, cut_minutes):
    deductions = risk_dimensions.collect_d2(
        {"v_removed_mm3": removed_mm3},
        cut_minutes,
    )

    assert len(deductions) == 1
    assert deductions[0]["rule_id"] == "D2-1"
    assert deductions[0]["deduction"] == 5


@pytest.mark.parametrize(
    ("removed_mm3", "cut_minutes"),
    [
        (0.6, 1),  # exactly 0.01 mm³/s
        (12_000_000, 1),  # exactly 200,000 mm³/s
    ],
)
def test_d2_mrr_band_is_inclusive(removed_mm3, cut_minutes):
    assert risk_dimensions.collect_d2(
        {"v_removed_mm3": removed_mm3},
        cut_minutes,
    ) == []


def test_d3_absurd_cost_shares_deduct_independently():
    deductions = risk_dimensions.collect_d3(
        100,
        {
            "material": 80.01,
            "machining": 80.01,
            "fixture": 50.01,
        },
    )

    assert {item["rule_id"] for item in deductions} == {"D3-1", "D3-2", "D3-3"}
    assert all(item["deduction"] == 5 for item in deductions)
    assert risk_dimensions.D3_SHARE_MAX == {
        "material": 0.80,
        "machining": 0.80,
        "fixture": 0.50,
    }


def test_d4_existing_equipment_mismatch_signal_deducts_once():
    deductions = risk_dimensions.collect_d4(["设备不匹配", "设备不匹配"])

    assert len(deductions) == 1
    assert deductions[0]["rule_id"] == "D4-1"
    assert deductions[0]["deduction"] == 10


@pytest.mark.parametrize(
    "tag",
    [
        "需要超高速切削中心",
        "主轴转速不足",
        "需要刀具可达性检查",
        "干涉风险",
        "刚性不足",
    ],
)
def test_r08_r16_risk_tags_do_not_trigger_equipment_deduction(tag):
    assert risk_dimensions.collect_d4([tag]) == []


@pytest.mark.parametrize(
    "step",
    [
        {"order": 1, "process": "drill", "n": 0, "f": 100},
        {"order": 1, "process": "drill", "n": 1000, "f": -1},
    ],
)
def test_d5_nonpositive_cutting_parameter_deducts(step):
    deductions = risk_dimensions.collect_d5([step])

    assert len(deductions) == 1
    assert deductions[0]["rule_id"] == "D5-1"
    assert deductions[0]["deduction"] == 5


def test_d5_missing_parameters_do_not_deduct():
    assert risk_dimensions.collect_d5([
        {"order": 1, "process": "manual"},
        {"order": 2, "process": "chamfer", "n": None, "f": ""},
    ]) == []


@pytest.mark.parametrize(
    "steps",
    [
        [
            {"order": 1, "process": "finish_face"},
            {"order": 2, "process": "rough_face"},
        ],
        [
            {"order": 1, "process": "rough_face"},
            {"order": 2, "process": "chamfer"},
            {"order": 3, "process": "drill"},
        ],
    ],
)
def test_d6_invalid_order_in_same_setup_deducts_once(steps):
    deductions = risk_dimensions.collect_d6(steps)

    assert len(deductions) == 1
    assert deductions[0]["rule_id"] == "D6-1"
    assert deductions[0]["deduction"] == 5


def test_d6_checks_each_explicit_setup_group_independently():
    assert risk_dimensions.collect_d6([
        {"order": 1, "process": "chamfer", "setup_group": "A"},
        {"order": 2, "process": "rough_face", "setup_group": "B"},
    ]) == []


@pytest.mark.parametrize("material_cost", [0, -1, 100.01])
def test_d7_absurd_material_cost_deducts(material_cost):
    deductions = risk_dimensions.collect_d7(
        100,
        {"material": material_cost},
    )

    assert len(deductions) == 1
    assert deductions[0]["rule_id"] == "D7-1"
    assert deductions[0]["deduction"] == 5


def test_d8_missing_equipment_deducts():
    deductions = risk_dimensions.collect_d8(
        [{"minutes": 1}],
        equipment={"model": None, "type": "3轴立式加工中心", "hourly_rate": 120},
        hours_cut=1 / 60,
    )

    assert len(deductions) == 1
    assert deductions[0]["rule_id"] == "D8-1"
    assert deductions[0]["deduction"] == 5
    assert deductions[0]["missing_equipment_fields"] == ["model"]


def test_d8_hours_minutes_mismatch_deducts_beyond_half_minute():
    deductions = risk_dimensions.collect_d8(
        [{"minutes": 1}, {"minutes": 2}],
        equipment={"model": "VMC850E", "type": "3轴立式加工中心", "hourly_rate": 120},
        hours_cut=3.51 / 60,
    )

    assert len(deductions) == 1
    assert deductions[0]["rule_id"] == "D8-1"
    assert deductions[0]["mismatch_minutes"] == pytest.approx(0.51)


def test_d8_half_minute_difference_is_allowed():
    assert risk_dimensions.collect_d8(
        [{"minutes": 3}],
        equipment={"model": "VMC850E", "type": "3轴立式加工中心", "hourly_rate": 120},
        hours_cut=3.5 / 60,
    ) == []


def test_quote_engine_wires_d2_from_removed_volume_and_cut_minutes(client):
    body = client.post("/api/v1/quotes", json={
        "material": "铝合金",
        "stock_type": "板材",
        "length": 80,
        "width": 60,
        "height": 12,
        # 84 * 64 * 16 = 86,016 mm³ blank，留下 0.1 mm³ 去除量。
        "v_part_cad": 86_015.9,
        "features": [{"type": "face", "length": 80, "width": 60}],
    }).get_json()

    assert body["status"] == "quoted"
    assert body["quote"]["amount"] > 0
    assert [item["rule_id"] for item in body["deductions"] if item["dimension"] == "D2"] == ["D2-1"]


def test_quote_engine_wires_d3_from_quote_cost_shares(client):
    body = client.post("/api/v1/quotes", json={
        "material": "铝合金",
        "stock_type": "板材",
        "length": 80,
        "width": 60,
        "height": 12,
        "price_per_kg": 1_000_000_000,
        "features": [{"type": "face", "length": 80, "width": 60}],
    }).get_json()

    assert body["status"] == "quoted"
    assert body["quote"]["amount"] > 0
    assert [item["rule_id"] for item in body["deductions"] if item["dimension"] == "D3"] == ["D3-1"]


def test_quote_engine_wires_d7_and_still_quotes_absurd_material(client):
    body = client.post("/api/v1/quotes", json={
        "material": "铝合金",
        "stock_type": "板材",
        "length": 80,
        "width": 60,
        "height": 12,
        "price_per_kg": 0,
        "features": [{"type": "face", "length": 80, "width": 60}],
    }).get_json()

    assert body["status"] == "quoted"
    assert body["quote"]["amount"] > 0
    assert [item["rule_id"] for item in body["deductions"] if item["dimension"] == "D7"] == ["D7-1"]
