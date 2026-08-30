"""工序排序：装夹分组内先粗后精、先面后孔、倒角最后。"""

ROUGH = {
    "drill", "peck_drill", "gun_drill", "u_drill", "spot_drill",
    "rough_face", "rough_pocket", "rough_step", "mill",
}
SEMI = {"semi_finish_pocket", "semi_bore", "semi_face", "semi_step"}
AUX = {"chamfer", "deburr"}

ROUGH_PRI = {
    "pocket": 1, "slot": 1, "step": 2, "face": 3, "plane": 3,
    "surface": 4, "hole": 5, "thread": 5,
}
FINISH_PRI = {
    "face": 1, "plane": 1, "hole": 2, "pocket": 3, "slot": 3,
    "step": 4, "surface": 5, "thread": 6,
}
FIXTURE_GROUP_FIELDS = ("fixture_group", "setup_group", "fixture_id", "setup_id")


def _axis_group(feature: dict) -> str | None:
    axis = feature.get("axis")
    if axis is None and isinstance(feature.get("pose"), dict):
        axis = feature["pose"].get("axis")
    if isinstance(axis, str):
        return axis or None
    if isinstance(axis, dict):
        values = (axis.get("x"), axis.get("y"), axis.get("z"))
    elif isinstance(axis, (tuple, list)) and len(axis) >= 3:
        values = axis[:3]
    else:
        return None
    try:
        x, y, z = (float(value or 0) for value in values)
    except (TypeError, ValueError):
        return None
    magnitude = (x * x + y * y + z * z) ** 0.5
    if magnitude <= 1e-9:
        return None
    normalized = (x / magnitude, y / magnitude, z / magnitude)
    dominant = max(range(3), key=lambda index: abs(normalized[index]))
    if abs(normalized[dominant]) >= 0.85:
        return f"{'+' if normalized[dominant] >= 0 else '-'}{'XYZ'[dominant]}"
    return ",".join(f"{value:.4f}" for value in normalized)


def feature_groups(features: list) -> tuple[dict, dict]:
    """返回显式夹具组和特征方向；无夹具标记的旧输入仍是单组。"""
    fixture_groups = {}
    direction_groups = {}
    for index, feature in enumerate(features, 1):
        feature_type = feature.get("type")
        feature_id = feature.get("id") or feature.get("feature_id") or f"{feature_type}-{index}"
        for field in FIXTURE_GROUP_FIELDS:
            value = feature.get(field)
            if value not in (None, ""):
                fixture_groups[feature_id] = str(value)
                break
        direction = feature.get("direction_group")
        if direction in (None, ""):
            direction = _axis_group(feature)
        if direction not in (None, ""):
            direction_groups[feature_id] = str(direction)
    return fixture_groups, direction_groups


def stage_of(proc: str) -> int:
    if proc in ROUGH:
        return 1
    if proc in SEMI:
        return 2
    return 3


def sort_steps(
    seq: list,
    feat_types: dict,
    direction_groups: dict | None = None,
    fixture_groups: dict | None = None,
) -> list:
    directions = direction_groups or {}
    fixtures = fixture_groups or {}

    def key(s: dict):
        proc = s.get("process") or ""
        feature_id = s.get("feature_id")
        ftype = feat_types.get(feature_id, "")
        st = stage_of(proc)
        pri = (ROUGH_PRI if st == 1 else FINISH_PRI).get(ftype, 9)
        fixture = fixtures.get(feature_id, "")
        direction = directions.get(feature_id, "")
        # 倒角仍显示为“精”，但排序阶段独立放到当前夹具组末尾。
        sort_stage = 4 if proc in AUX else st
        return (
            str(fixture),
            sort_stage,
            pri,
            str(direction),
            str(feature_id or ""),
            int(s.get("order") or 0),
        )

    out = sorted(list(seq), key=key)
    names = {1: "粗", 2: "半精", 3: "精"}
    for i, s in enumerate(out, 1):
        feature_id = s.get("feature_id")
        if feature_id in fixtures:
            s["fixture_group"] = fixtures[feature_id]
        if feature_id in directions:
            s["direction_group"] = directions[feature_id]
        s["order"] = i
        s["stage"] = names[stage_of(s.get("process") or "")]
    return out
