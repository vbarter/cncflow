"""九维风险 D2–D5 的冻结规则边界。"""

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
