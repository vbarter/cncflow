"""LLM 特征映射 + parse 主路径。不打真 tu-zi。"""
import json
import os

import pytest

from cncflow_core.geometry.llm import (
    build_messages,
    map_llm_features,
    read_step_ascii,
)
from cncflow_core.inquiries.api import _review_and_quote_features


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
LLM_D8 = os.path.join(FIXTURES, "llm_plate_hole_d8.json")
STEP_D8 = os.path.join(FIXTURES, "plate_hole_d8.step")
OPEN_SLOT_STEP = os.path.join(FIXTURES, "rect_open_slot.step")


def _fixture_payload():
    with open(LLM_D8, encoding="utf-8") as fh:
        return json.load(fh)


def test_map_llm_plate_hole_d8_fixture_fields():
    mapped = map_llm_features(_fixture_payload())
    by_type = {feat["type"]: feat for feat in mapped["features"]}
    hole = by_type["hole"]
    assert hole["feature_id"] == "hole-0"
    assert hole["subtype"] == "recognized_hole"
    assert hole["diameter_mm"] == 8
    assert hole["depth_mm"] == 12
    assert hole["hole_type"] == "through"
    assert hole["position_type"] == "垂直"
    assert hole["surface"] == "top"
    assert hole["cut_depth_mm"] == pytest.approx(14.4)
    assert hole["selected"] is True
    assert hole["pose"]["diameter_mm"] == 8

    face = by_type["face"]
    assert face["feature_id"] == "face-0"
    assert face["subtype"] == "recognized_face"
    assert face["length"] == 80
    assert face["width"] == 60
    assert face["area"] == 4800
    assert face["face_position"] == "水平"
    assert face["selected"] is True

    od = by_type["outer_cylinder"]
    assert od["feature_id"] == "od-0"
    assert od["subtype"] == "boss_or_od"
    assert od["selected"] is False
    assert od["diameter_mm"] == 80


def test_map_llm_fixture_review_and_quote_pins(client):
    features = map_llm_features(_fixture_payload())["features"]
    review, quoted = _review_and_quote_features(features, None, 80, 60, 12)
    assert {feat["feature_id"] for feat in review} == {"hole-0", "face-0", "od-0"}
    assert [feat["type"] for feat in quoted] == ["hole", "face"]
    hole = quoted[0]
    assert hole["cut_depth_mm"] == pytest.approx(14.4)
    assert hole["hole_type"] == "through"

    body = client.post("/api/v1/quotes", json={
        "material": "铝合金",
        "stock_type": "板材",
        "length": 80,
        "width": 60,
        "height": 12,
        "v_part_cad": 56_997,
        "features": quoted,
    }).get_json()
    assert body["labor_cost_breakdown"]["total"] == pytest.approx(211.39, abs=0.01)
    assert body["ui_cost"]["inspect"] == body["ui_cost"]["toolwear"] == body["ui_cost"]["scrap"] == 0


@pytest.mark.parametrize(
    ("raw", "expect_type", "expect_id"),
    [
        ({"type": "螺纹", "diameter_mm": 8, "pitch": 1.25, "thread_length": 12}, "thread", "thread-0"),
        ({"type": "slot", "length": 40, "width": 10, "depth": 8, "corner_radius": 3, "pocket_type": "开放"}, "slot", "slot-0"),
        ({"type": "台阶轮廓", "length": 80, "height": 8, "width": 25}, "step", "step-0"),
        ({"type": "曲面", "surface_type": "凸面", "curvature_radius": 20, "position": "顶面"}, "surface", "surface-0"),
        ({"type": "pocket", "length": 24, "width": 12, "depth": 6, "pocket_type": "封闭"}, "pocket", "slot-0"),
    ],
)
def test_map_handbook_type_aliases(raw, expect_type, expect_id):
    mapped = map_llm_features({"features": [raw]})["features"][0]
    assert mapped["type"] == expect_type
    assert mapped["feature_id"] == expect_id
    assert mapped["subtype"].startswith("recognized_") or mapped["subtype"] == "boss_or_od"


