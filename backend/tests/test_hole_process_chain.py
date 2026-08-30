"""孔工艺链生成测试（文档1模块二 + 文档2速查表）。"""
import pytest

from cncflow_core.features.hole.models import DEFAULT_TOLERANCE_IT, HoleSpec
from cncflow_core.features.hole.process_chain import generate_chain


def procs(chain):
    return [s["process"] for s in chain]


def hole(d, h, **kw):
    return HoleSpec(diameter_mm=d, depth_mm=h, **kw)


class TestPrimaryDrillSelection:
    def test_alu_d50_it7_bore_path(self):
        # 铝合金 D50 IT7：IT≤7 触发点钻；D>30 → U钻；D≥20+IT≤7 → 镗孔路径
        chain = generate_chain(hole(50, 200), "铝合金", 7)
        assert procs(chain) == ["spot_drill", "u_drill", "semi_bore", "fine_bore", "chamfer", "chamfer"]

    def test_small_hole_uses_drill(self):
        chain = generate_chain(hole(10, 20), "铝合金", 11)
        assert procs(chain) == ["drill", "chamfer", "chamfer"]
        assert chain[0]["cycle"] == "G81"                 # L/D=2 ≤3

    def test_deep_hole_g83(self):
        # 不锈钢 D10 H80：H/D=8 → 深孔钻 G83；不锈钢触发点钻
        chain = generate_chain(hole(10, 80), "不锈钢", 11)
        assert procs(chain) == ["spot_drill", "drill", "chamfer", "chamfer"]
        drill = chain[1]
        assert drill["cycle"] == "G83"

    def test_hd_boundary_5_uses_g83(self):
        chain = generate_chain(hole(10, 50), "铝合金", 11)
        drill = next(step for step in chain if step["process"] == "drill")
        assert drill["cycle"] == "G83"

    def test_hd_boundary_10_still_uses_g83(self):
        chain = generate_chain(hole(10, 100), "铝合金", 11)
        assert "gun_drill" not in procs(chain)
        drill = next(step for step in chain if step["process"] == "drill")
        assert drill["cycle"] == "G83"

    def test_ultra_deep_gun_drill(self):
        chain = generate_chain(hole(10, 120), "铝合金", 11)   # H/D=12
        assert "gun_drill" in procs(chain)

    def test_hd_boundary_20_still_allows_gun_drill(self):
        chain = generate_chain(hole(10, 200), "铝合金", 11)
        assert "gun_drill" in procs(chain)

    def test_hd_over_20_replaces_gun_drill_with_special_route(self):
        chain = generate_chain(hole(10, 201), "铝合金", 11)
        assert "special_hole" in procs(chain)
        assert "gun_drill" not in procs(chain)
        assert "drill" not in procs(chain)

    def test_micro_hole_replaces_ordinary_primary_drill(self):
        chain = generate_chain(hole(0.8, 3), "铝合金", 7)
        primary = [
            proc for proc in procs(chain)
            if proc in {"drill", "u_drill", "gun_drill", "micro_hole", "special_hole"}
        ]
        assert primary == ["micro_hole"]
        assert not {"ream", "semi_bore", "fine_bore"} & set(procs(chain))

    def test_large_hole_rough_bore_still_obeys_f08(self):
        chain = generate_chain(hole(90, 90), "铝合金", 11)
        assert procs(chain) == ["rough_bore", "chamfer", "chamfer"]


