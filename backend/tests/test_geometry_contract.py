"""几何特征服务契约：STEP 进、features 出；询价本轮不接线。"""


def test_geometry_contract_lists_plugins(client):
    r = client.get("/api/v1/geometry/contract")
    assert r.status_code == 200
    body = r.get_json()
    assert body["service"] == "geometry"
    assert body["endpoint"] == "POST /api/v1/geometry/parse"
    assert body["output"]["feature_schema"] == "hole-v3"
    ids = [p["id"] for p in body["plugins"]]
    assert ids == ["hole", "slot", "face"]
    assert body["plugins"][0]["status"] == "active"
    assert body["plugins"][1]["status"] == "stub"
    assert body["plugins"][2]["status"] == "stub"


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
