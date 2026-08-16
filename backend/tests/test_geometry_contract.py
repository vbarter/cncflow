"""几何特征服务契约：STEP 进、features 出；询价走 parse-jobs 接线。"""

HOLE_FIELDS = ("diameter_mm", "depth_mm", "hole_type", "position_type", "cut_depth_mm")


def test_geometry_contract_lists_plugins(client):
    r = client.get("/api/v1/geometry/contract")
    assert r.status_code == 200
    body = r.get_json()
    assert body["service"] == "geometry"
    assert body["endpoint"] == "POST /api/v1/geometry/parse"
    assert body["output"]["feature_schema"] == "hole-v3"
    ids = [p["id"] for p in body["plugins"]]
    assert ids == ["hole", "slot", "face", "thread"]
    assert body["plugins"][0]["status"] == "active"
    assert body["plugins"][1]["status"] == "active"
    assert body["plugins"][2]["status"] == "active"


def test_geometry_contract_lists_hole_fields(client):
    body = client.get("/api/v1/geometry/contract").get_json()
    output = body["output"]
    fields = output.get("feature_fields")
    if not fields:
        features = output.get("features")
        if isinstance(features, dict):
            fields = (features.get("hole") or {}).get("fields")
    assert fields, output
    for name in HOLE_FIELDS:
        assert name in fields
    hole = output["features"]["hole"] if isinstance(output.get("features"), dict) else None
    if hole:
        assert hole["status"] == "active"
        assert hole["version"] == "hole-v3"
        for name in HOLE_FIELDS:
            assert name in hole["fields"]
        assert output["features"]["slot"]["status"] == "active"
        assert output["features"]["slot"].get("accepted") is True
        assert output["features"]["face"]["status"] == "active"
        assert output["features"]["face"].get("accepted") is True
        for name in ("length", "width", "face_position"):
            assert name in output["features"]["face"]["fields"]
        assert output["features"]["thread"]["status"] == "active"
        for name in ("diameter_mm", "pitch", "thread_length"):
            assert name in output["features"]["thread"]["fields"]
        for name in ("pocket_type", "length", "width", "depth", "corner_radius"):
            assert name in output["features"]["slot"]["fields"]


def test_geometry_parse_requires_step(client):
    r = client.post("/api/v1/geometry/parse")
    assert r.status_code == 400
    assert "step_file" in r.get_json()["error"]


def test_geometry_parse_rejects_non_step(client):
    r = client.post(
        "/api/v1/geometry/parse",
        data={"step_file": (b"x", "part.pdf")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 400
