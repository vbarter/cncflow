"""报价引擎：体积公式、始终出价、滑轴、翻单。"""
import math

import pytest

from cncflow_core.quoting.engine import suggested_lead_time_days


def quote(client, payload):
    return client.post("/api/v1/quotes", json=payload)


@pytest.mark.parametrize(
    (
        "sample", "dimensions", "features", "v_part_cad", "names",
            "processes", "sku_pins", "machining", "material",
    ),
    [
        (
            "Ø8",
            (80, 60, 12),
            [
                {
                    "type": "hole",
                    "feature_id": "hole-0",
                    "diameter_mm": 8,
                    "depth_mm": 12,
                    "hole_type": "through",
                },
                {
                    "type": "face",
                    "feature_id": "face-1",
                    "length": 80,
                    "width": 60,
                },
            ],
            56_997,
            ["面粗", "钻孔", "倒角"],
            ["rough_face", "drill", "chamfer"],
            {},
            211.39,
            5.72,
        ),
        (
            "M8",
            (40, 40, 12),
            [
                {
                    "type": "thread",
                    "feature_id": "thread-0",
                    "nominal_d": 8,
                    "pitch": 1.25,
                    "thread_length": 12,
                },
                {
                    "type": "face",
                    "feature_id": "face-2",
                    "length": 40,
                    "width": 40,
                },
            ],
            18.757003,
            ["面粗", "底孔", "攻牙", "倒角"],
            ["rough_face", "drill", "tap", "chamfer"],
            {"tap": "TK-033"},
            211.19,
            1.17,
        ),
        (
            "开口槽",
            (80, 60, 12),
            [
                {
                    "type": "slot",
                    "feature_id": "slot-0",
                    "length": 40,
                    "width": 10,
                    "depth": 8,
                    "corner_radius": 3,
                    "pocket_type": "开放",
                },
                {
                    "type": "face",
                    "feature_id": "face-0",
                    "length": 80,
                    "width": 60,
                },
            ],
            54.430702,
            ["槽粗", "面粗", "倒角"],
            ["rough_pocket", "rough_face", "chamfer"],
            {
                "rough_pocket": "TK-022",
                "rough_face": "TK-028",
                "chamfer": "TK-036",
            },
            211.59,
            None,
        ),
    ],
)
def test_frozen_live_quote_pins(
    client,
    sample,
    dimensions,
    features,
    v_part_cad,
    names,
    processes,
    sku_pins,
    machining,
    material,
):
    length, width, height = dimensions
    body = quote(
        client,
        {
            "material": "铝合金",
            "stock_type": "板材",
            "length": length,
            "width": width,
            "height": height,
            "v_part_cad": v_part_cad,
            "features": features,
        },
    ).get_json()

    assert [step["name"] for step in body["process_sequence"]] == names, sample
    assert [step["process"] for step in body["process_sequence"]] == processes, sample
    by_process = {step["process"]: step for step in body["process_sequence"]}
    assert {
        process: by_process[process]["sku"]
        for process in sku_pins
    } == sku_pins, sample
    assert sum(step["process"] == "chamfer" for step in body["process_sequence"]) == 1
    assert body["labor_cost_breakdown"]["total"] == pytest.approx(
        machining,
        abs=0.01,
    ), sample
    assert not {"ream", "thread_mill"} & {
        step["process"] for step in body["process_sequence"]
    }, sample
    if sample != "M8":
        assert "tap" not in {
            step["process"] for step in body["process_sequence"]
        }, sample

    if material is not None:
        assert body["material_cost_breakdown"]["net_material_cost"] == pytest.approx(
            material,
            abs=0.01,
        ), sample
    if sample == "Ø8":
        assert body["volume"]["v_part_mm3"] == 56_997
        assert body["volume"]["v_blank_mm3"] == 86_016
        assert body["programming_time"] == 93
        assert body["programming_cost"] == pytest.approx(62, abs=0.01)
        assert body["confidence"] == 90
        tags = body["risk"]["tags"]
        assert all(
            tag == "低于下限"
            or "刀径非全等" in tag
            or ("库存无 Ø8mm 全等刀具" in tag and "需工艺确认" in tag)
            for tag in tags
        )
        assert not any(
            banned in tag
            for tag in tags
            for banned in ("超高速", "转速不足", "深腔", "可达性", "长悬伸", "刚性不足")
        )
    if sample == "M8":
        tap = next(step for step in body["process_sequence"] if step["process"] == "tap")
        assert tap["sku"] == "TK-033"


