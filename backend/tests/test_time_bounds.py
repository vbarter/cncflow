"""横切 t_min/t_max：有表工步打标，不改 cut/t，仍出价。"""


def _flags(step):
    return (step.get("time") or {}).get("tags") or []


def test_o8_hole_and_face_below_min(client):
    body = client.post("/api/v1/quotes", json={
        "material": "铝合金",
        "stock_type": "板材",
        "length": 80, "width": 60, "height": 12,
        "features": [
            {"type": "hole", "feature_id": "hole-0", "diameter_mm": 8, "depth_mm": 12, "hole_type": "through"},
            {"type": "face", "feature_id": "face-1", "length": 80, "width": 60},
        ],
    }).get_json()
    assert body["status"] == "quoted"
    assert body["quote"]["amount"] > 0
    assert [s["name"] for s in body["process_sequence"]] == ["面粗", "钻孔", "倒角"]
    face = next(s for s in body["process_sequence"] if s["process"] == "rough_face")
    drill = next(s for s in body["process_sequence"] if s["process"] == "drill")
    chamfer = next(s for s in body["process_sequence"] if s["process"] == "chamfer")
    assert abs(face["time"]["cut"] - 85.714) < 0.2
    assert 0.12 < face["time"]["t_cut"] < 0.16  # 标准 Vc×1.1 ≈8.2s
    assert abs(drill["time"]["cut"] - 14.4) < 0.05
    assert 0.005 < drill["time"]["t_cut"] < 0.009  # ≈0.41s
    assert "低于下限" in _flags(face)
    assert "低于下限" in _flags(drill)
    assert "低于下限" not in _flags(chamfer)
    assert "低于下限" in body["risk"]["tags"]
    assert body["equipment"]["model"] == "VMC850E"
    assert body["equipment"]["hourly_rate"] == 120


def test_open_slot_rough_and_face_below_min(client):
    body = client.post("/api/v1/quotes", json={
        "material": "铝合金",
        "stock_type": "板材",
        "length": 80, "width": 60, "height": 12,
        "features": [
            {"type": "slot", "feature_id": "slot-0", "length": 40, "width": 10, "depth": 8, "corner_radius": 3, "pocket_type": "开放"},
            {"type": "face", "feature_id": "face-0", "length": 80, "width": 60},
        ],
    }).get_json()
    assert body["status"] == "quoted"
    assert [s["name"] for s in body["process_sequence"]] == ["槽粗", "面粗", "倒角"]
    slot = next(s for s in body["process_sequence"] if s["process"] == "rough_pocket")
    face = next(s for s in body["process_sequence"] if s["process"] == "rough_face")
    assert abs(slot["time"]["cut"] - 95.238) < 0.3
    assert slot["time"]["passes"] == 8
    assert 0.15 < slot["time"]["t_cut"] < 0.22  # ≈11s
    assert "低于下限" in _flags(slot)
    assert "低于下限" in _flags(face)
    assert "低于下限" in body["risk"]["tags"]


def test_m8_tap_and_table_steps_below_min(client):
    body = client.post("/api/v1/quotes", json={
        "material": "铝合金",
        "stock_type": "板材",
        "length": 40, "width": 40, "height": 12,
        "features": [
            {"type": "face", "feature_id": "face-2", "length": 40, "width": 40},
            {"type": "thread", "feature_id": "thread-0", "nominal_d": 8, "pitch": 1.25, "thread_length": 12},
        ],
    }).get_json()
    assert body["status"] == "quoted"
    assert [s["name"] for s in body["process_sequence"]] == ["面粗", "底孔", "攻牙", "倒角"]
    tap = next(s for s in body["process_sequence"] if s["process"] == "tap")
    drill = next(s for s in body["process_sequence"] if s["process"] == "drill")
    face = next(s for s in body["process_sequence"] if s["process"] == "rough_face")
    chamfer = next(s for s in body["process_sequence"] if s["process"] == "chamfer")
    assert tap["time"]["n_act"] <= 1000
    assert abs(tap["time"]["t_cut"] - 0.0096) < 0.001
    assert "低于下限" in _flags(tap)
    assert "低于下限" in _flags(drill)
    assert "低于下限" in _flags(face)
    assert "低于下限" not in _flags(chamfer)
    assert "低于下限" in body["risk"]["tags"]
    assert body["equipment"]["model"] == "VMC850E"
