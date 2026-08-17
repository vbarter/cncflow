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


def stage_of(proc: str) -> int:
    if proc in ROUGH:
        return 1
    if proc in SEMI:
        return 2
    return 3


def sort_steps(seq: list, feat_types: dict, direction_groups: dict | None = None) -> list:
    groups = direction_groups or {}

    def key(s: dict):
        proc = s.get("process") or ""
        ftype = feat_types.get(s.get("feature_id"), "")
        st = stage_of(proc)
        aux = 1 if proc in AUX else 0
        pri = (ROUGH_PRI if st == 1 else FINISH_PRI).get(ftype, 9)
        dg = groups.get(s.get("feature_id"), 0)
        return (st, aux, pri, dg, str(s.get("feature_id") or ""), int(s.get("order") or 0))

    out = sorted(list(seq), key=key)
    names = {1: "粗", 2: "半精", 3: "精"}
    for i, s in enumerate(out, 1):
        s["order"] = i
        s["stage"] = names[stage_of(s.get("process") or "")]
    return out
