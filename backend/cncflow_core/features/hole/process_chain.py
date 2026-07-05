"""孔工艺链生成（文档1模块二 Step1~9 + 文档2速查表）。

输出有序工序列表，每项 {"process": str, "cycle": str|None}。
遵循"由粗到精、由简到繁、风险前置"：点钻 → 主钻削/镗削 → 修底 → 精加工 → 螺纹 → 倒角。
"""
from ...common.rule_loader import load_rules
from .models import HoleSpec


def _thread_nominal_d(thread: dict, fallback: float) -> float:
    """从螺纹规格（如 M12）取公称直径，取不到则退回孔径。"""
    spec = str(thread.get("spec", ""))
    digits = "".join(ch for ch in spec if ch.isdigit() or ch == ".")
    try:
        return float(digits)
    except ValueError:
        return fallback


def generate_chain(hole: HoleSpec, material: str, tolerance_it: int, roughness_ra=None) -> list:
    rules = load_rules("hole/process_chain.yaml")
    d, hd, ld = hole.diameter_mm, hole.h_over_d, hole.h_over_d
    chain = []

    # ── 超大孔（D>80）：不可钻，走 粗镗→半精镗→精镗 专属路径 ──
    large = rules["large_hole"]
    if d > large["min_d"]:
        for proc in large["chain"]:
            chain.append({"process": proc, "cycle": rules["cycles"].get(proc)})
        chain.append({"process": "chamfer", "cycle": None})
        return chain

    # ── Step2 点钻判定（触发任一条件，作为第一道工序）──
    spot = rules["spot_drill_triggers"]
    if (
        hole.surface in spot["surfaces"]
        or d < spot["max_diameter"]
        or tolerance_it <= spot["max_tolerance_it"]
        or material in spot["materials"]
    ):
        chain.append({"process": "spot_drill", "cycle": None})

    # ── Step1/3/4 主钻削：H/D>10 枪钻；H/D>5 深孔钻(G83)；D>30 U钻；否则普通钻 ──
    deep = rules["deep_hole"]
    drill_cycle = rules["drill_cycle"]
    if hd > deep["gun_drill_min_hd"]:
        chain.append({"process": "gun_drill", "cycle": "枪钻循环"})
    else:
        cycle = "G81" if ld <= drill_cycle["g81_max_ld"] else "G83"
        if d > rules["primary_drill"]["u_drill_min_d"] and hd <= deep["g83_min_hd"]:
            chain.append({"process": "u_drill", "cycle": cycle})
        else:
            chain.append({"process": "drill", "cycle": cycle})

    # ── Step8 孔底形状：盲孔平底 → 立铣刀修底 ──
    if hole.hole_type == "blind" and hole.bottom_shape == "flat" and rules["bottom"]["flat_requires_mill"]:
        chain.append({"process": "flat_bottom_mill", "cycle": None})

    # ── Step5 高精度精加工 + Step6 粗糙度专项 ──
    fin = rules["finishing"]
    finishing = []  # 依序追加，去重
    if tolerance_it <= fin["bore_max_it"] and d >= fin["bore_min_d"]:
        finishing = ["semi_bore", "fine_bore"]           # 大孔径镗孔路径（半精镗→精镗）
    elif tolerance_it <= fin["ream_max_it"]:
        finishing = ["ream"]                             # 中小孔径铰孔
    elif tolerance_it <= fin["semi_bore_max_it"]:
        finishing = ["semi_bore"]                        # IT8 半精镗修形

    if roughness_ra is not None:
        for band in rules["roughness"]:
            if roughness_ra <= band["max_ra"]:
                action = band["action"]
                if action == "grind":
                    finishing = ["grind"]                # 放弃切削，采用磨削
                elif action == "fine_bore" and "fine_bore" not in finishing and "grind" not in finishing:
                    finishing = finishing + ["fine_bore"] if finishing else ["semi_bore", "fine_bore"]
                elif action == "ream" and not finishing:
                    finishing = ["ream"]
                break

    for proc in finishing:
        chain.append({"process": proc, "cycle": rules["cycles"].get(proc)})

    # ── Step7 螺纹加工 ──
    if hole.thread:
        thread_d = _thread_nominal_d(hole.thread, d)
        thr = rules["thread"]
        if (
            thread_d > thr["tap_max_d"]
            or material in thr["thread_mill_materials"]
            or hd > thr["thread_mill_min_hd"]
        ):
            chain.append({"process": "thread_mill", "cycle": None})
        else:
            chain.append({"process": "tap", "cycle": None})

    # ── Step9 倒角（最终阶段，去锐边防划伤）──
    if rules["chamfer_always"]:
        chain.append({"process": "chamfer", "cycle": None})

    return chain
