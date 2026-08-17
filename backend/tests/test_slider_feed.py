"""滑轴倍率喂进 n/f/passes/t，禁止事后除分钟。"""


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


def test_standard_o8_n_t(client):
    body = client.post("/api/v1/quotes", json={**_o8(), "slider": "标准"}).get_json()
    assert [s["name"] for s in body["process_sequence"]] == ["粗铣", "钻孔", "倒角"]
    face = next(s for s in body["process_sequence"] if s["process"] == "rough_face")
    drill = next(s for s in body["process_sequence"] if s["process"] == "drill")
    assert abs(face["time"]["n_act"] - 875) < 8
    assert 7.5 < face["time"]["t_cut"] * 60 < 9.0  # ≈8.2s
    assert abs(face["time"]["cut"] - 85.714) < 0.2
    assert abs(drill["time"]["n_act"] - 8754) < 20
    assert 0.35 < drill["time"]["t_cut"] * 60 < 0.48  # ≈0.41s
    assert abs(drill["time"]["cut"] - 14.4) < 0.05
    assert "低于下限" in (body["risk"]["tags"] or [])
    assert body["equipment"]["model"] == "VMC850E"


def test_standard_slot_n_t(client):
    body = client.post("/api/v1/quotes", json={**_slot(), "slider": "标准"}).get_json()
    slot = next(s for s in body["process_sequence"] if s["process"] == "rough_pocket")
    assert abs(slot["time"]["n_act"] - 11671) < 30
    assert slot["time"]["passes"] == 8
    assert 10 < slot["time"]["t_cut"] * 60 < 13  # ≈11s
    assert abs(slot["time"]["cut"] - 95.238) < 0.3


def test_standard_m8_n_t(client):
    body = client.post("/api/v1/quotes", json={**_m8(), "slider": "标准"}).get_json()
    assert [s["name"] for s in body["process_sequence"]] == ["粗铣", "钻孔", "攻牙", "倒角"]
    face = next(s for s in body["process_sequence"] if s["process"] == "rough_face")
    tap = next(s for s in body["process_sequence"] if s["process"] == "tap")
    assert abs(face["time"]["n_act"] - 1401) < 10
    assert 2.8 < face["time"]["t_cut"] * 60 < 3.8  # ≈3.3s
    assert tap["time"]["n_act"] == 1000
    assert abs(tap["time"]["t_cut"] - 0.0096) < 0.001


def test_conservative_same_parts_n_down_t_up(client):
    o8s = client.post("/api/v1/quotes", json={**_o8(), "slider": "标准"}).get_json()
    o8c = client.post("/api/v1/quotes", json={**_o8(), "slider": "保守"}).get_json()
    face_s = next(s for s in o8s["process_sequence"] if s["process"] == "rough_face")
    face_c = next(s for s in o8c["process_sequence"] if s["process"] == "rough_face")
    drill_c = next(s for s in o8c["process_sequence"] if s["process"] == "drill")
    assert abs(face_c["time"]["n_act"] - 676) < 8
    assert face_c["time"]["n_act"] < face_s["time"]["n_act"]
    assert face_c["time"]["t_cut"] > face_s["time"]["t_cut"]
    assert abs(face_c["time"]["cut"] - 85.714) < 0.2
    assert abs(drill_c["time"]["n_act"] - 6764) < 20
    assert 0.50 < drill_c["time"]["t_cut"] * 60 < 0.75  # ≈0.6s
    assert [s["name"] for s in o8c["process_sequence"]] == ["粗铣", "钻孔", "倒角"]

    slot_s = client.post("/api/v1/quotes", json={**_slot(), "slider": "标准"}).get_json()
    slot_c = client.post("/api/v1/quotes", json={**_slot(), "slider": "保守"}).get_json()
    rs = next(s for s in slot_s["process_sequence"] if s["process"] == "rough_pocket")
    rc = next(s for s in slot_c["process_sequence"] if s["process"] == "rough_pocket")
    assert abs(rc["time"]["n_act"] - 9019) < 30
    assert rs["time"]["passes"] == 8
    assert rc["time"]["passes"] == 10
    assert 18 < rc["time"]["t_cut"] * 60 < 23  # ≈20s
    assert abs(rc["time"]["cut"] - 95.238) < 0.3
    assert [s["name"] for s in slot_c["process_sequence"]] == ["粗铣", "粗铣", "倒角"]

    m8s = client.post("/api/v1/quotes", json={**_m8(), "slider": "标准"}).get_json()
    m8c = client.post("/api/v1/quotes", json={**_m8(), "slider": "保守"}).get_json()
    fs = next(s for s in m8s["process_sequence"] if s["process"] == "rough_face")
    fc = next(s for s in m8c["process_sequence"] if s["process"] == "rough_face")
    tap_c = next(s for s in m8c["process_sequence"] if s["process"] == "tap")
    assert fc["time"]["n_act"] < fs["time"]["n_act"]
    assert fc["time"]["t_cut"] > fs["time"]["t_cut"]
    assert tap_c["time"]["n_act"] == 1000
    assert abs(tap_c["time"]["t_cut"] - 0.0096) < 0.001
    assert [s["name"] for s in m8c["process_sequence"]] == ["粗铣", "钻孔", "攻牙", "倒角"]
    assert m8c["equipment"]["model"] == "VMC850E"
    assert m8c["equipment"]["hourly_rate"] == 120
    assert "低于下限" in (m8c["risk"]["tags"] or [])
