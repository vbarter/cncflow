"""孔特征工时：切削长度 / Vc / fz → 每步 t，报价吃每步 t。"""
from __future__ import annotations

import math

FAMILY = {
    "铝合金": "铝合金",
    "钢": "钢",
    "普通碳钢": "钢",
    "不锈钢": "不锈钢",
    "钛合金": "钛合金",
    "淬硬钢": "淬硬钢",
    "铸铁": "铸铁",
}

# (材料族, 刀具组, 精加工) → (Vc m/min, fz mm/齿)
VC_FZ = {
    ("铝合金", "carbide", False): (200, 0.12),
    ("铝合金", "carbide", True): (250, 0.06),
    ("铝合金", "pcd", True): (400, 0.05),
    ("钢", "carbide", False): (120, 0.1),
    ("钢", "carbide", True): (150, 0.05),
    ("钢", "hss", False): (30, 0.08),
    ("钢", "cbn", True): (120, 0.03),
    ("不锈钢", "coated", False): (100, 0.08),
    ("不锈钢", "coated", True): (120, 0.04),
    ("钛合金", "coated", False): (60, 0.06),
    ("钛合金", "coated", True): (80, 0.03),
    ("淬硬钢", "cbn", False): (80, 0.05),
    ("淬硬钢", "cbn", True): (120, 0.02),
    ("铸铁", "carbide", False): (120, 0.1),
    ("铸铁", "carbide", True): (150, 0.05),
}

FINISH = {"ream", "bore", "semi_bore", "fine_bore", "chamfer", "tap", "thread_mill"}
DRILL = {"drill", "peck_drill", "gun_drill", "u_drill", "spot_drill"}
TAP = {"tap"}
REAM = {"ream"}
BORE = {"bore", "semi_bore", "fine_bore"}


def _family(material: str) -> str:
    if not material:
        return "铝合金"
    if material in FAMILY:
        return FAMILY[material]
    for key, fam in FAMILY.items():
        if key in material:
            return fam
    return "铝合金"


def _tool_group(base_material: str, coating: str) -> str:
    raw = f"{base_material or ''} {coating or ''}"
    if "PCD" in raw:
        return "pcd"
    if "CBN" in raw:
        return "cbn"
    if "HSS" in raw or "高速钢" in raw:
        return "hss"
    if coating and coating not in {"", "无涂层", "None"}:
        return "coated"
    return "carbide"


def _vc_fz(family: str, group: str, finish: bool) -> tuple[float, float]:
    for g in (group, "carbide", "coated"):
        hit = VC_FZ.get((family, g, finish))
        if hit:
            return hit
        hit = VC_FZ.get((family, g, not finish))
        if hit:
            return hit
    return (120, 0.08)


def _cut_passes(proc: str, hole: dict) -> tuple[float, int]:
    D = float(hole.get("diameter_mm") or 0) or 1.0
    H = float(hole.get("depth_mm") or 0)
    hd = H / D
    through = (hole.get("hole_type") or "through") == "through"
    if proc == "spot_drill":
        return 0.2 * D, 1
    if proc == "gun_drill" or (proc in DRILL and hd > 10):
        return H, 1
    if proc == "peck_drill" or (proc == "drill" and hd > 5):
        return H, max(1, math.ceil(H / (3 * D)))
    if proc in {"drill", "u_drill"}:
        return H + (0.3 * D if through else 0.0), 1
    if proc in REAM | BORE:
        return H, 1
    if proc == "thread_mill":
        return H or D, 1
    if proc == "flat_bottom_mill":
        return 0.3 * D, 1
    if proc == "chamfer":
        return 0.2 * D * (2 if through else 1), 1
    if proc == "tap":
        return H or D, 1
    return H or D, 1


def _bounds(proc: str, D: float) -> tuple[float, float] | None:
    if proc in DRILL:
        if D <= 6:
            return (0.05, 5.0)
        return (0.1, 5.0) if D <= 25 else (0.5, 20.0)
    if proc in TAP:
        return (0.1, 5.0) if D <= 24 else (1.0, 15.0)
    if proc in REAM:
        return (0.2, 10.0)
    if proc in BORE:
        return (1.0, 60.0)
    return None


def _max_rpm(factory: dict) -> float:
    rpms = [
        float(m.get("max_rpm") or 0)
        for m in (factory.get("machines") or [])
        if m.get("enabled", 1) and "3轴" in str(m.get("type") or "")
    ]
    return max(rpms) if rpms else 12000.0


def _toolchange_min(factory: dict) -> float:
    for m in factory.get("machines") or []:
        if m.get("enabled", 1) and m.get("tool_change_s"):
            return float(m["tool_change_s"]) / 60.0
    return 5.0 / 60.0


def compute(result: dict, factory: dict, material: str) -> dict:
    hole = result.get("hole") or {}
    D = float(hole.get("diameter_mm") or 0)
    family = _family(material)
    max_rpm = _max_rpm(factory)
    t_chg = _toolchange_min(factory)
    chain = result.get("tool_chain") or result.get("process_chain") or []
    steps, tags = [], []
    total = 0.0
    for i, step in enumerate(chain, 1):
        proc = step.get("process") or "drill"
        sel = step.get("selected_candidate") or {}
        attrs = sel.get("tool_attrs") or step.get("tool_attrs") or {}
        d = float(attrs.get("nominal_diameter_mm") or D or 1) or 1.0
        z = int(attrs.get("flutes") or 2) or 2
        group = _tool_group(attrs.get("base_material") or "硬质合金", attrs.get("coating") or "")
        finish = proc in FINISH
        vc, fz = _vc_fz(family, group, finish)
        n_req = 1000.0 * vc / (math.pi * d)
        n_act = min(n_req, max_rpm)
        if proc == "tap":
            n_act = min(n_act, 1000.0)
        compensate = 1.2 if n_act + 1e-6 < n_req else 1.0
        f = n_act * fz * z
        cut, passes = _cut_passes(proc, hole)
        if proc == "tap":
            pitch = float((hole.get("thread") or {}).get("pitch") or 1.25)
            t_cut = (cut / (n_act * pitch) if n_act and pitch else 0.0) * compensate
        else:
            t_cut = ((cut * passes / f) * compensate) if f else 0.0
        t_step = t_cut + t_chg
        bound = _bounds(proc, D)
        # 防错只打标不改 t：比的是切削时间 t_cut
        if bound and t_cut < bound[0]:
            tags.append("低于下限")
        elif bound and t_cut > bound[1]:
            tags.append("需人工复核")
        steps.append({
            "step": i,
            "process": proc,
            "d": round(d, 3),
            "n_req": round(n_req, 1),
            "n_act": round(n_act, 1),
            "f": round(f, 2),
            "cut": round(cut, 3),
            "passes": passes,
            "t_cut": round(t_cut, 4),
            "t_tool": round(t_chg, 4),
            "t_step": round(t_step, 4),
        })
        total += t_step
    return {
        "steps": steps,
        "total_min": round(total, 4),
        "tags": list(dict.fromkeys(tags)),
    }
