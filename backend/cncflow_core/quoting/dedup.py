"""工序去重：台阶吃肩顶 + 倒角合并 + 螺纹吃孔。不改识别、不改三库。"""


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


def _footprint(feat: dict) -> tuple[float, float] | None:
    length = _num(feat, "length")
    width = _num(feat, "width")
    if length <= 0 or width <= 0:
        return None
    return tuple(sorted((length, width), reverse=True))


def _is_step_shoulder_top(face: dict, steps: list[dict], tol: float = 3.0) -> bool:
    """同尺寸水平面是台阶轮廓的肩顶；整板顶面和侧面不是。"""
    if face.get("type") != "face":
        return False
    position = face.get("face_position")
    if position is None:
        position = (face.get("dimensions") or {}).get("face_position")
    if position not in (None, "", "水平", "top", "horizontal"):
        return False
    face_footprint = _footprint(face)
    if face_footprint is None:
        return False
    return any(
        (step_footprint := _footprint(step)) is not None
        and all(abs(a - b) <= tol for a, b in zip(face_footprint, step_footprint))
        for step in steps
    )


def absorb_step_faces(features: list) -> list:
    """台阶轮廓已包含肩台顶面加工；只吸收同尺寸水平面。"""
    steps = [feature for feature in features if feature.get("type") == "step"]
    if not steps:
        return list(features)
    return [
        feature
        for feature in features
        if not _is_step_shoulder_top(feature, steps)
    ]


def _timed_status(step: dict, t_cut: float) -> str:
    t_min = step.get("t_min")
    t_max = step.get("t_max")
    if t_min is not None and t_cut < float(t_min):
        return "低于下限"
    if t_max is not None and t_cut > float(t_max):
        return "需人工复核"
    return "ok"


def _time_signature(step: dict) -> tuple:
    """Only identical operations may share one tool change."""
    time = step.get("time") or {}

    def rounded(key):
        value = time.get(key)
        if value is None:
            value = step.get(key)
        try:
            return round(float(value), 6)
        except (TypeError, ValueError):
            return value

    return (
        step.get("process"),
        step.get("sku") or step.get("tool"),
        step.get("cycle"),
        step.get("side"),
        rounded("d"),
        rounded("n_act"),
        rounded("f"),
        rounded("cut"),
        rounded("passes"),
        time.get("formula") or step.get("formula"),
    )


def _aggregate_identical_steps(steps: list[dict]) -> dict:
    merged = dict(steps[0])
    time = dict(merged.get("time") or {})
    t_cut = sum(float((step.get("time") or {}).get("t_cut") or 0) for step in steps)
    t_tool = float(time.get("t_tool") or 0)
    cut = sum(float((step.get("time") or {}).get("cut") or 0) for step in steps)
    t_step = t_cut + t_tool
    time.update({
        "cut": round(cut, 4),
        "t_cut": round(t_cut, 4),
        "t_tool": round(t_tool, 4),
        "t_step": round(t_step, 4),
        "quantity": len(steps),
    })
    status = _timed_status(merged, t_cut)
    time["status"] = status
    merged.update({
        "minutes": round(t_step, 4),
        "time": time,
        "cut": time["cut"],
        "status": status,
        "quantity": len(steps),
        "merged_from": [step.get("feature_id") for step in steps],
    })
    return merged


def merge_identical_hole_steps(seq: list, feat_types: dict) -> list:
    """同刀同工艺的相同孔合成一行：切削时间累加，换刀只收一次。"""
    if not seq:
        return seq
    out = []
    groups: dict[tuple, list[dict]] = {}
    group_indexes: dict[tuple, list[int]] = {}
    group_feature_ids: dict[int, set] = {}
    for step in seq:
        feature_id = step.get("feature_id")
        if feat_types.get(feature_id) != "hole" or not step.get("time"):
            out.append(step)
            continue
        signature = _time_signature(step)
        target = next(
            (
                index
                for index in group_indexes.get(signature, [])
                if feature_id not in group_feature_ids[index]
            ),
            None,
        )
        if target is None:
            target = len(out)
            out.append(step)
            groups[target] = [step]
            group_indexes.setdefault(signature, []).append(target)
            group_feature_ids[target] = {feature_id}
        else:
            groups[target].append(step)
            group_feature_ids[target].add(feature_id)

    for index, steps in groups.items():
        if len(steps) > 1:
            out[index] = _aggregate_identical_steps(steps)
    for index, step in enumerate(out, 1):
        step["order"] = index
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
    timed = [s for s in chamfers if s.get("time")]
    tm = dict(timed[0]["time"]) if timed else None
    if tm:
        t_cut = sum(float(s["time"].get("t_cut") or 0) for s in timed)
        t_tool = sum(float(s["time"].get("t_tool") or 0) for s in timed)
        cut = sum(float(s["time"].get("cut") or 0) for s in timed)
        tm.update({
            "cut": round(cut, 4),
            "t_cut": round(t_cut, 4),
            "t_tool": round(t_tool, 4),
            "t_step": round(t_cut + t_tool, 4),
            "quantity": sum(int(s.get("quantity") or 1) for s in chamfers),
        })
        tm["status"] = _timed_status(merged, t_cut)
        merged["time"] = tm
    for key in ("formula", "n", "f", "cut", "passes", "t_min", "t_max", "status"):
        hit = tm.get(key) if tm and tm.get(key) is not None else None
        if hit is None:
            hit = next((s.get(key) for s in chamfers if s.get(key) is not None), None)
        if hit is None and tm and tm.get(key) is not None:
            hit = tm[key]
        if hit is not None:
            merged[key] = hit
        elif key == "status":
            merged.setdefault("status", "ok")
    if timed:
        merged["quantity"] = sum(int(s.get("quantity") or 1) for s in chamfers)
    out = others + [merged]
    for i, s in enumerate(out, 1):
        s["order"] = i
    return out
