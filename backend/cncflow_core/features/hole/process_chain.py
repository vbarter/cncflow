"""孔工艺链生成（文档1模块二 Step1~9 + 文档2速查表）。

输出有序工序列表，每项 {"process": str, "cycle": str|None}。
遵循冻结顺序：点钻 → 基础钻孔/镗削 → 精加工 → 螺纹 → 修底 → 倒角。
"""
import re

from ...common.rule_loader import load_rules
from .models import HoleSpec


def _thread_nominal_d(thread: dict, fallback: float) -> float:
    """从螺纹规格（如 M12、M8×1.25）取公称直径，取不到则退回孔径。"""
    spec = str(thread.get("spec", ""))
    match = re.search(r"[Mm]\s*(\d+(?:\.\d+)?)", spec)
    return float(match.group(1)) if match else fallback


def _select_finishing(
    hole: HoleSpec,
    tolerance_it: int,
    roughness_ra,
    rules: dict,
) -> list[str]:
    """F01–F09：按冻结优先级只返回一个精加工族。"""
    d, hd = hole.diameter_mm, hole.h_over_d
    fin = rules["finishing"]
    ra = fin["default_ra"] if roughness_ra is None else float(roughness_ra)

    # F01：微孔的主工序已含 EDM/超高速钻削，禁止再镗或铰。
    if d < fin["micro_hole_max_d"]:
        return []

    # F02/F03/F09：磨削优先于所有切削精加工。
    if (
        hd > fin["deep_grind_min_hd"]
        and tolerance_it <= fin["deep_grind_max_it"]
    ) or ra <= fin["grind_max_ra"]:
        return ["grind"]

    # F04：半精镗→精镗是一条镗孔路径，不是两个竞争族。
    if d >= fin["bore_min_d"] and tolerance_it <= fin["bore_max_it"]:
        return ["semi_bore", "fine_bore"]

    # F05/F06：Ra 边界决定精镗或铰孔，二者互斥。
    if d < fin["bore_min_d"] and tolerance_it <= fin["fine_bore_max_it"]:
        if ra <= fin["fine_bore_max_ra"]:
            return ["fine_bore"]
        if fin["ream_min_ra"] < ra <= fin["ream_max_ra"]:
            return ["ream"]

    # F07：IT8 只半精镗；F03 已在上方按 F09 优先处理。
    if tolerance_it == fin["semi_bore_it"]:
        return ["semi_bore"]

    # F08：默认 IT11/Ra3.2 明确无精加工。
    if (
        tolerance_it > fin["no_finish_min_it"]
        and ra >= fin["no_finish_min_ra"]
    ):
        return []

    # 未命中 F01–F08 的组合也不推断额外精加工。
    return []


def _select_thread_process(
    hole: HoleSpec,
    material: str,
    rules: dict,
) -> str | None:
    """T01–T03：无螺纹返回空，否则只选攻牙或螺纹铣之一。"""
    if not hole.thread:
        return None

    thread_d = _thread_nominal_d(hole.thread, hole.diameter_mm)
    thread = rules["thread"]
    if (
        thread_d > thread["tap_max_d"]
        or material in thread["thread_mill_materials"]
        or hole.h_over_d > thread["thread_mill_min_hd"]
    ):
        return "thread_mill"
    return "tap"


def generate_chain(hole: HoleSpec, material: str, tolerance_it: int, roughness_ra=None) -> list:
    rules = load_rules("hole/process_chain.yaml")
    d, hd = hole.diameter_mm, hole.h_over_d
    chain = []

    # ── 超大孔（D>80）：不可钻，以粗镗替代钻削；精加工仍服从 F01–F09 ──
    large = rules["large_hole"]
    if d > large["min_d"]:
        primary_process = large["primary"]
        chain.append({
            "process": primary_process,
            "cycle": rules["cycles"].get(primary_process),
        })
    else:
        # ── Step2 点钻判定（触发任一条件，作为第一道工序）──
        spot = rules["spot_drill_triggers"]
        if (
            hole.surface in spot["surfaces"]
            or d < spot["max_diameter"]
            or tolerance_it <= spot["max_tolerance_it"]
            or material in spot["materials"]
        ):
            chain.append({"process": "spot_drill", "cycle": None})

        # ── 基础钻孔：每个孔只选一道主工序；微孔与极限深孔替代常规钻削 ──
        deep = rules["deep_hole"]
        primary = rules["primary_drill"]
        if d < primary["micro_hole_max_d"]:
            chain.append({
                "process": "micro_hole",
                "cycle": None,
                "name": "微孔 EDM / 超高速钻削",
            })
        elif hd > deep["gun_drill_max_hd"]:
            chain.append({
                "process": "special_hole",
                "cycle": None,
                "name": "特种加工 / EDM",
            })
        elif hd > deep["gun_drill_min_hd"]:
            chain.append({"process": "gun_drill", "cycle": "枪钻循环"})
        else:
            cycle = "G83" if hd >= deep["g83_min_hd"] else "G81"
            if d > primary["u_drill_min_d"] and hd < deep["g83_min_hd"]:
                chain.append({"process": "u_drill", "cycle": cycle})
            else:
                chain.append({"process": "drill", "cycle": cycle})

    # ── 精加工：F01–F09 只选一个工艺族 ──
    for proc in _select_finishing(hole, tolerance_it, roughness_ra, rules):
        chain.append({"process": proc, "cycle": rules["cycles"].get(proc)})

    # ── 螺纹加工：T01–T03 只追加一个选择结果 ──
    thread_process = _select_thread_process(hole, material, rules)
    if thread_process:
        chain.append({"process": thread_process, "cycle": None})

    # ── 修底：冻结在精加工、螺纹之后，倒角之前 ──
    if (
        hole.hole_type == "blind"
        and hole.bottom_shape == "flat"
        and rules["bottom"]["flat_requires_mill"]
    ):
        chain.append({"process": "flat_bottom_mill", "cycle": None})

    # ── 倒角（通孔双面，盲孔单面）──
    if rules["chamfer_always"]:
        if hole.hole_type == "through":
            chain.append({
                "process": "chamfer",
                "cycle": None,
                "name": "入口倒角",
                "side": "entry",
            })
            chain.append({
                "process": "chamfer",
                "cycle": None,
                "name": "出口倒角",
                "side": "exit",
            })
        else:
            chain.append({"process": "chamfer", "cycle": None, "name": "倒角"})

    return chain