def test_map_llm_empty_or_garbage_is_visible_failure():
    with pytest.raises(ValueError, match="缺少 features"):
        map_llm_features({})
    with pytest.raises(ValueError, match="未产出可用特征"):
        map_llm_features({"features": []})
    with pytest.raises(ValueError, match="未产出可用特征"):
        map_llm_features({"features": [{"type": "hole", "diameter_mm": 0, "depth_mm": 12}]})
    with pytest.raises(ValueError, match="不是 JSON"):
        from cncflow_core.geometry.llm import _json_object
        _json_object("not-json")


def test_map_llm_skips_unknown_keeps_valid():
    mapped = map_llm_features({
        "features": [
            {"type": "chamfer"},
            {"type": "hole", "diameter_mm": 6, "depth_mm": 10, "hole_type": "盲孔", "position_type": "侧向"},
        ],
    })
    assert [feat["feature_id"] for feat in mapped["features"]] == ["hole-0"]
    assert mapped["features"][0]["hole_type"] == "blind"
    assert mapped["features"][0]["surface"] == "side"
    assert mapped["errors"]


def test_read_step_ascii_and_messages_use_text_not_files():
    text, truncated = read_step_ascii(STEP_D8)
    assert truncated is False
    assert "ISO-10303-21" in text
    assert "CARTESIAN_POINT" in text
    messages = build_messages(text, geometry={"bounding_box_mm": {"x": 80, "y": 60, "z": 12}, "volume_cm3": 55})
    blob = json.dumps(messages, ensure_ascii=False)
    assert "ISO-10303-21" in blob
    assert "bbox_mm=80×60×12" in blob
    assert "孔" in blob and "滑轴" in blob and "槽腔" in blob
    assert "两侧壁平行" in blob
    assert "deterministic-open-slot-rescue" not in blob
    assert '"pocket_type":"开放"' in blob


@pytest.mark.llm_features
def test_parse_step_file_llm_primary_maps_fixture(monkeypatch, tmp_path):
    from cncflow_core.geometry import llm as llm_mod
    from cncflow_core.geometry.service import parse_step_file
    from cncflow_core.ingestion import step_parser

    monkeypatch.setattr(step_parser, "parse_step", lambda path: {
        "geometry": {"volume_cm3": 55.0, "bounding_box_mm": {"x": 80, "y": 60, "z": 12}},
        "features": [],
        "warnings": [],
    })
    monkeypatch.setattr(llm_mod, "_tuzi_chat", lambda messages, model=None: _fixture_payload())
    step = tmp_path / "plate.step"
    step.write_text(open(STEP_D8, encoding="ascii", errors="replace").read(), encoding="ascii")
    result = parse_step_file(str(step))
    assert result["parser"] == "geometry-service"
    assert result["feature_source"] == "llm"
    assert result["llm"]["ok"] is True
    assert result["llm"]["model"] == "gpt-6-astra" or result["llm"]["called"]
    types = {feat["type"] for feat in result["features"]}
    assert {"hole", "face", "outer_cylinder"} <= types
    hole = next(feat for feat in result["features"] if feat["type"] == "hole")
    assert hole["subtype"] == "recognized_hole"
    assert hole["cut_depth_mm"] == pytest.approx(14.4)
    ods = [feat for feat in result["features"] if feat["type"] == "outer_cylinder"]
    assert ods and ods[0]["selected"] is False


