"""face / pocket / thread / surface 管道。"""


def post(client, payload):
    return client.post("/api/v1/process-plan", json=payload)


def test_face_easy_d1(client):
    resp = post(client, {
        "feature": {"type": "face", "length": 80, "width": 40, "depth": 1},
        "material": "铝合金",
        "tolerance_it": 11,
        "roughness_ra": 3.2,
    })
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["difficulty"]["level"] == "D1"
    assert body["process_chain"]


def test_pocket_deep_is_d3_not_na(client):
    resp = post(client, {
        "feature": {"type": "pocket", "length": 40, "width": 5, "depth": 30, "corner_radius": 0.2},
        "material": "不锈钢",
    })
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["difficulty"]["level"] == "D3"


def test_face_area_bands(client):
    def area_level(length, width):
        body = post(client, {
            "feature": {"type": "face", "length": length, "width": width, "depth": 1},
            "tolerance_it": 11, "roughness_ra": 3.2,
        }).get_json()
        return body["difficulty"]["level"]
    assert area_level(80, 40) == "D1"          # 3200
    assert area_level(250, 200) == "D2"        # 50000 > 4万
    assert area_level(500, 400) == "D3"        # 200000 > 16万


def test_thread_diameter_bands(client):
    def d_level(nominal_d):
        body = post(client, {
            "feature": {"type": "thread", "nominal_d": nominal_d, "pitch": 1.25, "thread_length": 8},
        }).get_json()
        return body["difficulty"]["level"]
    assert d_level(8) == "D1"
    assert d_level(20) == "D2"                 # >16
    assert d_level(0.8) == "D3"                # <3，不是 NA


def test_thread_normal(client):
    resp = post(client, {
        "feature": {"type": "thread", "nominal_d": 8, "pitch": 1.25, "thread_length": 12},
        "material": "铝合金",
    })
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["difficulty"]["level"] in {"D1", "D2"}
    assert any(step["op"] in {"tap", "thread_mill", "drill"} for step in body["process_chain"])


def test_surface_manual_risk(client):
    resp = post(client, {"feature": {"type": "surface"}, "manual_hours": 1.5})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["manual_hours"] == 1.5
    assert "需补五轴工时" in body["risk_tags"]


def test_health_lists_new_features(client):
    body = client.get("/api/v1/health").get_json()
    assert set(body["features"]) >= {"hole", "face", "pocket", "thread", "surface"}
