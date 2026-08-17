"""槽/面/螺纹工时公式：cut / n / t 秒级，禁止难度桶。"""


def test_o8_face_cut_and_hole_unchanged(client):
    body = client.post("/api/v1/quotes", json={
        "material": "铝合金",
        "stock_type": "板材",
        "length": 80, "width": 60, "height": 12,
        "features": [
            {"type": "hole", "feature_id": "hole-0", "diameter_mm": 8, "depth_mm": 12, "hole_type": "through"},
            {"type": "face", "feature_id": "face-1", "length": 80, "width": 60},
        ],
    }).get_json()
    names = [s["name"] for s in body["process_sequence"]]
    assert names == ["粗铣", "钻孔", "倒角"], names
    face = next(s for s in body["process_sequence"] if s["process"] == "rough_face")
    assert face["sku"] == "TK-028"
    assert abs(face["time"]["cut"] - 85.714) < 0.2
    assert 0.10 < face["time"]["t_cut"] < 0.20  # ~9s
    assert face["minutes"] < 2
    drill = next(s for s in body["process_sequence"] if s["process"] == "drill")
    assert abs(drill["time"]["cut"] - 14.4) < 0.05
    assert drill["time"]["t_cut"] < 0.02
    eq = body["equipment"]
    assert eq["model"] == "VMC850E" and eq["hourly_rate"] == 120


def test_open_slot_rough_cut_passes(client):
    body = client.post("/api/v1/quotes", json={
        "material": "铝合金",
        "stock_type": "板材",
        "length": 80, "width": 60, "height": 12,
        "features": [
            {"type": "slot", "feature_id": "slot-0", "length": 40, "width": 10, "depth": 8, "corner_radius": 3, "pocket_type": "开放"},
            {"type": "face", "feature_id": "face-0", "length": 80, "width": 60},
        ],
    }).get_json()
    assert [s["name"] for s in body["process_sequence"]] == ["粗铣", "粗铣", "倒角"]
    slot = next(s for s in body["process_sequence"] if s["process"] == "rough_pocket")
    assert slot["sku"] == "TK-022"
    assert abs(slot["time"]["cut"] - 95.238) < 0.3
    assert slot["time"]["passes"] == 8
    assert 0.15 < slot["time"]["t_cut"] < 0.35  # ~15s
    assert slot["minutes"] < 2


def test_m8_tap_seconds(client):
    body = client.post("/api/v1/quotes", json={
        "material": "铝合金",
        "stock_type": "板材",
        "length": 40, "width": 40, "height": 12,
        "features": [
            {"type": "face", "feature_id": "face-2", "length": 40, "width": 40},
            {"type": "thread", "feature_id": "thread-0", "nominal_d": 8, "pitch": 1.25, "thread_length": 12},
        ],
    }).get_json()
    assert [s["name"] for s in body["process_sequence"]] == ["粗铣", "钻孔", "攻牙", "倒角"]
    tap = next(s for s in body["process_sequence"] if s["process"] == "tap")
    assert tap["time"]["n_act"] <= 1000
    assert abs(tap["time"]["t_cut"] - 12 / (tap["time"]["n_act"] * 1.25)) < 1e-3
    assert 0.4 < tap["time"]["t_cut"] * 60 < 1.0  # ~0.6s
    assert tap["minutes"] < 2
    assert body["equipment"]["model"] == "VMC850E"