@pytest.mark.llm_features
def test_parse_step_file_llm_open_slot_fixture_maps_slot_v1(monkeypatch):
    from cncflow_core.geometry import llm as llm_mod
    from cncflow_core.geometry import service as service_mod
    from cncflow_core.ingestion import step_parser

    monkeypatch.setattr(step_parser, "parse_step", lambda path: {
        "geometry": {
            "volume_cm3": 53.6,
            "bounding_box_mm": {"x": 80, "y": 60, "z": 12},
            "face_count": 16,
        },
        "features": [],
        "warnings": [],
    })
    monkeypatch.setattr(llm_mod, "_tuzi_chat", lambda messages, model=None: {
        "features": [
            {
                "type": "face",
                "length": 80,
                "width": 60,
                "face_position": "水平",
            },
            {
                "type": "slot",
                "pocket_type": "开放",
                "length": 40.1,
                "width": 10,
                "depth": 8,
                "corner_radius": 3,
                "location": {"x": -20, "y": 0, "z": 4},
                "axis": {"x": 0, "y": 0, "z": 1},
            },
        ],
    })
    monkeypatch.setattr(
        service_mod,
        "run_slot",
        lambda path: (_ for _ in ()).throw(AssertionError("已有槽时不应运行修复")),
    )

    result = service_mod.parse_step_file(OPEN_SLOT_STEP)

    slot = next(
        feat for feat in result["features"]
        if feat.get("subtype") == "recognized_slot"
    )
    assert slot["type"] == "slot"
    assert slot["pocket_type"] == "开放"
    assert slot["length"] == pytest.approx(40, abs=1.5)
    assert slot["width"] == pytest.approx(10, abs=1.5)
    assert slot["depth"] == pytest.approx(8, abs=1.5)
    assert slot["corner_radius"] == pytest.approx(3, abs=0.6)
    assert slot["location"] == {"x": -20, "y": 0, "z": 4}
    assert result["llm"]["repaired_open_slots"] == 0


@pytest.mark.llm_features
@pytest.mark.parametrize(
    "wrong_feature",
    [
        {"type": "surface", "surface_type": "B_SPLINE_SURFACE", "position": "顶面"},
        {"type": "outer_cylinder", "diameter_mm": 6, "depth_mm": 10},
    ],
)
def test_parse_step_file_repairs_previous_open_slot_failure_modes(
    monkeypatch,
    wrong_feature,
):
    from cncflow_core.geometry import llm as llm_mod
    from cncflow_core.geometry import service as service_mod
    from cncflow_core.ingestion import step_parser

    monkeypatch.setattr(step_parser, "parse_step", lambda path: {
        "geometry": {
            "volume_cm3": 53.6,
            "bounding_box_mm": {"x": 80, "y": 60, "z": 12},
        },
        "features": [],
        "warnings": [],
    })
    monkeypatch.setattr(llm_mod, "_tuzi_chat", lambda messages, model=None: {
        "features": [
            {"type": "face", "length": 80, "width": 60},
            wrong_feature,
        ],
    })
    monkeypatch.setattr(service_mod, "run_slot", lambda path: [{
        "feature_id": "slot-0",
        "type": "pocket",
        "subtype": "recognized_slot",
        "selected": True,
        "pocket_type": "开放",
        "length": 40,
        "width": 10,
        "depth": 8,
        "corner_radius": 3,
        "location": {"x": -20, "y": 0, "z": 4},
        "axis": {"x": 0, "y": 0, "z": 1},
        "evidence": ["inner-walls x3"],
    }])

    result = service_mod.parse_step_file(OPEN_SLOT_STEP)

    slots = [
        feat for feat in result["features"]
        if feat.get("subtype") == "recognized_slot"
    ]
    assert len(slots) == 1
    assert slots[0]["pocket_type"] == "开放"
    assert slots[0]["source"] == "geometry-rescue"
    assert "deterministic-open-slot-rescue" in slots[0]["evidence"]
    assert result["llm"]["repaired_open_slots"] == 1
    assert any("确定性 STEP 拓扑" in warning for warning in result["warnings"])


def test_open_slot_repair_ignores_closed_pocket(monkeypatch):
    from cncflow_core.geometry import service as service_mod

    features = [{"type": "face", "subtype": "recognized_face"}]
    monkeypatch.setattr(service_mod, "run_slot", lambda path: [{
        "type": "pocket",
        "subtype": "recognized_slot",
        "pocket_type": "封闭",
    }])

    repaired, count = service_mod._repair_missing_open_slots("part.step", features)

    assert repaired == features
    assert count == 0


