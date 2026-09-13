"""LLM 特征映射 + parse 主路径。不打真 tu-zi。"""
import json
import os

import pytest

from cncflow_core.geometry.llm import (
    build_messages,
    map_llm_features,
    read_step_ascii,
)
from cncflow_core.inquiries.api import _review_and_quote_features, _sanitize_review_features


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
LLM_D8 = os.path.join(FIXTURES, "llm_plate_hole_d8.json")
LLM_OPEN_SLOT = os.path.join(FIXTURES, "llm_rect_open_slot.json")
LLM_NUC_WINDOWS_MISS = os.path.join(FIXTURES, "llm_nuc_windows_miss.json")
STEP_D8 = os.path.join(FIXTURES, "plate_hole_d8.step")
STEP_OPEN_SLOT = os.path.join(FIXTURES, "rect_open_slot.step")
STEP_NUC_WINDOWS = os.path.join(FIXTURES, "nuc_plate_windows.step")
SLOT_TREE_FIELDS = ("pocket_type", "length", "width", "depth", "corner_radius")


def _cylinder_groups_step(groups, faces_per_axis=2):
    entities = []
    entity_id = 1
    for radius, axis_positions in groups:
        for x, z in axis_positions:
            for face_index in range(faces_per_axis):
                point_x = x + face_index * 0.2
                point_z = z - face_index * 0.2
                cylinder_id = entity_id
                placement_id = entity_id + 1
                point_id = entity_id + 2
                direction_id = entity_id + 3
                entities.extend([
                    f"#{cylinder_id}=CYLINDRICAL_SURFACE('',#{placement_id},{radius});",
                    (
                        f"#{placement_id}=AXIS2_PLACEMENT_3D("
                        f"'',#{point_id},#{direction_id},$);"
                    ),
                    (
                        f"#{point_id}=CARTESIAN_POINT("
                        f"'',({point_x},{face_index * 8.0},{point_z}));"
                    ),
                    f"#{direction_id}=DIRECTION('',(0.,1.,0.));",
                ])
                entity_id += 4
    return (
        "ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\n"
        + "\n".join(entities)
        + "\nENDSEC;\nEND-ISO-10303-21;"
    )


def _cylinder_step(axis_positions, radius=1.7, faces_per_axis=2):
    return _cylinder_groups_step(
        [(radius, axis_positions)],
        faces_per_axis=faces_per_axis,
    )


def _fixture_payload():
    with open(LLM_D8, encoding="utf-8") as fh:
        return json.load(fh)


def _open_slot_payload():
    with open(LLM_OPEN_SLOT, encoding="utf-8") as fh:
        return json.load(fh)


def _nuc_windows_miss_payload():
    with open(LLM_NUC_WINDOWS_MISS, encoding="utf-8") as fh:
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
    assert {feat["feature_id"] for feat in review} == {
        "hole-0", "face-0", "od-0",
    }
    assert [feat["type"] for feat in quoted] == ["hole", "face"]
    outer = next(feat for feat in review if feat["type"] == "outer_cylinder")
    assert outer["quote_excluded"] is True
    assert outer["amount_contribution"] == 0
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
        ({"type": "开口槽", "L": 40, "W": 10, "H": 8, "R": 3}, "slot", "slot-0"),
        ({"type": "groove", "length": 40, "width": 10, "depth": 8, "corner_radius": 3, "open": True}, "slot", "slot-0"),
        ({"type": "矩形槽", "slot_length": 40, "slot_width": 10, "slot_depth": 8, "fillet": 3}, "slot", "slot-0"),
        ({"type": "open-slot", "length_mm": 40, "width_mm": 10, "depth_mm": 8, "radius_mm": 3}, "slot", "slot-0"),
        ({"type": "台阶轮廓", "length": 80, "height": 8, "width": 25}, "step", "step-0"),
        ({"type": "曲面", "surface_type": "凸面", "curvature_radius": 20, "position": "顶面"}, "surface", "surface-0"),
        ({"type": "pocket", "length": 24, "width": 12, "depth": 6, "pocket_type": "封闭"}, "pocket", "slot-0"),
        ({"type": "pocket_or_step", "length": 24, "width": 12, "depth": 6, "pocket_type": "封闭"}, "pocket", "slot-0"),
        ({"type": "倒角", "chamfer_mm": 0.8}, "chamfer", "chamfer-0"),
        ({"type": "圆角", "dimensions": {"fillet_radius": 2}}, "fillet", "fillet-0"),
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


