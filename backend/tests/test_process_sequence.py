"""工序排序：IT10 两段粗→精，倒角最后。"""
from cncflow_core.quoting import sequence


def _seq(*rows):
    out = []
    for i, (fid, ftype, proc, name) in enumerate(rows, 1):
        out.append({"order": i, "feature_id": fid, "process": proc, "name": name, "_type": ftype})
    return out


def _types(seq):
    return {s["feature_id"]: s["_type"] for s in seq}


def _names(seq):
    return [s.get("name") or s.get("process") for s in seq]


def test_o8_face_then_drill_then_chamfer():
    seq = _seq(
        ("hole-1", "hole", "drill", "钻孔"),
        ("hole-1", "hole", "chamfer", "入口倒角"),
        ("hole-1", "hole", "chamfer", "出口倒角"),
        ("face-2", "face", "rough_face", "粗铣"),
        ("face-2", "face", "chamfer", "倒角"),
    )
    got = sequence.sort_steps(seq, _types(seq))
    core = [s for s in got if s["process"] != "chamfer"]
    assert _names(core) == ["粗铣", "钻孔"]
    assert all(s["process"] == "chamfer" for s in got[len(core):])
    hole_ch = [s["name"] for s in got if s["feature_id"] == "hole-1" and s["process"] == "chamfer"]
    assert hole_ch == ["入口倒角", "出口倒角"]


def test_open_slot_pocket_then_face_then_chamfer():
    seq = _seq(
        ("slot-1", "slot", "rough_pocket", "粗铣"),
        ("slot-1", "slot", "chamfer", "倒角"),
        ("face-2", "face", "rough_face", "粗铣"),
        ("face-2", "face", "chamfer", "倒角"),
    )
    got = sequence.sort_steps(seq, _types(seq))
    assert [s["feature_id"] for s in got if s["process"] != "chamfer"] == ["slot-1", "face-2"]
    assert all(s["process"] == "chamfer" for s in got[2:])


def test_m8_face_drill_tap_chamfer():
    seq = _seq(
        ("face-1", "face", "rough_face", "粗铣"),
        ("face-1", "face", "chamfer", "倒角"),
        ("thread-2", "thread", "drill", "钻孔"),
        ("thread-2", "thread", "tap", "攻牙"),
    )
    got = sequence.sort_steps(seq, _types(seq))
    assert _names(got) == ["粗铣", "钻孔", "攻牙", "倒角"]
