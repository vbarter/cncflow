"""Slice 2：工步中间量 + validation 防错 + 材料/夹具分行。不含九维风险。"""

KEYS = ("formula", "n", "f", "cut", "passes", "t_min", "t_max", "status")


def _o8():
    return {
        "material": "铝合金", "stock_type": "板材",
        "length": 80, "width": 60, "height": 12,
        "features": [
            {"type": "hole", "feature_id": "hole-0", "diameter_mm": 8, "depth_mm": 12, "hole_type": "through"},
            {"type": "face", "feature_id": "face-1", "length": 80, "width": 60},
        ],
    }


def _slot():
    return {
        "material": "铝合金", "stock_type": "板材",
        "length": 80, "width": 60, "height": 12,
        "features": [
            {"type": "slot", "feature_id": "slot-0", "length": 40, "width": 10, "depth": 8, "corner_radius": 3, "pocket_type": "开放"},
            {"type": "face", "feature_id": "face-0", "length": 80, "width": 60},
        ],
    }


def _m8():
    return {
        "material": "铝合金", "stock_type": "板材",
        "length": 40, "width": 40, "height": 12,
        "features": [
            {"type": "face", "feature_id": "face-2", "length": 40, "width": 40},
            {"type": "thread", "feature_id": "thread-0", "nominal_d": 8, "pitch": 1.25, "thread_length": 12},
        ],
    }


def _blob(obj):
    return str(obj)


def _assert_step_params(step):
    for key in KEYS:
        assert key in step, (key, step)
    tm = step.get("time") or {}
    if tm.get("n_act") is not None:
        assert step["n"] == tm["n_act"]
        assert tm.get("n") == tm["n_act"]
    if tm.get("f") is not None:
        assert step["f"] == tm["f"]
    if tm.get("cut") is not None:
        assert step["cut"] == tm["cut"]
    if tm.get("passes") is not None:
        assert step["passes"] == tm["passes"]
    assert step["formula"] in {"t=cut*passes/f", "t=cut*passes/f*k", "t=cut/(n*P)"}
    assert step["status"] in {"ok", "低于下限", "需人工复核"}
    if step["status"] != "ok":
        assert step["t_min"] is not None and step["t_max"] is not None


def _assert_costs_split(body):
    items = {i["code"]: i["amount"] for i in body["cost_items"]}
    assert "MAT" in items
    assert "FIX" in items
    ui = body["ui_cost"]
    assert "material" in ui
    assert "fixture" in ui
    assert ui["material"] == items["MAT"]
    assert ui["fixture"] == items["FIX"]
    assert abs(ui["setup"] - (items["SETUP"] + items["MACHINE_SETUP"])) < 0.02


def _assert_validation(body):
    val = body["validation"]
    assert isinstance(val, dict)
    assert "ok" in val and "items" in val
    blob = _blob(val)
    assert "rule_id" not in blob
    assert "D1" not in blob and "D9" not in blob
    flagged = [s for s in body["process_sequence"] if s.get("status") and s["status"] != "ok"]
    assert val["ok"] is (not flagged)
    assert len(val["items"]) == len(flagged)
    for item in val["items"]:
        assert item["status"] in {"低于下限", "需人工复核"}
        assert "rule_id" not in item


def _assert_smoke(body, names, hours=0.1):
    assert body["status"] == "quoted"
    assert body["quote"]["amount"] > 0
    assert [s["name"] for s in body["process_sequence"]] == names
    assert body["hours"]["total"] == hours
    assert body["quote"]["hours"] == hours
    for step in body["process_sequence"]:
        _assert_step_params(step)
    _assert_costs_split(body)
    _assert_validation(body)
    assert "rule_id" not in _blob(body.get("validation"))


def test_o8_plate_emits_step_params(client):
    body = client.post("/api/v1/quotes", json=_o8()).get_json()
    _assert_smoke(body, ["粗铣", "钻孔", "倒角"])
    face = next(s for s in body["process_sequence"] if s["process"] == "rough_face")
    drill = next(s for s in body["process_sequence"] if s["process"] == "drill")
    chamfer = next(s for s in body["process_sequence"] if s["process"] == "chamfer")
    assert face["formula"] == "t=cut*passes/f"
    assert abs(face["cut"] - 85.714) < 0.2
    assert face["t_min"] == 1.0 and face["t_max"] == 120.0
    assert face["status"] == "低于下限"
    assert abs(drill["cut"] - 14.4) < 0.05
    assert drill["t_min"] == 0.1 and drill["t_max"] == 5.0
    assert drill["status"] == "低于下限"
    assert chamfer["status"] == "ok"
    assert chamfer["t_min"] is None and chamfer["t_max"] is None
    assert body["validation"]["ok"] is False
    assert {i["process"] for i in body["validation"]["items"]} >= {"rough_face", "drill"}


def test_open_slot_emits_step_params(client):
    body = client.post("/api/v1/quotes", json=_slot()).get_json()
    _assert_smoke(body, ["粗铣", "粗铣", "倒角"])
    slot = next(s for s in body["process_sequence"] if s["process"] == "rough_pocket")
    assert slot["formula"] == "t=cut*passes/f"
    assert slot["passes"] == 8
    assert abs(slot["cut"] - 95.238) < 0.3
    assert slot["t_min"] == 2.0 and slot["t_max"] == 180.0
    assert slot["status"] == "低于下限"


def test_m8_thread_emits_step_params(client):
    body = client.post("/api/v1/quotes", json=_m8()).get_json()
    _assert_smoke(body, ["粗铣", "钻孔", "攻牙", "倒角"])
    tap = next(s for s in body["process_sequence"] if s["process"] == "tap")
    assert tap["formula"] == "t=cut/(n*P)"
    assert tap["n"] <= 1000
    assert tap["t_min"] == 0.1 and tap["t_max"] == 5.0
    assert tap["status"] == "低于下限"
    assert abs(tap["time"]["t_cut"] - 0.0096) < 0.001
