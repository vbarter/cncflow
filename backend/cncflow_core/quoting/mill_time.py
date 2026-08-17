"""槽/面/螺纹/台阶工时：切削长度 / Vc/fz → 每步 t。不改孔公式。"""
from __future__ import annotations

import math

from . import hole_time

ROUGH = {
    "rough_face", "rough_pocket", "rough_step", "mill", "drill",
    "peck_drill", "gun_drill", "u_drill", "spot_drill",
}
FINISH = {
    "semi_face", "finish_face", "semi_finish_pocket", "finish_pocket",
    "semi_step", "finish_step", "chamfer", "tap", "thread_mill",
    "rest_mill", "grind",
}


def _num(*vals) -> float:
    for v in vals:
        if v in (None, ""):
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            pass
    return 0.0


def _dims(feat: dict, result: dict) -> dict:
    m = result.get("metrics") or {}
    return {
        "L": _num(feat.get("length"), m.get("length"), result.get("length")),
        "W": _num(feat.get("width"), m.get("width"), result.get("width")),
        "H": _num(feat.get("depth"), feat.get("depth_mm"), feat.get("height"),
                  feat.get("thread_length"), m.get("depth"), result.get("height"),
                  result.get("thread_length")),
        "D": _num(feat.get("nominal_d"), feat.get("diameter_mm"), feat.get("diameter"),
                  result.get("diameter_mm"), result.get("nominal_d")),
        "P": _num(feat.get("pitch"), result.get("pitch")) or 1.25,
        "area": _num(m.get("area")),
    }


def _lookup_tool(factory: dict, attrs: dict, sku: str | None) -> dict:
    tools = factory.get("tools") or []
    if sku:
        for t in tools:
            if t.get("sku") == sku:
                return t
    cat = attrs.get("category")
    d = attrs.get("nominal_diameter_mm")
    if cat and d is not None:
        hits = [t for t in tools if t.get("category") == cat and t.get("in_stock", 1)]
        if hits:
            return min(hits, key=lambda t: abs(float(t.get("diameter_mm") or 0) - float(d)))
    return {}


def _cut_passes(ftype: str, proc: str, dims: dict, d: float) -> tuple[float, int]:
    L, W, H, D, area = dims["L"], dims["W"], dims["H"], dims["D"], dims["area"]
    if not area and L and W:
        area = L * W
    d = d or 1.0
    if proc == "chamfer":
        if ftype in {"face", "pocket", "slot"}:
            return 2 * (L + W) * 0.2, 1
        if ftype == "step":
            return L * 0.2, 1
        return 0.2 * (D or d), 1
    if proc in {"rough_face", "semi_face"}:
        return (area / (0.7 * d)) if d else 0.0, max(1, int(math.ceil((H or 1) / 1.0))) if proc == "rough_face" else 1
    if proc == "finish_face":
        return (area / (0.5 * d)) if d else 0.0, 1
    if proc == "rough_pocket":
        width_pass = max(1.0, W / (0.7 * d)) if d else 1.0
        return L * width_pass, max(1, int(math.ceil((H or 1) / 1.0)))
    if proc in {"semi_finish_pocket", "finish_pocket", "rest_mill"}:
        cut = 2 * (L + W) * (0.1 if proc == "rest_mill" else 1)
        return cut, 1
    if proc == "rough_step":
        layers = max(1, int(math.ceil((H or 1) / 1.0)))
        return L * layers, layers
    if proc in {"semi_step", "finish_step"}:
        return L, 1
    if proc in {"drill", "peck_drill", "u_drill", "spot_drill", "gun_drill"}:
        return (H or D or 0), 1
    if proc == "tap":
        return H or D or 0, 1
    if proc == "thread_mill":
        return H or D or 0, 1
    return max(L, area, H, 1.0), 1


def compute(ftype: str, feat: dict, result: dict, factory: dict, material: str) -> dict:
    dims = _dims(feat, result)
    family = hole_time._family(material)
    max_rpm = hole_time._max_rpm(factory)
    t_chg = hole_time._toolchange_min(factory)
    chain = result.get("tool_chain") or result.get("process_chain") or []
    steps, tags = [], []
    total = 0.0
    for i, step in enumerate(chain, 1):
        proc = step.get("process") or "mill"
        sel = step.get("selected_candidate") or {}
        attrs = dict(sel.get("tool_attrs") or step.get("tool_attrs") or {})
        sku = None
        if sel.get("candidate_type") == "sku":
            sku = sel.get("candidate_id")
        sku = sku or next((c for c in (step.get("sku_candidates") or []) if c), None)
        tool = _lookup_tool(factory, attrs, sku)
        d = _num(tool.get("diameter_mm"), attrs.get("nominal_diameter_mm"), dims["D"]) or 1.0
        z = int(attrs.get("flutes") or tool.get("flutes") or (6 if d >= 50 else 3)) or 2
        group = hole_time._tool_group(
            attrs.get("base_material") or tool.get("base_material") or "硬质合金",
            attrs.get("coating") or tool.get("coating") or "",
        )
        finish = proc in FINISH
        vc, fz = hole_time._vc_fz(family, group, finish)
        n_req = 1000.0 * vc / (math.pi * d)
        n_act = min(n_req, max_rpm)
        if proc == "tap":
            n_act = min(n_act, 1000.0)
        compensate = 1.2 if n_act + 1e-6 < n_req else 1.0
        f = n_act * fz * z
        cut, passes = _cut_passes(ftype, proc, dims, d)
        if proc == "tap":
            pitch = dims["P"] or 1.25
            t_cut = (cut / (n_act * pitch) if n_act and pitch else 0.0)
        else:
            t_cut = ((cut * passes / f) * compensate) if f else 0.0
        t_step = t_cut + t_chg
        flag = hole_time._flag(t_cut, hole_time._bounds(proc, d))
        if flag:
            tags.append(flag)
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
            "tags": [flag] if flag else [],
        })
        total += t_step
    return {"steps": steps, "total_min": round(total, 4), "tags": list(dict.fromkeys(tags))}
