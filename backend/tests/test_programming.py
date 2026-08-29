"""Word v3 编程工时与成本。"""
import pytest

from cncflow_core.quoting.programming import calculate_cost, calculate_time


def _quote(client, features, **overrides):
    payload = {
        "material": "铝合金",
        "stock_type": "板材",
        "length": 80,
        "width": 60,
        "height": 12,
        "batch_size": 1,
        "features": features,
    }
    payload.update(overrides)
    response = client.post("/api/v1/quotes", json=payload)
    assert response.status_code == 200, response.get_json()
    return response.get_json()


def test_t_base_type_mapping_and_unmapped_type_is_not_counted():
    result = calculate_time([
        {"type": "hole", "feature_id": "hole"},
        {"type": "thread", "feature_id": "thread"},
        {"type": "face", "feature_id": "face"},
        {"type": "plane", "feature_id": "plane"},
        {"type": "step", "feature_id": "step"},
        {"type": "slot", "feature_id": "slot"},
        {"type": "pocket", "feature_id": "pocket"},
        {"type": "surface", "feature_id": "surface"},
        {"type": "pocket_or_step", "feature_id": "unsupported"},
    ], setup_count=1, machine_axes=3)

    minutes = {row["feature_id"]: row["t_base"] for row in result["programming_time_detail"]}
    assert minutes == {
        "hole": 5,
        "thread": 5,
        "face": 8,
        "plane": 8,
        "step": 10,
        "slot": 15,
        "pocket": 15,
        "surface": 25,
    }
    assert "unsupported" not in minutes


def test_difficulty_freeform_and_axes_factors():
    result = calculate_time([
        {"type": "face", "difficulty": {"level": "D2"}},
        {"type": "step", "difficulty_level": "D3"},
        {"type": "surface", "difficulty": "D4", "surface_type": "自由曲面"},
        {"type": "hole", "difficulty": "D4"},
    ], setup_count=2, machine_axes=5)

    feature_minutes = 8 * 1.3 + 10 * 1.8 + 25 * 2.5 * 1.5 + 5
    assert result["programming_time"] == pytest.approx((30 + feature_minutes + 2 * 50) * 1.6)
    assert result["program_count"] == 2


def test_empty_selected_feature_list_has_no_program():
    result = calculate_time([
        {"type": "hole", "selected": False},
        {"type": "face", "selected": False},
    ], setup_count=0, machine_axes=3)
    assert result["programming_time"] == 0
    assert result["program_count"] == 0