@pytest.mark.llm_features
def test_extract_step_features_retries_one_timeout(monkeypatch):
    from cncflow_core.geometry import llm as llm_mod

    calls = []

    def fake_chat(messages, model=None):
        calls.append(messages)
        if len(calls) == 1:
            raise TimeoutError("read timed out")
        return {
            "features": [{
                "type": "slot",
                "pocket_type": "开放",
                "length": 40,
                "width": 10,
                "depth": 8,
                "corner_radius": 3,
            }],
        }

    monkeypatch.setattr(llm_mod, "_tuzi_chat", fake_chat)

    extracted = llm_mod.extract_step_features(OPEN_SLOT_STEP)

    assert len(calls) == 2
    assert extracted["features"][0]["subtype"] == "recognized_slot"


@pytest.mark.llm_features
def test_parse_step_file_llm_failure_is_not_empty_success(monkeypatch, tmp_path):
    from cncflow_core.geometry import llm as llm_mod
    from cncflow_core.geometry.service import parse_step_file
    from cncflow_core.ingestion import step_parser

    monkeypatch.setattr(step_parser, "parse_step", lambda path: {
        "geometry": {"volume_cm3": 1},
        "features": [{"type": "hole", "feature_id": "hole-0", "subtype": "recognized_hole",
                      "diameter_mm": 8, "depth_mm": 12}],
        "warnings": [],
    })
    monkeypatch.setattr(llm_mod, "_tuzi_chat", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("tu-zi 500")))
    step = tmp_path / "x.step"
    step.write_bytes(
        b"ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('AUTOMOTIVE_DESIGN'));\n"
        b"ENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;"
    )
    with pytest.raises(RuntimeError, match="LLM 特征识别失败"):
        parse_step_file(str(step))


@pytest.mark.llm_features
def test_parse_step_file_dual_falls_back_to_geometry(monkeypatch, tmp_path):
    from cncflow_core.geometry import llm as llm_mod
    from cncflow_core.geometry.service import parse_step_file
    from cncflow_core.ingestion import step_parser

    monkeypatch.setenv("CNCFLOW_FEATURE_PARSER", "dual")
    monkeypatch.setattr(step_parser, "parse_step", lambda path: {
        "geometry": {"volume_cm3": 1, "bounding_box_mm": {"x": 80, "y": 60, "z": 12}},
        "features": [{
            "type": "hole", "feature_id": "hole-0", "subtype": "recognized_hole",
            "selected": True, "diameter_mm": 8, "depth_mm": 12,
            "hole_type": "through", "position_type": "垂直", "cut_depth_mm": 14.4,
        }],
        "warnings": [],
    })
    monkeypatch.setattr(llm_mod, "_tuzi_chat", lambda *a, **k: (_ for _ in ()).throw(TimeoutError("timeout")))
    step = tmp_path / "x.step"
    step.write_bytes(
        b"ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('AUTOMOTIVE_DESIGN'));\n"
        b"ENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;"
    )
    result = parse_step_file(str(step))
    assert result["feature_source"] == "geometry"
    assert result["llm"]["ok"] is False
    assert any("回退几何插件" in w for w in result["warnings"])
    assert result["features"][0]["diameter_mm"] == 8


def test_geometry_contract_lists_llm_primary(client):
    body = client.get("/api/v1/geometry/contract").get_json()
    assert body["feature_parser"] == "geometry"
    assert body["feature_llm"]["provider"] == "tu-zi"
    assert body["feature_llm"]["model"] == "gpt-6-astra"
    assert "gpt-6-astra" in " ".join(body["notes"])
    caps = client.get("/api/v1/parse-capabilities").get_json()
    assert caps["feature_parser"] == "geometry"
    assert caps["feature_llm_model"] == "gpt-6-astra"


@pytest.mark.llm_features
def test_capabilities_and_health_default_llm(client, monkeypatch):
    monkeypatch.delenv("CNCFLOW_FEATURE_PARSER", raising=False)
    monkeypatch.delenv("TUZI_FEATURE_MODEL", raising=False)

    body = client.get("/api/v1/parse-capabilities").get_json()
    assert body["feature_parser"] == "llm"
    assert body["feature_llm_model"] == "gpt-6-astra"
    parser = client.get("/api/v1/health").get_json()["parser"]
    assert parser["feature_parser"] == "llm"
    assert parser["feature_llm_model"] == "gpt-6-astra"