def test_nuc_mounting_plate_groups_holes_and_uses_net_face_area(client):
    features = [
        {
            "type": "hole",
            "feature_id": f"hole-{index}",
            "diameter_mm": 2.5,
            "depth_mm": 3.5,
            "hole_type": "through",
        }
        for index in range(18)
    ]
    features.append({
        "type": "face",
        "feature_id": "face-0",
        "length": 285,
        "width": 128,
    })
    body = quote(client, {
        "material": "铝合金",
        "stock_type": "板材",
        "length": 285,
        "width": 128,
        "height": 3.5,
        "v_part_cad": 70_641,
        "features": features,
    }).get_json()

    assert body["volume"]["v_part_mm3"] == 70_641
    assert body["material_cost_breakdown"]["net_material_cost"] == pytest.approx(
        13.86,
        abs=0.01,
    )
    face = next(plan["plan"] for plan in body["features"] if plan["type"] == "face")
    assert face["metrics"]["area"] == 20_183
    rough_face = next(
        step for step in body["process_sequence"] if step["process"] == "rough_face"
    )
    assert rough_face["time"]["cut"] == pytest.approx(360.4107, abs=0.01)
    assert rough_face["time"]["cut"] == pytest.approx(20_183 / (0.7 * 80), abs=0.01)
    assert rough_face["time"]["cut"] != pytest.approx(
        285 * 128 / (0.7 * 80),
        abs=0.01,
    )
    assert rough_face["time"]["t_cut"] == pytest.approx(0.57, abs=0.03)

    for process in ("spot_drill", "drill"):
        steps = [
            step for step in body["process_sequence"] if step["process"] == process
        ]
        assert len(steps) == 1
        assert steps[0]["quantity"] == 18
        assert steps[0]["time"]["t_tool"] == pytest.approx(5 / 60, abs=0.0001)
    chamfer = next(
        step for step in body["process_sequence"] if step["process"] == "chamfer"
    )
    assert chamfer["minutes"] == pytest.approx(0.25, abs=0.08)
    # Seeded equipment picks DMU65, unlike the live NUC factory config. The
    # grouped operation row itself remains the expected ~¥5.5; live retest adds
    # the unchanged ¥48.67 changeover for a total of about ¥54.
    assert body["labor_cost_breakdown"]["machining_total"] == pytest.approx(
        5.5,
        abs=0.2,
    )


def test_nuc_live_setup_freezes_machining_54_23(tmp_path):
    from app import create_app
    from cncflow_core.common.db import get_conn

    db_path = tmp_path / "nuc-live.db"
    live_client = create_app(db_path=str(db_path)).test_client()
    conn = get_conn(db_path)
    conn.execute("UPDATE machines SET setup_fee = 30 WHERE id = 'DMU65'")
    conn.execute(
        "UPDATE rate_table SET setup_fee = 30 "
        "WHERE equipment_type = '5轴联动加工中心'"
    )
    conn.commit()
    conn.close()
    features = [
        {
            "type": "hole",
            "feature_id": f"hole-{index}",
            "diameter_mm": 2.5,
            "depth_mm": 3.5,
            "hole_type": "through",
        }
        for index in range(18)
    ]
    features.append({
        "type": "face",
        "feature_id": "face-0",
        "length": 285,
        "width": 128,
    })

    body = quote(live_client, {
        "material": "铝合金",
        "stock_type": "板材",
        "length": 285,
        "width": 128,
        "height": 3.5,
        "v_part_cad": 70_641,
        "features": features,
    }).get_json()

    assert body["labor_cost_breakdown"]["total"] == pytest.approx(54.23, abs=0.01)
    assert body["material_cost_breakdown"]["net_material_cost"] == pytest.approx(13.86, abs=0.01)
    assert body["volume"]["v_part_mm3"] == 70_641


@pytest.mark.parametrize(
    ("feature", "risk_override", "safe_override", "tag"),
    [
        (
            {"type": "hole", "diameter_mm": 0.5, "depth_mm": 2},
            {"machine_max_rpm": 29_999},
            {"machine_max_rpm": 30_000},
            "需要超高速切削中心",
        ),
        (
            {"type": "hole", "diameter_mm": 1, "depth_mm": 2},
            {"machine_max_rpm": 19_999},
            {"machine_max_rpm": 20_000},
            "主轴转速不足",
        ),
        (
            {
                "type": "hole",
                "diameter_mm": 10,
                "depth_mm": 20,
                "position_type": "深腔",
            },
            {"hole_bottom_distance_from_opening_mm": 50.01},
            {"hole_bottom_distance_from_opening_mm": 50},
            "需要刀具可达性检查",
        ),
        (
            {"type": "hole", "diameter_mm": 10, "depth_mm": 50},
            {"long_overhang": True},
            {"long_overhang": False},
            "刚性不足",
        ),
    ],
)
def test_r08_r09_r14_r16_tags_do_not_deduct_confidence(
    client,
    feature,
    risk_override,
    safe_override,
    tag,
):
    base = {
        "material": "铝合金",
        "stock_type": "板材",
        "length": 80,
        "width": 60,
        "height": 12,
    }
    risk_feature = {**feature, **{
        key: value
        for key, value in risk_override.items()
        if key not in {"machine_max_rpm"}
    }}
    safe_feature = {**feature, **{
        key: value
        for key, value in safe_override.items()
        if key not in {"machine_max_rpm"}
    }}
    risk_body = quote(client, {
        **base,
        **{key: value for key, value in risk_override.items() if key == "machine_max_rpm"},
        "features": [risk_feature],
    }).get_json()
    safe_body = quote(client, {
        **base,
        **{key: value for key, value in safe_override.items() if key == "machine_max_rpm"},
        "features": [safe_feature],
    }).get_json()

    assert tag in risk_body["risk"]["tags"]
    assert tag not in safe_body["risk"]["tags"]
    assert risk_body["confidence"] == safe_body["confidence"]
    assert risk_body["process_sequence"]


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