@pytest.mark.parametrize(
    ("sample_id", "features", "expected_time", "expected_cost"),
    [
        (
            "0526dade-0448-44b9-8c5d-7a27cce2a1f7",
            [
                {"type": "hole", "feature_id": "hole-0", "selected": True},
                {"type": "face", "feature_id": "face-1", "selected": True},
            ],
            93,
            62.00,
        ),
        (
            "5fbaf21e-16dc-4353-a708-fda46352642c",
            [
                {"type": "slot", "feature_id": "slot-0", "selected": True},
                {"type": "face", "feature_id": "face-0", "selected": True},
            ],
            103,
            68.67,
        ),
        (
            "f6d22246-4224-4c93-8804-b8cdef19085c",
            [
                {"type": "thread", "feature_id": "thread-0", "selected": True},
                {"type": "face", "feature_id": "face-2", "selected": True},
            ],
            93,
            62.00,
        ),
    ],
)
def test_pinned_live_sample_numbers(client, sample_id, features, expected_time, expected_cost):
    body = _quote(client, features)
    items = {item["code"]: item["amount"] for item in body["cost_items"]}
    fixture = body["fixture"]

    assert fixture["method"] == "平口钳", sample_id
    assert fixture["setup_count"] == 1, sample_id
    assert fixture["is_fixture_needed"] is False, sample_id
    assert fixture["fixture_material"] == "-", sample_id
    assert fixture["fixture_count"] == 0, sample_id
    assert (
        fixture["fixture_block_L"],
        fixture["fixture_block_W"],
        fixture["fixture_block_H"],
    ) == (0, 0, 0), sample_id
    assert fixture["datum_face"] is False, sample_id
    assert fixture["clamp_hole_count"] == 0, sample_id
    assert fixture["thread_count"] == 0, sample_id
    assert fixture["profile_mill"] is False, sample_id
    assert fixture["angled_feature_count"] == 0, sample_id
    assert fixture["surface_type"] == "平面", sample_id
    assert fixture["orientation_count"] == 1, sample_id
    assert fixture["fixture_material_cost"] == 0, sample_id
    assert fixture["fixture_processing_cost"] == 0, sample_id
    assert items["FIX"] == 0, sample_id
    assert body["equipment"]["axes"] == 3, sample_id
    assert body["programming_time"] == expected_time, sample_id
    assert body["programming_cost"] == pytest.approx(expected_cost, abs=0.02), sample_id
    assert body["programming_cost_per_piece"] == pytest.approx(expected_cost, abs=0.02)
    assert body["ui_cost"]["programming"] == pytest.approx(expected_cost, abs=0.02)
    assert items["PROG"] == pytest.approx(expected_cost, abs=0.02)
    assert body["formula_trace"]["programming_time"].endswith(f"= {expected_time}")
    assert body["formula_trace"]["programming_cost"].endswith(f"= {expected_cost:g}")
    labor = body["labor_cost_breakdown"]
    assert labor["total"] == pytest.approx(labor["machining"] + labor["setup"], abs=0.02)
    assert labor["total"] == pytest.approx(
        body["ui_cost"]["machining"] + body["ui_cost"]["setup"],
        abs=0.02,
    )


def test_it6_requires_aluminum_fixture_without_changing_programming(client):
    body = _quote(
        client,
        [
            {"type": "hole", "feature_id": "hole-0", "selected": True},
            {"type": "face", "feature_id": "face-1", "selected": True},
        ],
        tolerance_it="IT6",
    )
    fixture = body["fixture"]
    items = {item["code"]: item["amount"] for item in body["cost_items"]}

    assert fixture["is_fixture_needed"] is True
    assert fixture["fixture_material"] == "铝合金"
    assert fixture["fixture_count"] == 1
    assert (
        fixture["fixture_block_L"],
        fixture["fixture_block_W"],
        fixture["fixture_block_H"],
    ) == (120, 100, 42)
    assert fixture["datum_face"] is True
    assert fixture["clamp_hole_count"] == 2
    assert fixture["thread_count"] == 2
    assert fixture["profile_mill"] is False
    assert fixture["angled_feature_count"] == 0
    assert fixture["surface_type"] == "平面"
    assert fixture["fixture_orientation_count"] == 1
    # AL-01: 120*100*42 mm³ * 2.70 g/cm³ / 1e6 * ¥30/kg = ¥40.824。
    assert fixture["fixture_material_cost"] == pytest.approx(40.82, abs=0.01)
    assert fixture["fixture_processing_cost"] == 0
    assert items["FIX"] == pytest.approx(40.82, abs=0.01)
    assert body["programming_time"] == 93
    assert body["programming_cost"] == pytest.approx(62, abs=0.02)


def test_o8_material_cost_uses_full_scrap_value_without_eta(client):
    body = _quote(
        client,
        [
            {"type": "hole", "feature_id": "hole-0", "selected": True},
            {"type": "face", "feature_id": "face-1", "selected": True},
        ],
        # 现网 Ø8 样本的 CAD 体积字段；保持现有询价数据路径和单位行为不变。
        v_part_cad=56.997,
    )
    items = {item["code"]: item["amount"] for item in body["cost_items"]}
    material = body["material_cost_breakdown"]

    # 0.2322 kg×¥30/kg − 0.2321 kg×¥16/kg = ¥3.2524 → ¥3.25。
    assert material == {
        "density_g_cm3": 2.7,
        "blank_price_per_kg": 30,
        "scrap_price_per_kg": 16,
        "blank_volume_mm3": 86016,
        "blank_weight_kg": 0.2322,
        "part_volume_mm3": 56.997,
        "part_weight_kg": 0.00015,
        "scrap_volume_mm3": 85959.003,
        "scrap_weight_kg": 0.2321,
        "blank_cost": 6.97,
        "scrap_recycle_cost": 3.71,
        "net_material_cost": 3.25,
    }
    assert items["MAT"] == pytest.approx(3.25, abs=0.01)
    assert body["ui_cost"]["material"] == pytest.approx(3.25, abs=0.01)
    assert material["net_material_cost"] == items["MAT"]
    assert body["programming_time"] == 93
    assert body["programming_cost"] == pytest.approx(62, abs=0.02)


