"""孔可加工性判定测试（文档1模块一）。边界值全部取自 YAML 定死的区间。"""
from cncflow_core.features.hole.machinability import evaluate
from cncflow_core.features.hole.models import HoleSpec


def hole(d, h, **kw):
    return HoleSpec(diameter_mm=d, depth_mm=h, **kw)


class TestDepthRatioBands:
    def test_normal_hole_level1(self):
        r = evaluate(hole(10, 40), "铝合金", 11)          # H/D=4 常规孔
        assert r.level == 1
        assert r.label == "Manufacturable"
        assert "HOLE-GEO-HD" in r.fired_rules

    def test_hd_boundary_5_is_deep(self):
        r = evaluate(hole(10, 50), "铝合金", 11)          # H/D=5 → 深孔档（min 含）
        assert r.level == 2

    def test_hd_boundary_10_is_still_deep(self):
        r = evaluate(hole(10, 100), "铝合金", 11)         # H/D=10 → G83 深孔档
        assert r.level == 2

    def test_hd_boundary_20_is_special_process(self):
        r = evaluate(hole(10, 200), "铝合金", 11)         # H/D=20 → 枪钻档上界
        assert r.level == 3

    def test_hd_over_20_is_special_not_na(self):
        r = evaluate(hole(10, 201), "铝合金", 11)
        assert r.level == 3
        assert r.label == "Special process required"


class TestGeometryChecks:
    def test_micro_hole_special_process(self):
        r = evaluate(hole(0.5, 2), "铝合金", 11)          # D<1
        assert r.level == 3
        assert "HOLE-GEO-SMALL" in r.fired_rules

    def test_large_hole_special_process(self):
        r = evaluate(hole(90, 90), "铝合金", 11)          # D>80
        assert r.level == 3
        assert "HOLE-GEO-LARGE" in r.fired_rules

    def test_d80_exactly_not_large(self):
        r = evaluate(hole(80, 80), "铝合金", 11)          # D=80 不触发（原文 D>80）
        assert "HOLE-GEO-LARGE" not in r.fired_rules


class TestMaterialAndPrecision:
    def test_stainless_high_risk(self):
        r = evaluate(hole(10, 30), "不锈钢", 11)
        assert r.level == 2
        assert "HOLE-MAT" in r.fired_rules

    def test_it7_requires_finishing(self):
        r = evaluate(hole(10, 30), "铝合金", 7)
        assert r.level == 2
        assert "HOLE-PREC-IT7" in r.fired_rules

    def test_deep_plus_it6_conflict(self):
        r = evaluate(hole(10, 150), "铝合金", 6)          # H/D=15 且 IT6
        assert r.level == 3
        assert "HOLE-PREC-DEEP-CONFLICT" in r.fired_rules

    def test_no_conflict_when_shallow(self):
        r = evaluate(hole(10, 30), "铝合金", 6)           # IT6 但 H/D=3
        assert "HOLE-PREC-DEEP-CONFLICT" not in r.fired_rules


def _pipeline_payload(**overrides):
    payload = {
        "feature": {
            "type": "hole",
            "diameter_mm": 10,
            "depth_mm": 20,
            "hole_type": "through",
            "position_type": "垂直",
        },
        "material": "铝合金",
        "tolerance_it": 11,
    }
    for key, value in overrides.pop("feature", {}).items():
        payload["feature"][key] = value
    payload.update(overrides)
    return payload


def _post_pipeline(client, **overrides):
    response = client.post("/api/v1/process-plan", json=_pipeline_payload(**overrides))
    assert response.status_code == 200, response.get_json()
    return response.get_json()


class TestFrozenNaGuards:
    def test_z_overtravel_is_na_and_has_no_process_chain(self, client):
        result = _post_pipeline(client, machine_max_z=19)
        assert result["machinability"]["label"] == "NA"
        assert result["process_chain"] == []
        assert result["tool_chain"] == []
        assert [item["code"] for item in result["blockers"]] == ["Z_OVERTRAVEL"]

    def test_three_axis_side_hole_is_na(self, client):
        result = _post_pipeline(
            client,
            feature={"position_type": "侧向", "surface": "side"},
            machine_axes=3,
        )
        assert result["machinability"]["label"] == "NA"
        assert result["process_chain"] == []
        assert [item["code"] for item in result["blockers"]] == ["THREE_AXIS_SIDE_HOLE"]

    def test_side_hole_without_machine_axes_is_not_na(self, client):
        result = _post_pipeline(
            client,
            feature={"position_type": "侧向", "surface": "side"},
        )
        assert result["is_machinable"] is True
        assert result["process_chain"]
        assert result["blockers"] == []

    def test_r15_deep_cavity_interference_does_not_auto_na(self, client):
        result = _post_pipeline(
            client,
            feature={"deep_cavity_interference": True},
            rule_hits=["R15"],
        )
        assert result["is_machinable"] is True
        assert result["process_chain"]

    def test_r22_missing_nonstandard_tool_channel_does_not_auto_na(self, client):
        result = _post_pipeline(
            client,
            feature={"diameter_mm": 9.7, "nonstandard_tool_channel": False},
            rule_hits=["R22"],
        )
        assert result["is_machinable"] is True
        assert result["process_chain"]