def test_sanitize_keeps_quote_and_review_only_feature_types():
    cleaned = _sanitize_review_features([
        {"type": "hole", "feature_id": "hole-0"},
        {"type": "face", "feature_id": "face-0"},
        {"type": "pocket", "feature_id": "slot-0", "subtype": "recognized_slot"},
        {"type": "slot", "feature_id": "open-slot-0"},
        {"type": "thread", "feature_id": "thread-0"},
        {"type": "surface", "feature_id": "surface-0", "subtype": "recognized_surface"},
        {"type": "step", "feature_id": "step-0"},
        {"type": "outer_cylinder", "feature_id": "od-0"},
        {"type": "chamfer", "feature_id": "chamfer-0"},
        {"type": "fillet", "feature_id": "fillet-0"},
        {"type": "boss", "feature_id": "boss-0"},
        {"type": "pocket_or_step", "feature_id": "prismatic-region-0", "subtype": "planar_region"},
        {"type": "hole", "feature_id": "cylinder-0", "subtype": "cylindrical_candidate"},
    ])
    assert [feat["feature_id"] for feat in cleaned] == [
        "hole-0",
        "face-0",
        "slot-0",
        "open-slot-0",
        "thread-0",
        "surface-0",
        "step-0",
        "od-0",
        "chamfer-0",
        "fillet-0",
    ]


def test_llm_chamfer_and_fillet_keep_only_explicit_sizes_and_review_warnings():
    warning = "可能是沉头孔、倒角或锥面，需人工分类"
    mapped = map_llm_features({
        "features": [
            {
                "type": "chamfer",
                "feature_id": "chamfer-explicit",
                "dimensions": {"C": 0.8, "x": 90, "y": 60, "z": 12},
                "warnings": [warning],
            },
            {
                "type": "fillet",
                "feature_id": "fillet-explicit",
                "fillet_radius": 2.5,
            },
            {
                "type": "chamfer",
                "feature_id": "chamfer-bbox-only",
                "dimensions": {"x": 1, "y": 30, "z": 30},
            },
        ],
    })["features"]

    assert mapped[0]["C"] == mapped[0]["dimensions"]["C"] == 0.8
    assert mapped[0]["warnings"] == [warning]
    assert mapped[1]["R"] == mapped[1]["dimensions"]["R"] == 2.5
    assert "C" not in mapped[2]
    assert "C" not in mapped[2]["dimensions"]

    review, quoted = _review_and_quote_features(
        mapped + [{
            "type": "hole",
            "feature_id": "hole-0",
            "diameter_mm": 8,
            "depth_mm": 12,
        }],
        None,
        80,
        60,
        12,
    )
    assert [feature["type"] for feature in quoted] == ["hole"]
    edges = [feature for feature in review if feature["type"] in {"chamfer", "fillet"}]
    assert {feature["feature_id"] for feature in edges} == {
        "chamfer-explicit",
        "fillet-explicit",
        "chamfer-bbox-only",
    }
    assert all(feature["quote_status"] == "待手册公式" for feature in edges)
    assert all(feature["quote_excluded"] is True for feature in edges)
    assert all(feature["amount_contribution"] == 0 for feature in edges)
    assert all(
        step["minutes"] is None
        and step["amount"] == 0
        and step["quote_excluded"] is True
        and step["process"] != "chamfer"
        for feature in edges
        for step in feature["process_chain"]
    )
    bbox_only = next(
        feature for feature in edges
        if feature["feature_id"] == "chamfer-bbox-only"
    )
    assert "C" not in bbox_only
    assert any("不得从 bbox 推断" in gap for gap in bbox_only["gaps"])
    assert next(
        feature for feature in edges
        if feature["feature_id"] == "chamfer-explicit"
    )["warnings"] == [warning]
    torus_warning = "可能是圆角或环形槽，需人工分类"
    step_candidate = _sanitize_review_features([{
        "type": "fillet",
        "feature_id": "torus-7",
        "subtype": "toroidal_face",
        "dimensions": {"x": 6, "y": 6, "z": 2},
        "warnings": [torus_warning],
    }])[0]
    assert step_candidate["warnings"] == [torus_warning]
    assert "R" not in step_candidate
    assert any("不得从 bbox 推断" in gap for gap in step_candidate["gaps"])


