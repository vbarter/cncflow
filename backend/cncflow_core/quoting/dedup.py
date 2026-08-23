"""工序去重：倒角合并 + 螺纹吃孔。不改识别、不改三库。"""


def _num(feat: dict, *keys) -> float:
    for k in keys:
        v = feat.get(k)
        if v is not None and v != "":
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    dims = feat.get("dimensions") or {}
    for k in keys:
        v = dims.get(k)
        if v is not None and v != "":
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    return 0.0


def _loc(feat: dict):
    loc = feat.get("location")
    if not loc and isinstance(feat.get("pose"), dict):
        loc = feat["pose"].get("origin") or feat["pose"].get("location")
    if not isinstance(loc, dict):
        return None
    try:
        return (float(loc.get("x") or 0), float(loc.get("y") or 0), float(loc.get("z") or 0))
    except (TypeError, ValueError):
        return None


def _near(a, b, tol=3.0) -> bool:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5 <= tol


def _same_bore(hole: dict, thread: dict) -> bool:
    hd = _num(hole, "diameter_mm", "diameter", "nominal_d")
    td = _num(thread, "nominal_d", "diameter_mm", "diameter")
    if hd <= 0 or td <= 0:
        return False
    pitch = _num(thread, "pitch") or 1.25
    diam_hit = abs(hd - td) <= 0.8 or abs(hd - (td - pitch)) <= 0.8
    if not diam_hit:
        return False
    hl, tl = _loc(hole), _loc(thread)
    if hl and tl:
        return _near(hl, tl)
    return True


def absorb_holes(features: list) -> list:
    """已选螺纹吃掉同位置同径（或底孔径）的孔，避免再出一套钻孔+倒角。"""
    threads = [f for f in features if f.get("type") == "thread"]
    if not threads:
        return list(features)
    out = []
    for f in features:
        if f.get("type") == "hole" and any(_same_bore(f, t) for t in threads):
            continue
        out.append(f)
    return out


def merge_chamfers(seq: list) -> list:
    """同装夹倒角合成一条，放最后。工时/金额相加，不改 t 公式。"""
    if not seq:
        return seq
    chamfers = [s for s in seq if (s.get("process") or "") == "chamfer"]
    others = [s for s in seq if (s.get("process") or "") != "chamfer"]
    if len(chamfers) <= 1:
        return seq
    minutes = sum(float(s["minutes"]) for s in chamfers if s.get("minutes") is not None)
    amount = sum(float(s["amount"]) for s in chamfers if s.get("amount") is not None)
    sku = next((s.get("sku") for s in chamfers if s.get("sku")), None)
    merged = {
        "process": "chamfer",
        "name": "倒角",
        "sku": sku,
        "tool": sku or "倒角",
        "feature_id": chamfers[0].get("feature_id"),
        "cycle": None,
        "merged_from": [s.get("feature_id") for s in chamfers],
        "stage": "精",
    }
    if minutes:
        merged["minutes"] = round(minutes, 4)
    if amount:
        merged["amount"] = round(amount, 2)
    tm = next((s.get("time") for s in chamfers if s.get("time")), None)
    if tm:
        merged["time"] = tm
    for key in ("formula", "n", "f", "cut", "passes", "t_min", "t_max", "status"):
        hit = next((s.get(key) for s in chamfers if s.get(key) is not None), None)
        if hit is None and tm and tm.get(key) is not None:
            hit = tm[key]
        if hit is not None:
            merged[key] = hit
        elif key == "status":
            merged.setdefault("status", "ok")
    out = others + [merged]
    for i, s in enumerate(out, 1):
        s["order"] = i
    return out
