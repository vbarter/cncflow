"""单刀 5 项硬性属性推算测试（文档2）。"""
import pytest

from cncflow_core.features.hole.tool_attrs import derive


class TestNominalDiameter:
    def test_rough_drill_with_finishing_d50(self):
        # D>30 余量 0.5：粗刀 = 50 - 0.5 = 49.5
        attrs = derive("u_drill", 50, 4, "铝合金", 7, has_finishing=True)
        assert attrs.nominal_diameter_mm == 49.5

    def test_rough_drill_with_finishing_d10(self):
        # D≤30 余量 0.3：粗刀 = 10 - 0.3 = 9.7
        attrs = derive("drill", 10, 2, "铝合金", 7, has_finishing=True)
        assert attrs.nominal_diameter_mm == 9.7

    def test_drill_without_finishing_full_diameter(self):
        attrs = derive("drill", 10, 2, "铝合金", 11, has_finishing=False)
        assert attrs.nominal_diameter_mm == 10

    def test_finishing_tool_equals_hole_diameter(self):
        attrs = derive("ream", 10, 2, "铝合金", 7, has_finishing=True)
        assert attrs.nominal_diameter_mm == 10

    def test_chamfer_unrestricted(self):
        attrs = derive("chamfer", 50, 4, "铝合金", 7, has_finishing=True)
        assert attrs.nominal_diameter_mm is None


class TestStructure:
    def test_standard_below_hd5(self):
        assert derive("drill", 10, 5, "铝合金", 11, False).structure == "标准"   # H/D≤5 含边界

    def test_coolant_type_between_5_and_10(self):
        assert derive("drill", 10, 8, "不锈钢", 11, False).structure == "内冷"

    def test_gun_drill_structure(self):
        assert derive("gun_drill", 10, 12, "铝合金", 11, False).structure == "枪钻"

    def test_finishing_tool_never_gun_structure(self):
        # 深孔精加工刀具不存在"枪钻"结构，回落内冷
        assert derive("fine_bore", 10, 12, "铝合金", 6, True).structure == "内冷"


class TestMaterialMapping:
    def test_alu_carbide_uncoated(self):
        attrs = derive("drill", 10, 2, "铝合金", 11, False)
        assert (attrs.base_material, attrs.coating) == ("硬质合金", "无涂层")

    def test_stainless_carbide_tialn(self):
        attrs = derive("drill", 10, 2, "不锈钢", 11, False)
        assert (attrs.base_material, attrs.coating) == ("硬质合金", "TiAlN")

    def test_carbon_steel_hss_tin(self):
        attrs = derive("drill", 10, 2, "普通碳钢", 11, False)
        assert (attrs.base_material, attrs.coating) == ("高速钢", "TiN")


class TestPrecisionGrade:
    def test_rough_tool_always_normal(self):
        assert derive("drill", 10, 2, "铝合金", 6, True).precision_grade == "普通"

    def test_finishing_it7_high_precision(self):
        assert derive("ream", 10, 2, "铝合金", 7, True).precision_grade == "高精度"

    def test_finishing_it6_ultra(self):
        assert derive("fine_bore", 25, 2, "铝合金", 6, True).precision_grade == "超精密"

    def test_finishing_it9_normal(self):
        assert derive("semi_bore", 25, 2, "铝合金", 9, True).precision_grade == "普通"


class TestCategoryMapping:
    @pytest.mark.parametrize(
        "process,category",
        [("drill", "钻头"), ("u_drill", "U钻"), ("gun_drill", "枪钻"), ("ream", "铰刀"),
         ("rough_bore", "镗刀"), ("semi_bore", "镗刀"), ("fine_bore", "镗刀"),
         ("tap", "丝锥"), ("thread_mill", "螺纹铣刀"), ("flat_bottom_mill", "平底立铣刀"),
         ("chamfer", "倒角刀"), ("spot_drill", "中心钻")],
    )
    def test_process_to_category(self, process, category):
        assert derive(process, 12, 2, "铝合金", 7, True).category == category