class TestFinishing:
    FINISHING = {"ream", "semi_bore", "fine_bore", "grind"}

    @pytest.mark.parametrize("roughness_ra", [None, 3.2])
    def test_f08_default_o8_has_no_finishing(self, roughness_ra):
        chain = generate_chain(
            hole(8, 12),
            "铝合金",
            DEFAULT_TOLERANCE_IT,
            roughness_ra=roughness_ra,
        )
        assert not self.FINISHING & set(procs(chain))

    def test_it7_with_missing_ra_does_not_force_finishing(self):
        chain = generate_chain(hole(12, 24), "铝合金", 7)
        assert not self.FINISHING & set(procs(chain))

    def test_f01_micro_hole_disables_bore_and_ream_even_for_it7(self):
        chain = generate_chain(hole(0.8, 3), "铝合金", 7, roughness_ra=1.6)
        assert not {"ream", "semi_bore", "fine_bore"} & set(procs(chain))

    def test_f02_deep_it6_uses_grind(self):
        chain = generate_chain(hole(10, 110), "铝合金", 6, roughness_ra=1.6)
        assert self.FINISHING & set(procs(chain)) == {"grind"}

    def test_f04_large_it7_uses_one_bore_path(self):
        chain = generate_chain(hole(20, 40), "铝合金", 7, roughness_ra=1.6)
        finishing = [proc for proc in procs(chain) if proc in self.FINISHING]
        assert finishing == ["semi_bore", "fine_bore"]

    def test_f05_ra08_uses_fine_bore_not_ream(self):
        chain = generate_chain(hole(12, 24), "铝合金", 7, roughness_ra=0.8)
        assert self.FINISHING & set(procs(chain)) == {"fine_bore"}

    def test_f06_ra16_uses_ream_not_bore(self):
        chain = generate_chain(hole(12, 24), "铝合金", 7, roughness_ra=1.6)
        assert self.FINISHING & set(procs(chain)) == {"ream"}

    def test_f07_it8_uses_semi_bore_only(self):
        chain = generate_chain(hole(25, 50), "铝合金", 8, roughness_ra=1.6)
        assert self.FINISHING & set(procs(chain)) == {"semi_bore"}

    def test_f09_grind_beats_ream_at_ra04(self):
        chain = generate_chain(hole(12, 24), "铝合金", 7, roughness_ra=0.4)
        assert self.FINISHING & set(procs(chain)) == {"grind"}


class TestThreadAndBottom:
    THREADING = {"tap", "thread_mill"}

    def test_t01_no_thread_emits_no_thread_process(self):
        chain = generate_chain(hole(12, 24), "铝合金", 11)
        assert not self.THREADING & set(procs(chain))

    @pytest.mark.parametrize(
        ("diameter", "depth", "spec"),
        [(8, 16, "M8×1.25"), (12, 24, "M12")],
    )
    def test_t02_ordinary_aluminum_thread_taps_only(self, diameter, depth, spec):
        chain = generate_chain(
            hole(diameter, depth, thread={"spec": spec}),
            "铝合金",
            11,
        )
        assert self.THREADING & set(procs(chain)) == {"tap"}

    @pytest.mark.parametrize(
        ("diameter", "depth", "spec", "material"),
        [
            (12, 24, "M12", "不锈钢"),
            (20, 40, "M20", "铝合金"),
            (8, 48, "M8", "铝合金"),
        ],
    )
    def test_t03_difficult_threads_mill_only(self, diameter, depth, spec, material):
        chain = generate_chain(
            hole(diameter, depth, thread={"spec": spec}),
            material,
            11,
        )
        assert self.THREADING & set(procs(chain)) == {"thread_mill"}

    def test_flat_bottom_blind_hole(self):
        chain = generate_chain(hole(20, 40, hole_type="blind", bottom_shape="flat"), "铝合金", 11)
        assert "flat_bottom_mill" in procs(chain)

    def test_frozen_finishing_thread_bottom_chamfer_order(self):
        chain = generate_chain(
            hole(
                12,
                24,
                hole_type="blind",
                bottom_shape="flat",
                thread={"spec": "M12"},
            ),
            "铝合金",
            7,
            roughness_ra=1.6,
        )
        assert procs(chain) == [
            "spot_drill",
            "drill",
            "ream",
            "tap",
            "flat_bottom_mill",
            "chamfer",
        ]

    def test_chamfer_always_last(self):
        for spec in [hole(10, 20), hole(50, 100), hole(90, 90)]:
            chain = generate_chain(spec, "铝合金", 11)
            assert procs(chain)[-1] == "chamfer"


    def test_through_hole_two_chamfers(self):
        chain = generate_chain(hole(8, 12, hole_type="through"), "铝合金", 11)
        ch = [s for s in chain if s["process"] == "chamfer"]
        assert [s.get("side") for s in ch] == ["entry", "exit"]
        assert [s.get("name") for s in ch] == ["入口倒角", "出口倒角"]

    def test_blind_hole_one_chamfer(self):
        chain = generate_chain(hole(8, 12, hole_type="blind"), "铝合金", 11)
        ch = [s for s in chain if s["process"] == "chamfer"]
        assert len(ch) == 1
        assert ch[0].get("side") is None
