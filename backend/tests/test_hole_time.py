"""孔工时公式：切削长度 / Vc / fz，报价吃每步 t。"""
import math

from cncflow_core.quoting import hole_time


def _hole(D, H, hole_type="through"):
    return {
        "hole": {"diameter_mm": D, "depth_mm": H, "hole_type": hole_type},
        "tool_chain": [
            {"process": "drill", "tool_attrs": {"nominal_diameter_mm": D, "flutes": 2, "base_material": "硬质合金", "coating": "无涂层"}},
            {"process": "chamfer", "tool_attrs": {"nominal_diameter_mm": 6, "flutes": 2, "base_material": "硬质合金", "coating": "无涂层"}},
        ],
    }


def test_o8_cut_length_through():
    cut, passes = hole_time._cut_passes("drill", {"diameter_mm": 8, "depth_mm": 12, "hole_type": "through"})
    assert abs(cut - (12 + 0.3 * 8)) < 1e-6
    assert passes == 1


def test_zn010_peck_passes():
    cut, passes = hole_time._cut_passes("drill", {"diameter_mm": 3.3, "depth_mm": 26, "hole_type": "through"})
    assert abs(cut - 26) < 1e-6
    assert passes == math.ceil(26 / (3 * 3.3))


def test_o8_minutes_are_formula_not_bucket():
    factory = {"machines": [{"type": "3轴立式加工中心", "enabled": 1, "max_rpm": 12000}]}
    timed = hole_time.compute(_hole(8, 12), factory, "铝合金")
    drill = next(s for s in timed["steps"] if s["process"] == "drill")
    n_req = 1000 * 200 / (math.pi * 8)
    assert abs(drill["n_req"] - n_req) < 1
    assert drill["passes"] == 1
    assert abs(drill["cut"] - 14.4) < 0.01
    assert timed["total_min"] < 2.0  # 不再吃 D1=2 分钟桶
    assert timed["total_min"] > 0


def test_zn010_minutes_use_peck():
    factory = {"machines": [{"type": "3轴立式加工中心", "enabled": 1, "max_rpm": 12000}]}
    timed = hole_time.compute(_hole(3.3, 26), factory, "铝合金")
    drill = next(s for s in timed["steps"] if s["process"] == "drill")
    assert drill["passes"] == 3
    assert abs(drill["cut"] - 26) < 0.01
    assert timed["total_min"] < 2.0


def test_quote_eats_step_t(client):
    body = client.post("/api/v1/quotes", json={
        "material": "铝合金",
        "stock_type": "板材",
        "length": 80, "width": 60, "height": 12,
        "features": [{"type": "hole", "diameter_mm": 8, "depth_mm": 12, "hole_type": "through"}],
    }).get_json()
    plan = next(f["plan"] for f in body["features"] if f["type"] == "hole")
    assert plan.get("time")
    assert plan["time"]["total_min"] < 2
    drill = next(s for s in body["process_sequence"] if s.get("process") == "drill")
    assert drill.get("minutes") is not None
    assert drill["minutes"] < 2
    assert "time" in drill
    assert abs(drill["time"]["cut"] - 14.4) < 0.05


def test_drill_bound_flags_review():
    factory = {"machines": [{"type": "3轴立式加工中心", "enabled": 1, "max_rpm": 12000}]}
    timed = hole_time.compute(_hole(8, 12), factory, "铝合金")
    # 公式秒级低于 0.1min，只打标不改 t
    assert "低于下限" in timed["tags"]
    assert abs(drill := next(s for s in timed["steps"] if s["process"] == "drill")["t_cut"] - 0.0075) < 0.01