def test_o8_labor_trace_reconciles_live_machining_and_changeover(tmp_path):
    from app import create_app
    from cncflow_core.common.db import get_conn
    from data.seed_tools import seed

    db_path = tmp_path / "o8-labor.db"
    conn = get_conn(db_path)
    seed(conn)
    conn.close()
    client = create_app(db_path=str(db_path)).test_client()
    body = _quote(
        client,
        [
            {
                "type": "hole",
                "feature_id": "hole-0",
                "diameter_mm": 8,
                "depth_mm": 12,
                "hole_type": "through",
                "selected": True,
            },
            {
                "type": "face",
                "feature_id": "face-1",
                "length": 80,
                "width": 60,
                "selected": True,
            },
        ],
    )
    labor = body["labor_cost_breakdown"]
    groups = {group["feature_type"]: group for group in labor["groups"]}
    hole_ops = groups["hole"]["operations"]
    face_ops = groups["face"]["operations"]

    assert body["ui_cost"]["machining"] == 1.39
    assert body["ui_cost"]["setup"] == 210
    assert labor["machining_total"] == 1.39
    assert labor["operation_cost"] == 1.22
    assert labor["air_cut_and_tool_change_cost"] == 0.17
    assert labor["total"] == 211.39
    assert [(group["name"], group["quantity"]) for group in labor["groups"]] == [
        ("孔", 1),
        ("面", 1),
    ]
    assert [
        (op["name"], op["tool_sku"], op["minutes"], op["cost"])
        for op in hole_ops
    ] == [("钻孔", "TK-003", 0.0902, 0.18)]
    assert [
        (op["name"], op["tool_sku"], op["minutes"], op["cost"])
        for op in face_ops
    ] == [
        ("粗铣", "TK-028", 0.2193, 0.44),
        ("倒角", "TK-036", 0.3016, 0.60),
    ]
    assert labor["changeover"] == {
        "minutes": 5.0,
        "equipment_name": "VMC850E",
        "hourly_rate": 120.0,
        "labor_cost": 10.0,
        "machine_setup_cost": 200.0,
        "cost": 210.0,
    }
    assert labor["machining_total"] + labor["changeover"]["cost"] == labor["total"]


def test_deselect_hole_recalculates_programming(client):
    body = _quote(client, [
        {"type": "hole", "feature_id": "hole-0", "selected": False},
        {"type": "face", "feature_id": "face-1", "selected": True},
    ])
    assert body["programming_time"] == 88
    assert body["programming_cost"] == pytest.approx(58.67, abs=0.02)


def test_repeat_order_keeps_time_and_zeros_cost(client):
    body = _quote(
        client,
        [
            {"type": "hole", "feature_id": "hole-0", "selected": True},
            {"type": "face", "feature_id": "face-1", "selected": True},
        ],
        is_repeat_order=True,
    )
    assert body["programming_time"] == 93
    assert body["programming_cost"] == 0
    assert body["programming_cost_per_piece"] == 0
    assert body["ui_cost"]["programming"] == 0


def test_programming_cost_uses_valid_override_and_defaults_invalid_rate():
    overridden = calculate_cost(90, machine_axes=4, rate_row={"programming_hourly_rate": 80})
    fallback = calculate_cost(90, machine_axes=4, rate_row={"programming_hourly_rate": 0})
    assert overridden["programming_cost"] == 120
    assert fallback["programming_cost"] == 90