def test_map_llm_skips_unknown_keeps_valid():
    mapped = map_llm_features({
        "features": [
            {"type": "boss"},
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
    assert "强制穷举全部孔族" in blob
    assert "禁止只报告最大孔" in blob
    assert "有大中心孔时也不得省略小安装孔" in blob
    assert "occurrences" in blob
    assert "开口矩形槽" in blob
    assert "贯穿板厚" in blob and "plate window" in blob
    assert "pocket_type=封闭" in blob
    open_text, _ = read_step_ascii(STEP_OPEN_SLOT)
    open_blob = json.dumps(build_messages(open_text), ensure_ascii=False)
    assert "slot/pocket" in open_blob
    assert "CYLINDRICAL_SURFACE" in open_text or "CIRCLE" in open_text


def test_multi_cylinder_cavity_hint_only_rejects_slot_corner_cylinders():
    step_text = "\n".join(
        f"#{index}=CYLINDRICAL_SURFACE('',#{index + 20},3.);"
        for index in range(1, 4)
    )
    blob = json.dumps(build_messages(step_text), ensure_ascii=False)

    assert "仅槽角 R 对应的部分圆柱不得报成 hole/outer_cylinder" in blob
    assert "真实完整圆柱壁构成的通孔或盲孔必须逐族报 hole" in blob
    assert "绝不能整体跳过孔" in blob
    assert "不要报成 outer_cylinder 或 hole" not in blob


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


def _assert_open_slot_tree(slot):
    assert slot["type"] in {"slot", "pocket"}
    assert slot["subtype"] == "recognized_slot"
    assert slot["feature_id"] == "slot-0"
    assert slot["pocket_type"] == "开放"
    assert slot["length"] == pytest.approx(40)
    assert slot["width"] == pytest.approx(10)
    assert slot["depth"] == pytest.approx(8)
    assert slot["corner_radius"] == pytest.approx(3)
    for name in SLOT_TREE_FIELDS:
        assert name in slot
    for name in ("length", "width", "depth", "corner_radius"):
        assert name in slot["dimensions"]


def test_map_llm_rect_open_slot_fixture_fields():
    mapped = map_llm_features(_open_slot_payload())
    by_type = {feat["type"]: feat for feat in mapped["features"]}
    _assert_open_slot_tree(by_type["slot"])
    face = by_type["face"]
    assert face["feature_id"] == "face-0"
    assert face["length"] == 80
    assert face["width"] == 60
    assert face["selected"] is True


def test_map_llm_rect_open_slot_review_and_quote_pin(client):
    features = map_llm_features(_open_slot_payload())["features"]
    review, quoted = _review_and_quote_features(features, None, 80, 60, 12)
    assert {feat["feature_id"] for feat in review} == {"slot-0", "face-0"}
    assert {feat["type"] for feat in quoted} == {"pocket", "face"}
    slot = next(feat for feat in review if feat["type"] in {"slot", "pocket"})
    face = next(feat for feat in review if feat["type"] == "face")
    _assert_open_slot_tree(slot)
    assert slot["selected"] is True and face["selected"] is True

    body = client.post("/api/v1/quotes", json={
        "material": "铝合金",
        "stock_type": "板材",
        "length": 80,
        "width": 60,
        "height": 12,
        "v_part_cad": 54.430702,
        "features": [
            {
                "type": "slot",
                "feature_id": slot["feature_id"],
                "length": slot["length"],
                "width": slot["width"],
                "depth": slot["depth"],
                "corner_radius": slot["corner_radius"],
                "pocket_type": slot["pocket_type"],
            },
            {"type": "face", "feature_id": face["feature_id"], "length": face["length"], "width": face["width"]},
        ],
    }).get_json()
    assert body["labor_cost_breakdown"]["total"] == pytest.approx(211.59, abs=0.01)
    assert body["ui_cost"]["inspect"] == body["ui_cost"]["toolwear"] == body["ui_cost"]["scrap"] == 0


@pytest.mark.parametrize(
    "raw",
    [
        {"type": "自由曲面", "surface_type": "自由曲面", "length": 40, "width": 10, "depth": 8, "corner_radius": 3},
        {"type": "face", "length": 40, "width": 10, "depth": 8, "corner_radius": 3, "name": "开口槽"},
        {"type": "surface", "surface_type": "槽底", "L": 40, "W": 10, "H": 8, "R": 3},
        {"type": "face", "length": 80, "width": 60, "slots": [
            {"length": 40, "width": 10, "depth": 8, "corner_radius": 3, "pocket_type": "开放"},
        ]},
    ],
)
def test_map_llm_recovers_open_slot_from_miss_shapes(raw):
    mapped = map_llm_features({"features": [raw]})
    slots = [feat for feat in mapped["features"] if feat["type"] in {"slot", "pocket"}]
    assert slots, mapped
    _assert_open_slot_tree(slots[0])


def test_map_llm_keeps_real_step_and_hole():
    mapped = map_llm_features({
        "features": [
            {"type": "台阶轮廓", "length": 80, "height": 8, "width": 25},
            {"type": "hole", "diameter_mm": 8, "depth_mm": 12, "hole_type": "through"},
        ],
    })
    assert [feat["type"] for feat in mapped["features"]] == ["step", "hole"]


@pytest.mark.llm_features
def test_parse_step_file_llm_rect_open_slot_fixture(monkeypatch):
    from cncflow_core.geometry import llm as llm_mod
    from cncflow_core.geometry.service import parse_step_file
    from cncflow_core.ingestion import step_parser

    monkeypatch.setattr(step_parser, "parse_step", lambda path: {
        "geometry": {"volume_cm3": 54.43, "bounding_box_mm": {"x": 80, "y": 60, "z": 12}},
        "features": [],
        "warnings": [],
    })
    monkeypatch.setattr(llm_mod, "_tuzi_chat", lambda messages, model=None: _open_slot_payload())
    result = parse_step_file(STEP_OPEN_SLOT)
    assert result["feature_source"] == "llm"
    assert result["llm"]["ok"] is True
    slot = next(feat for feat in result["features"] if feat["type"] in {"slot", "pocket"})
    _assert_open_slot_tree(slot)


@pytest.mark.llm_features
@pytest.mark.parametrize(
    "miss",
    [
        {"features": [
            {"type": "face", "length": 80, "width": 60},
            {"type": "surface", "surface_type": "自由曲面"},
        ]},
        {"features": [
            {"type": "face", "length": 80, "width": 60},
            {"type": "outer_cylinder", "diameter_mm": 6, "depth_mm": 8},
        ]},
    ],
)
def test_extract_retries_thin_miss_as_open_slot(monkeypatch, miss):
    from cncflow_core.geometry import llm as llm_mod

    calls = []

    def chat(messages, model=None):
        calls.append(messages)
        return _open_slot_payload() if len(calls) > 1 else miss

    monkeypatch.setattr(llm_mod, "_tuzi_chat", chat)
    out = llm_mod.extract_step_features(STEP_OPEN_SLOT)
    assert len(calls) == 2
    slot = next(feat for feat in out["features"] if feat["type"] in {"slot", "pocket"})
    _assert_open_slot_tree(slot)
    assert any("补询已补" in w for w in out["warnings"])
    retry_blob = json.dumps(calls[1], ensure_ascii=False)
    assert "开口槽必须出" in retry_blob


@pytest.mark.llm_features
def test_extract_retries_when_step_cylinders_far_outnumber_hole_occurrences(
    monkeypatch,
    tmp_path,
):
    from cncflow_core.geometry import llm as llm_mod

    step = tmp_path / "many-holes.step"
    step.write_text(
        _cylinder_step(
            [(index * 5.0, index * 3.0) for index in range(12)],
            radius=2.5,
            faces_per_axis=1,
        ),
        encoding="ascii",
    )
    first = {
        "features": [
            {
                "type": "hole",
                "diameter_mm": 40,
                "depth_mm": 8,
                "hole_type": "through",
            },
            {"type": "face", "length": 200, "width": 120},
        ],
    }
    completed = {
        "features": [
            {
                "type": "hole",
                "diameter_mm": 40,
                "depth_mm": 8,
                "hole_type": "through",
            },
            {
                "type": "hole",
                "diameter_mm": 5,
                "depth_mm": 8,
                "hole_type": "through",
                "occurrences": 10,
            },
            {"type": "face", "length": 200, "width": 120},
        ],
    }
    calls = []

    def chat(messages, model=None):
        calls.append(messages)
        return first if len(calls) == 1 else completed

    monkeypatch.delenv("TUZI_FEATURE_HOLE_RETRY", raising=False)
    monkeypatch.setattr(llm_mod, "_tuzi_chat", chat)

    out = llm_mod.extract_step_features(str(step))

    assert len(calls) == 2
    assert sum(
        feat["occurrences"]
        for feat in out["features"]
        if feat["type"] == "hole"
    ) == 11
    assert "LLM 首次孔欠检，补询已补 hole" in out["warnings"]
    retry_blob = json.dumps(calls[1], ensure_ascii=False)
    assert "强制穷举全部孔族" in retry_blob
    assert "禁止只报告最大孔" in retry_blob
    assert "小安装孔" in retry_blob
    assert "occurrences" in retry_blob


@pytest.mark.llm_features
def test_extract_clamps_hole_occurrences_to_unique_step_axes(
    monkeypatch,
    tmp_path,
):
    from cncflow_core.geometry import llm as llm_mod

    step = tmp_path / "xm8-axis-clusters.step"
    step.write_text(
        _cylinder_step([
            (-27.5, -27.5),
            (-27.5, 27.5),
            (27.5, -27.5),
            (27.5, 27.5),
            (-27.5, 0),
            (0, 27.5),
            (27.5, 0),
        ]),
        encoding="ascii",
    )
    monkeypatch.setattr(llm_mod, "_tuzi_chat", lambda *_args, **_kwargs: {
        "features": [{
            "type": "hole",
            "diameter_mm": 3.4,
            "depth_mm": 8,
            "hole_type": "through",
            "occurrences": 8,
        }],
    })

    out = llm_mod.extract_step_features(str(step))

    hole = next(feature for feature in out["features"] if feature["type"] == "hole")
    warning = "LLM 孔 occurrences 超几何轴簇，已按 STEP clamp Ø3.4 8→7"
    expected_instances = [
        {"x": -27.5, "y": 0.0, "z": -27.5},
        {"x": -27.5, "y": 0.0, "z": 27.5},
        {"x": 27.5, "y": 0.0, "z": -27.5},
        {"x": 27.5, "y": 0.0, "z": 27.5},
        {"x": -27.5, "y": 0.0, "z": 0.0},
        {"x": 0.0, "y": 0.0, "z": 27.5},
        {"x": 27.5, "y": 0.0, "z": 0.0},
    ]
    assert hole["occurrences"] == 7
    assert warning in out["warnings"]
    assert warning not in (hole.get("warnings") or [])
    assert not any(
        "轴簇" in text or "8→7" in text or "LLM" in text
        for text in hole.get("warnings") or []
    )
    assert hole["instances"] == expected_instances
    assert hole["location"] in expected_instances
    assert hole["location"] != {"x": 0, "y": 0, "z": 0}
    assert hole["pose"]["origin"] == hole["location"]
    assert max(abs(hole["location"][axis]) for axis in ("x", "y", "z")) > 1


def test_map_llm_hole_keeps_explicit_instances_and_shop_warnings():
    mapped = map_llm_features({
        "features": [{
            "type": "hole",
            "diameter_mm": 3.4,
            "depth_mm": 8,
            "hole_type": "through",
            "occurrences": 2,
            "location": {"x": 0, "y": 0, "z": 0},
            "instances": [
                {"x": -27.5, "y": 0, "z": -27.5},
                {"location": {"x": 27.5, "y": 0, "z": 27.5}},
            ],
            "warnings": ["孔径偏小，建议核对"],
        }],
    })["features"][0]
    assert mapped["instances"] == [
        {"x": -27.5, "y": 0.0, "z": -27.5},
        {"x": 27.5, "y": 0.0, "z": 27.5},
    ]
    assert mapped["warnings"] == ["孔径偏小，建议核对"]


@pytest.mark.llm_features
def test_extract_syncs_hole_occurrences_to_step_instances(
    monkeypatch,
    tmp_path,
):
    from cncflow_core.geometry import llm as llm_mod

    step = tmp_path / "hole-under-geometry-count.step"
    step.write_text(
        _cylinder_step([(index * 5.0, 0) for index in range(3)]),
        encoding="ascii",
    )
    monkeypatch.setattr(llm_mod, "_tuzi_chat", lambda *_args, **_kwargs: {
        "features": [{
            "type": "hole",
            "diameter_mm": 3.4,
            "depth_mm": 8,
            "hole_type": "through",
            "occurrences": 1,
        }],
    })

    out = llm_mod.extract_step_features(str(step))
    hole = next(feature for feature in out["features"] if feature["type"] == "hole")

    assert hole["occurrences"] == 3
    assert not any("occurrences 超几何轴簇" in warning for warning in out["warnings"])
    assert len(hole["instances"]) == 3
    assert hole["location"] in hole["instances"]
    assert hole["location"] != {"x": 0, "y": 0, "z": 0}


@pytest.mark.llm_features
def test_extract_backfills_missing_step_radius_hole_family(
    monkeypatch,
    tmp_path,
):
    from cncflow_core.geometry import llm as llm_mod

    step = tmp_path / "xm7-missing-hole-family.step"
    missing_instances = [
        (0, 27.5),
        (23.816, -13.75),
        (-23.816, -13.75),
    ]
    step.write_text(
        _cylinder_groups_step([
            (1.5, [(0, 0)]),
            (1.7, missing_instances),
        ]),
        encoding="ascii",
    )
    monkeypatch.setattr(llm_mod, "_tuzi_chat", lambda *_args, **_kwargs: {
        "features": [{
            "type": "hole",
            "diameter_mm": 3,
            "depth_mm": 22,
            "hole_type": "through",
            "occurrences": 1,
        }],
    })

    out = llm_mod.extract_step_features(
        str(step),
        geometry={"bounding_box_mm": {"x": 64, "y": 22, "z": 64}},
    )

    holes = [feature for feature in out["features"] if feature["type"] == "hole"]
    assert [hole["diameter_mm"] for hole in holes] == [3, 3.4]
    backfilled = holes[1]
    expected_instances = [
        {"x": 0.0, "y": 0.0, "z": 27.5},
        {"x": 23.816, "y": 0.0, "z": -13.75},
        {"x": -23.816, "y": 0.0, "z": -13.75},
    ]
    assert backfilled["occurrences"] == 3
    assert backfilled["instances"] == expected_instances
    assert backfilled["location"] in expected_instances
    assert backfilled["location"] != {"x": 0, "y": 0, "z": 0}
    assert backfilled["pose"]["origin"] == backfilled["location"]
    assert backfilled["axis"] == {"x": 0.0, "y": 1.0, "z": 0.0}
    assert backfilled["depth_mm"] == 22
    assert backfilled["hole_type"] == "through"
    assert backfilled["source"] == "geometry"
    assert "STEP axis geometry backfill" in backfilled["evidence"]
    assert backfilled["warnings"] == []
    assert "STEP 轴簇几何回填 hole Ø3.4 ×3" in out["warnings"]


def test_hole_retry_uses_unique_axes_instead_of_cylindrical_faces():
    from cncflow_core.geometry import llm as llm_mod

    duplicate_faces = _cylinder_step(
        [(index * 5.0, 0) for index in range(7)],
        faces_per_axis=2,
    )
    unique_axes = _cylinder_step(
        [(index * 5.0, 0) for index in range(12)],
        faces_per_axis=1,
    )

    assert duplicate_faces.count("CYLINDRICAL_SURFACE") == 14
    assert llm_mod._step_cylinder_axis_counts(duplicate_faces) == {1.7: 7}
    clustered = llm_mod._step_cylinder_axis_clusters(duplicate_faces)
    assert clustered[1.7]["count"] == 7
    assert len(clustered[1.7]["origins"]) == 7
    assert all(set(origin) == {"x", "y", "z"} for origin in clustered[1.7]["origins"])
    assert not llm_mod._hole_retry_needed(
        duplicate_faces,
        [{"type": "hole", "occurrences": 3}],
    )
    assert llm_mod._hole_retry_needed(
        unique_axes,
        [{"type": "hole", "occurrences": 1}],
    )


@pytest.mark.llm_features
def test_feature_cache_skips_second_tuzi_and_force_reparse_bypasses(
    seeded_conn,
    monkeypatch,
    tmp_path,
):
    from cncflow_core.geometry import llm as llm_mod

    step = tmp_path / "feature-cache.step"
    step.write_bytes(
        b"ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\n"
        b"/* FEATURE-CACHE-UNIQUE */\nENDSEC;\nEND-ISO-10303-21;"
    )
    calls = []

    def fake_tuzi(*_args, **_kwargs):
        calls.append(True)
        return {"features": [{"type": "step", "length": 80, "height": 8}]}

    monkeypatch.setattr(llm_mod, "_tuzi_chat", fake_tuzi)
    first = llm_mod.extract_step_features(str(step), cache_conn=seeded_conn)
    second = llm_mod.extract_step_features(str(step), cache_conn=seeded_conn)
    forced = llm_mod.extract_step_features(
        str(step),
        cache_conn=seeded_conn,
        force_reparse=True,
    )

    assert len(calls) == 2
    assert first["cache_hit"] is False
    assert second["cache_hit"] is True
    assert forced["cache_hit"] is False
    assert second["features"] == first["features"]


@pytest.mark.llm_features
def test_extract_drops_nuc_window_pockets_but_keeps_mounting_holes(monkeypatch):
    from cncflow_core.geometry import llm as llm_mod

    raw = _nuc_windows_miss_payload()
    mapped_miss = map_llm_features(raw)["features"]
    assert len([
        feat
        for feat in mapped_miss
        if feat["type"] == "pocket" and feat["pocket_type"] == "封闭"
    ]) == 4

    monkeypatch.setattr(llm_mod, "_tuzi_chat", lambda messages, model=None: raw)
    out = llm_mod.extract_step_features(
        STEP_NUC_WINDOWS,
        geometry={"bounding_box_mm": {"x": 285, "y": 128, "z": 3.5}},
    )

    assert len([feat for feat in out["features"] if feat["type"] == "hole"]) == 18
    assert not [
        feat
        for feat in out["features"]
        if feat["type"] in {"slot", "pocket"}
    ]
    assert any("已移除 4 个半板厚封闭 pocket" in warning for warning in out["warnings"])

    review, quoted = _review_and_quote_features(
        out["features"],
        None,
        285,
        128,
        3.5,
    )
    assert len([feat for feat in review if feat["type"] == "hole"]) == 18
    assert len([feat for feat in quoted if feat["type"] == "hole"]) == 18
    assert not [feat for feat in quoted if feat["type"] in {"slot", "pocket"}]


@pytest.mark.llm_features
def test_nuc_repair_keeps_single_real_closed_pocket(monkeypatch):
    from cncflow_core.geometry import llm as llm_mod

    raw = _nuc_windows_miss_payload()
    raw["features"] = [
        feat
        for feat in raw["features"]
        if feat.get("type") != "pocket"
    ] + [next(feat for feat in raw["features"] if feat.get("type") == "pocket")]
    monkeypatch.setattr(llm_mod, "_tuzi_chat", lambda messages, model=None: raw)

    out = llm_mod.extract_step_features(
        STEP_NUC_WINDOWS,
        geometry={"bounding_box_mm": {"x": 285, "y": 128, "z": 3.5}},
    )

    pockets = [feat for feat in out["features"] if feat["type"] == "pocket"]
    assert len(pockets) == 1
    assert pockets[0]["pocket_type"] == "封闭"
    assert not any("窗口修复" in warning for warning in out["warnings"])


def test_tuzi_chat_retries_timeout_once(monkeypatch):
    from cncflow_core.geometry import llm as llm_mod

    calls = {"n": 0}

    def once_timeout(messages, model=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimeoutError("read timeout")
        return {"features": [{"type": "step", "length": 80, "height": 8}]}

    monkeypatch.setattr(llm_mod, "_tuzi_complete", once_timeout)
    out = llm_mod._tuzi_chat([{"role": "user", "content": "x"}])
    assert calls["n"] == 2
    assert out["features"][0]["type"] == "step"


def test_tuzi_chat_does_not_retry_hard_failure(monkeypatch):
    from cncflow_core.geometry import llm as llm_mod

    calls = {"n": 0}

    def boom(messages, model=None):
        calls["n"] += 1
        raise RuntimeError("tu-zi 500")

    monkeypatch.setattr(llm_mod, "_tuzi_complete", boom)
    with pytest.raises(RuntimeError, match="500"):
        llm_mod._tuzi_chat([])
    assert calls["n"] == 1
