"""倒角合并 + 螺纹吃孔。识别/三库/孔工时公式不改。"""
from cncflow_core.quoting import dedup


def test_merge_o8_three_chamfers_to_one():
    seq = [
        {"order": 1, "feature_id": "face-1", "process": "rough_face", "name": "粗铣"},
        {"order": 2, "feature_id": "hole-0", "process": "drill", "name": "钻孔"},
        {"order": 3, "feature_id": "face-1", "process": "chamfer", "name": "倒角", "sku": "TK-036", "minutes": 0.5},
        {"order": 4, "feature_id": "hole-0", "process": "chamfer", "name": "入口倒角", "sku": "TK-036", "minutes": 0.1},
        {"order": 5, "feature_id": "hole-0", "process": "chamfer", "name": "出口倒角", "sku": "TK-036", "minutes": 0.1},
    ]
    got = dedup.merge_chamfers(seq)
    assert [s["name"] for s in got] == ["粗铣", "钻孔", "倒角"]
    assert got[-1]["sku"] == "TK-036"
    assert abs(got[-1]["minutes"] - 0.7) < 1e-6
    assert got[-1]["merged_from"] == ["face-1", "hole-0", "hole-0"]


def test_merge_slot_face_chamfers():
    seq = [
        {"order": 1, "feature_id": "slot-0", "process": "rough_pocket", "name": "粗铣"},
        {"order": 2, "feature_id": "face-0", "process": "rough_face", "name": "粗铣"},
        {"order": 3, "feature_id": "face-0", "process": "chamfer", "name": "倒角", "sku": "TK-036"},
        {"order": 4, "feature_id": "slot-0", "process": "chamfer", "name": "倒角", "sku": "TK-036"},
    ]
    got = dedup.merge_chamfers(seq)
    assert [s["process"] for s in got] == ["rough_pocket", "rough_face", "chamfer"]


def test_single_chamfer_untouched():
    seq = [
        {"order": 1, "process": "rough_face", "name": "粗铣"},
        {"order": 2, "process": "chamfer", "name": "倒角", "sku": "TK-036"},
    ]
    assert dedup.merge_chamfers(seq) is seq


def test_thread_eats_same_location_hole():
    feats = [
        {"type": "face", "feature_id": "face-2", "length": 40, "width": 40},
        {"type": "thread", "feature_id": "thread-0", "nominal_d": 8, "pitch": 1.25,
         "location": {"x": 0, "y": 0, "z": 6}},
        {"type": "hole", "feature_id": "hole-0", "diameter_mm": 8, "depth_mm": 12,
         "location": {"x": 0.1, "y": -0.1, "z": 6}},
    ]
    got = dedup.absorb_holes(feats)
    assert [f["type"] for f in got] == ["face", "thread"]


def test_thread_eats_tap_drill_diameter():
    feats = [
        {"type": "thread", "nominal_d": 8, "pitch": 1.25},
        {"type": "hole", "diameter_mm": 6.75, "depth_mm": 12},
    ]
    got = dedup.absorb_holes(feats)
    assert [f["type"] for f in got] == ["thread"]


def test_far_hole_not_eaten():
    feats = [
        {"type": "thread", "nominal_d": 8, "pitch": 1.25, "location": {"x": 0, "y": 0, "z": 6}},
        {"type": "hole", "diameter_mm": 8, "depth_mm": 12, "location": {"x": 30, "y": 0, "z": 6}},
    ]
    got = dedup.absorb_holes(feats)
    assert [f["type"] for f in got] == ["thread", "hole"]


def test_quote_o8_three_steps(client):
    body = client.post("/api/v1/quotes", json={
        "material": "铝合金",
        "stock_type": "板材",
        "length": 80, "width": 60, "height": 12,
        "features": [
            {"type": "hole", "feature_id": "hole-0", "diameter_mm": 8, "depth_mm": 12, "hole_type": "through"},
            {"type": "face", "feature_id": "face-1", "length": 80, "width": 60},
        ],
    }).get_json()
    names = [s.get("name") for s in body["process_sequence"]]
    assert names == ["粗铣", "钻孔", "倒角"], names
    drill = next(s for s in body["process_sequence"] if s["process"] == "drill")
    assert abs(drill["time"]["cut"] - 14.4) < 0.05


def test_quote_m8_thread_eats_hole(client):
    body = client.post("/api/v1/quotes", json={
        "material": "铝合金",
        "stock_type": "板材",
        "length": 40, "width": 40, "height": 12,
        "features": [
            {"type": "face", "feature_id": "face-2", "length": 40, "width": 40},
            {"type": "thread", "feature_id": "thread-0", "nominal_d": 8, "pitch": 1.25, "thread_length": 12,
             "location": {"x": 0, "y": 0, "z": 6}},
            {"type": "hole", "feature_id": "hole-0", "diameter_mm": 8, "depth_mm": 12, "hole_type": "through",
             "location": {"x": 0, "y": 0, "z": 6}},
        ],
    }).get_json()
    types = [f["type"] for f in body["features"]]
    assert "hole" not in types
    names = [s.get("name") for s in body["process_sequence"]]
    assert names == ["粗铣", "钻孔", "攻牙", "倒角"], names
    assert sum(1 for s in body["process_sequence"] if s["process"] == "drill") == 1
    skus = [s.get("sku") for s in body["process_sequence"]]
    assert "TK-033" in skus


def test_quote_open_slot_plus_face_three_steps(client):
    body = client.post("/api/v1/quotes", json={
        "material": "铝合金",
        "stock_type": "板材",
        "length": 80, "width": 60, "height": 12,
        "features": [
            {"type": "slot", "feature_id": "slot-0", "length": 40, "width": 10, "depth": 8, "corner_radius": 3, "pocket_type": "开放"},
            {"type": "face", "feature_id": "face-0", "length": 80, "width": 60},
        ],
    }).get_json()
    names = [s.get("name") for s in body["process_sequence"]]
    assert names == ["粗铣", "粗铣", "倒角"], names
    assert [s["feature_id"] for s in body["process_sequence"] if s["process"] != "chamfer"] == ["slot-0", "face-0"]
