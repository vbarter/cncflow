"""切削参数计算测试。黄金用例来自《4-加工参数知识库》§六 完整计算示例，逐字段比对。"""
import pytest

from cncflow_core.common.params_calc import calc_params, lookup_vc, spindle_rpm


class TestGoldenExamples:
    """文档4 示例1/2：铝合金 D=50 钻孔+铰孔，稳定/激进两种模式。"""

    def test_drill_alu_d50_stable(self):
        params = calc_params("drill", "铝合金", "硬质合金", 50, deep=False)["stable"]
        assert params.vc_m_min == 150
        assert params.spindle_rpm == 955
        assert params.feed_per_rev_mm == 0.20
        assert params.cutting_depth == "全径"

    def test_drill_alu_d50_aggressive(self):
        params = calc_params("drill", "铝合金", "硬质合金", 50)["aggressive"]
        assert params.vc_m_min == 250
        assert params.spindle_rpm == 1592
        assert params.feed_per_rev_mm == 0.36

    def test_ream_alu_d50_stable(self):
        params = calc_params("ream", "铝合金", "硬质合金", 50)["stable"]
        assert params.vc_m_min == 75          # 铰刀 Vc = 钻头 150 × 50%
        assert params.spindle_rpm == 477
        assert params.feed_per_rev_mm == 0.15
        assert params.cutting_depth == "0.15 (单边)"

    def test_ream_alu_d50_aggressive(self):
        params = calc_params("ream", "铝合金", "硬质合金", 50)["aggressive"]
        assert params.vc_m_min == 150         # 250 × 60%
        assert params.spindle_rpm == 955
        assert params.feed_per_rev_mm == 0.28

    def test_rpm_formula_example_d10(self):
        # 文档4 §二 计算示例：铝合金硬质合金钻头 D=10 稳定 → 4775 rpm
        assert spindle_rpm(150, 10) == 4775


class TestMaterialCorrection:
    def test_stainless_drill_d10_feed_factor(self):
        # 文档4 §7.3：不锈钢 D10 钻头稳定 fr = 0.08 × 0.7 = 0.056
        params = calc_params("drill", "不锈钢", "硬质合金", 10)["stable"]
        assert params.vc_m_min == 70
        assert params.feed_per_rev_mm == 0.056

    def test_carbon_steel_factor(self):
        params = calc_params("drill", "普通碳钢", "高速钢", 10)["stable"]
        assert params.feed_per_rev_mm == round(0.08 * 0.9, 4)


class TestCoolantAndBoundaries:
    def test_deep_drill_coolant(self):
        params = calc_params("drill", "铝合金", "硬质合金", 10, deep=True)["stable"]
        assert "高压内冷" in params.coolant

    def test_u_drill_coolant(self):
        params = calc_params("u_drill", "铝合金", "硬质合金", 49.5)["stable"]
        assert "高压内冷" in params.coolant

    def test_fr_boundary_inclusive_max(self):
        # 区间 min 不含 max 含："3<D≤6" → D=3 属上一档 0.02，D=6 属本档 0.05
        assert calc_params("drill", "铝合金", "硬质合金", 3)["stable"].feed_per_rev_mm == 0.02
        assert calc_params("drill", "铝合金", "硬质合金", 6)["stable"].feed_per_rev_mm == 0.05

    def test_bore_uses_bore_table(self):
        params = calc_params("fine_bore", "铝合金", "硬质合金", 50)["stable"]
        assert params.feed_per_rev_mm == 0.08  # bore 表 20<D≤50

    def test_unsupported_process_returns_none(self):
        assert calc_params("chamfer", "铝合金", "硬质合金", 25) is None
        assert calc_params("spot_drill", "铝合金", "硬质合金", 3) is None

    def test_missing_vc_fails_fast(self):
        # 高速钢 × 钛合金 原文未提供 → fail fast
        with pytest.raises(ValueError, match="线速度基准表未覆盖"):
            lookup_vc("高速钢", "钛合金", "stable")

    def test_fr_out_of_range_fails_fast(self):
        with pytest.raises(ValueError, match="未覆盖直径"):
            calc_params("drill", "铝合金", "硬质合金", 100)
