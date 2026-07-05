"""孔工艺链生成测试（文档1模块二 + 文档2速查表）。"""
from cncflow_core.features.hole.models import HoleSpec
from cncflow_core.features.hole.process_chain import generate_chain


def procs(chain):
    return [s["process"] for s in chain]


def hole(d, h, **kw):
    return HoleSpec(diameter_mm=d, depth_mm=h, **kw)


class TestPrimaryDrillSelection:
    def test_alu_d50_it7_bore_path(self):
        # 铝合金 D50 IT7：IT≤7 触发点钻；D>30 → U钻；D≥20+IT≤7 → 镗孔路径
        chain = generate_chain(hole(50, 200), "铝合金", 7)
        assert procs(chain) == ["spot_drill", "u_drill", "semi_bore", "fine_bore", "chamfer"]

    def test_small_hole_uses_drill(self):
        chain = generate_chain(hole(10, 20), "铝合金", 11)
        assert procs(chain) == ["drill", "chamfer"]
        assert chain[0]["cycle"] == "G81"                 # L/D=2 ≤3

    def test_deep_hole_g83(self):
        # 不锈钢 D10 H80：H/D=8 → 深孔钻 G83；不锈钢触发点钻
        chain = generate_chain(hole(10, 80), "不锈钢", 11)
        assert procs(chain) == ["spot_drill", "drill", "chamfer"]
        drill = chain[1]
        assert drill["cycle"] == "G83"

    def test_ultra_deep_gun_drill(self):
        chain = generate_chain(hole(10, 120), "铝合金", 11)   # H/D=12
        assert "gun_drill" in procs(chain)

    def test_large_hole_bore_only_path(self):
        chain = generate_chain(hole(90, 90), "铝合金", 11)    # D>80 不可钻
        assert procs(chain) == ["rough_bore", "semi_bore", "fine_bore", "chamfer"]


class TestFinishing:
    def test_ream_for_small_precise_hole(self):
        chain = generate_chain(hole(10, 20), "铝合金", 7)     # IT7 D<20 → 铰
        assert "ream" in procs(chain)
        assert "fine_bore" not in procs(chain)

    def test_semi_bore_for_it8(self):
        chain = generate_chain(hole(25, 50), "铝合金", 8)
        assert "semi_bore" in procs(chain)
        assert "fine_bore" not in procs(chain)

    def test_ra16_forces_ream(self):
        chain = generate_chain(hole(10, 20), "铝合金", 11, roughness_ra=1.6)
        assert "ream" in procs(chain)

    def test_ra04_switches_to_grind(self):
        chain = generate_chain(hole(10, 20), "铝合金", 7, roughness_ra=0.4)
        assert "grind" in procs(chain)
        assert "ream" not in procs(chain)                 # 放弃切削


class TestThreadAndBottom:
    def test_tap_for_small_thread(self):
        chain = generate_chain(hole(12, 24, thread={"spec": "M12"}), "铝合金", 11)
        assert "tap" in procs(chain)

    def test_thread_mill_for_stainless(self):
        chain = generate_chain(hole(12, 24, thread={"spec": "M12"}), "不锈钢", 11)
        assert "thread_mill" in procs(chain)
        assert "tap" not in procs(chain)

    def test_flat_bottom_blind_hole(self):
        chain = generate_chain(hole(20, 40, hole_type="blind", bottom_shape="flat"), "铝合金", 11)
        assert "flat_bottom_mill" in procs(chain)

    def test_chamfer_always_last(self):
        for spec in [hole(10, 20), hole(50, 100), hole(90, 90)]:
            chain = generate_chain(spec, "铝合金", 11)
            assert procs(chain)[-1] == "chamfer"
