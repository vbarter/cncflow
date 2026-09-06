"""tu-zi STEP 特征识别：请求格式、字段映射和可见失败。"""
from types import SimpleNamespace

import pytest

from cncflow_core.geometry.llm_recognizer import (
    DEFAULT_MODEL,
    map_tuzi_features,
    recognize_step_features,
)
from cncflow_core.geometry.service import parse_step_file


class FakeCompletions:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        message = SimpleNamespace(content=outcome)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeClient:
    def __init__(self, outcomes):
        self.completions = FakeCompletions(outcomes)
        self.chat = SimpleNamespace(completions=self.completions)


def test_mocked_tuzi_json_maps_hole_slot_and_surface(tmp_path, monkeypatch):
    monkeypatch.delenv("TUZI_MODEL", raising=False)
    step = tmp_path / "part.step"
    step.write_text("ISO-10303-21;\nEND-ISO-10303-21;", encoding="ascii")
    response = {
        "features": [
            {
                "type": "孔",
                "diameter_mm": 8,
                "depth_mm": 12,
                "hole_type": "通孔",
                "position_type": "垂直",
                "location": [1, 2, 3],
                "axis": "+Z",
            },
            {
                "type": "槽腔",
                "pocket_type": "开放",
                "length": 40,
                "width": 10,
                "depth": 8,
                "corner_radius": 3,
                "location": {"x": 0, "y": 0, "z": 4},
                "axis": {"x": 0, "y": 0, "z": 1},
            },
            {
                "type": "曲面",
                "surface_type": "凸面",
                "curvature_radius": 20,
                "position": "顶面",
            },
        ],
    }
    client = FakeClient([response])

    result = recognize_step_features(
        step,
        image_urls=["data:image/png;base64,aW1hZ2U="],
        client=client,
    )

    assert result["model"] == DEFAULT_MODEL == "gpt-6-astra"
    assert result["input_mode"] == "file_part"
    assert [feature["feature_id"] for feature in result["features"]] == [
        "hole-0",
        "slot-0",
        "surface-0",
    ]
    hole, slot, surface = result["features"]
    assert hole["type"] == "hole"
    assert hole["cut_depth_mm"] == pytest.approx(14.4)
    assert hole["location"] == {"x": 1.0, "y": 2.0, "z": 3.0}
    assert hole["axis"] == {"x": 0.0, "y": 0.0, "z": 1.0}
    assert slot["type"] == "pocket"
    assert slot["subtype"] == "recognized_slot"
    assert slot["dimensions"] == {
        "pocket_type": "开放",
        "length": 40.0,
        "width": 10.0,
        "depth": 8.0,
        "corner_radius": 3.0,
    }
    assert surface["surface_type"] == "凸面"
    assert surface["curvature_radius"] == 20.0

    call = client.completions.calls[0]
    assert call["model"] == "gpt-6-astra"
    assert call["response_format"] == {"type": "json_object"}
    content = call["messages"][1]["content"]
    file_part = next(part for part in content if part["type"] == "file")
    assert file_part["file"]["file_data"].startswith("data:text/plain;base64,")
    assert any(part["type"] == "image_url" for part in content)


def test_file_part_failure_falls_back_to_step_ascii(tmp_path):
    step = tmp_path / "fallback.step"
    step.write_text("ISO-10303-21;\n#1=PRODUCT('fallback');\nEND-ISO-10303-21;", encoding="ascii")
    client = FakeClient([
        RuntimeError("file type rejected"),
        {"features": [{
            "type": "surface",
            "surface_type": "自由曲面",
            "curvature_radius": None,
            "position": "侧面",
        }]},
    ])

    result = recognize_step_features(step, client=client)

    assert result["input_mode"] == "text_fallback"
    assert result["features"][0]["feature_id"] == "surface-0"
    assert "file part 失败" in result["warnings"][0]
    fallback = client.completions.calls[1]["messages"][1]["content"]
    assert "STEP ASCII:" in fallback[0]["text"]
    assert "#1=PRODUCT('fallback')" in fallback[0]["text"]


def test_mapping_rejects_slider_and_invalid_dimensions():
    warnings = []
    features = map_tuzi_features({
        "features": [
            {"type": "滑轴", "length": 10},
            {"type": "slot", "length": 40, "width": 0, "depth": 8},
        ],
    }, warnings)
    assert features == []
    assert len(warnings) == 2
    assert "不受支持" in warnings[0]
    assert "必填字段无效" in warnings[1]


def test_hard_api_failure_keeps_geometry_and_returns_warning(monkeypatch, tmp_path):
    from cncflow_core.ingestion import step_parser
    from cncflow_core.geometry import service

    monkeypatch.setenv("TUZI_API_KEY", "test-key")
    monkeypatch.setattr(step_parser, "parse_step", lambda path: {
        "geometry": {
            "bounding_box_mm": {"x": 80, "y": 60, "z": 12},
            "volume_cm3": 57,
        },
        "features": [
            {"type": "hole", "feature_id": "hole-classical"},
            {
                "type": "outer_cylinder",
                "feature_id": "od-1",
                "selected": False,
            },
        ],
        "warnings": [],
        "_mesh_glb": b"glb",
    })
    monkeypatch.setattr(
        service,
        "recognize_step_features",
        lambda path, image_urls=None: (_ for _ in ()).throw(
            RuntimeError("upstream 503")
        ),
    )
    step = tmp_path / "part.step"
    step.write_text("ISO-10303-21;", encoding="ascii")

    result = parse_step_file(step)

    assert result["geometry"]["bounding_box_mm"] == {"x": 80, "y": 60, "z": 12}
    assert result["_mesh_glb"] == b"glb"
    assert result["features"] == [{
        "type": "outer_cylinder",
        "feature_id": "od-1",
        "selected": False,
    }]
    assert result["feature_recognition"]["called"] is True
    assert result["feature_recognition"]["ok"] is False
    assert any("tu-zi STEP 特征识别失败" in warning for warning in result["warnings"])
