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

    def test_hd_boundary_10_is_ultra_deep(self):
        r = evaluate(hole(10, 100), "铝合金", 11)         # H/D=10 → 超深孔
        assert r.level == 3

    def test_hd_over_20_not_recommended(self):
        r = evaluate(hole(10, 200), "铝合金", 11)         # H/D=20 → 极限深孔
        assert r.level == 4
        assert r.label == "Not recommended"


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
