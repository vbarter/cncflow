"""PM 验收链：健康检查 → 新建询价 → 上传 → 解析结果 → 报价 → 改参 → 确认。"""
from io import BytesIO

from cncflow_core.common.db import get_conn
from cncflow_core.ingestion.jobs import finish_job


MINIMAL_STEP = (
    b"ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('AUTOMOTIVE_DESIGN'));\n"
    b"ENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;"
)


def test_health_and_capabilities(client):
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    body = health.get_json()
    assert body["status"] in {"ok", "degraded"}
    assert "hole" in body["features"]
    caps = client.get("/api/v1/parse-capabilities").get_json()
    assert "step" in caps["formats"]
    factory = client.get("/api/v1/factory-config")
    assert factory.status_code == 200
    cfg = factory.get_json()
    assert cfg.get("machines") or cfg.get("settings") is not None


def _d8_through_result():
    return {
        "geometry": {"volume_cm3": 55.0, "bounding_box_mm": {"x": 80, "y": 60, "z": 12}},
        "features": [
            {
                "type": "hole", "feature_id": "hole-0", "subtype": "recognized_hole",
                "selected": True, "diameter_mm": 8, "depth_mm": 12,
                "hole_type": "through", "position_type": "垂直", "surface": "top",
                "bottom_shape": "cone", "cut_depth_mm": 14.4, "h_over_d": 1.5,
                "dimensions": {"diameter_mm": 8, "depth_mm": 12},
            },
            {
                "type": "outer_cylinder", "feature_id": "od-1", "selected": False,
                "diameter_mm": 80, "depth_mm": 12,
                "dimensions": {"diameter_mm": 80, "depth_mm": 12},
            },
        ],
        "drawing": None, "warnings": [],
    }


def test_pm_new_quote_through_hole_contract(client, seeded_db_path):
    inq = client.post("/api/v1/inquiries", json={"customer": "验收", "project": "Ø8通孔板"}).get_json()
    assert inq["title"].startswith("RFQ-")
    iid = inq["id"]
    part = client.post(
        f"/api/v1/inquiries/{iid}/parts",
        json={"name": "Ø8通孔板", "material": "铝合金"},
    ).get_json()
    pid = part["id"]
    data = {"step_file": (BytesIO(MINIMAL_STEP), "plate_hole_d8.step"), "part_id": pid}
    up = client.post("/api/v1/parse-jobs", data=data, content_type="multipart/form-data")
    assert up.status_code == 202, up.get_json()
    job_id = up.get_json()["job_id"]
    assert up.get_json()["part_id"] == pid
    status = client.get(f"/api/v1/parse-jobs/{job_id}")
    assert status.status_code == 200
    assert status.get_json()["status"] in {"queued", "running", "needs_review", "failed"}

    conn = get_conn(seeded_db_path)
    finish_job(conn, job_id, _d8_through_result())
    conn.close()
    job = client.get(f"/api/v1/parse-jobs/{job_id}").get_json()
    assert job["status"] == "needs_review"
    feats = (job.get("result") or {}).get("features") or []
    hole = next(f for f in feats if f.get("feature_id") == "hole-0")
    assert hole["hole_type"] == "through"
    assert hole["position_type"] == "垂直"
    assert hole["diameter_mm"] == 8
    assert hole["depth_mm"] == 12

    quoted = client.post(f"/api/v1/inquiries/{iid}/quote", json={})
    assert quoted.status_code == 200, quoted.get_json()
    part = quoted.get_json()["parts"][0]
    assert part["status"] == "quoted"
    assert part["quote"]["quote"]["amount"] > 0
    review = (part["quote"] or {}).get("review_features") or []
    by_id = {f.get("feature_id"): f for f in review}
    assert by_id["hole-0"]["selected"] is True
    assert by_id["hole-0"]["hole_type"] == "through"
    assert by_id["hole-0"]["position_type"] == "垂直"
    assert by_id["od-1"]["selected"] is False

    plans = (part["quote"] or {}).get("features") or []
    hole_plans = [p for p in plans if p.get("type") == "hole"]
    assert len(hole_plans) == 1
    hole_out = (hole_plans[0].get("plan") or {}).get("hole") or {}
    assert hole_out.get("hole_type") == "through"
    assert hole_out.get("h_over_d") == 1.5
    assert hole_out.get("cut_depth_mm") == 14.4
    chain = (hole_plans[0].get("plan") or {}).get("process_chain") or []
    procs = [s.get("process") for s in chain]
    assert "drill" in procs
    assert chain[procs.index("drill")].get("cycle") == "G81"

    seq = (part["quote"] or {}).get("process_sequence") or []
    assert seq
    assert not any("od-1" in str(s) for s in seq)

    patched = client.patch(f"/api/v1/parts/{pid}", json={
        "material": "SUS304", "tolerance_it": 7, "roughness_ra": 1.6,
        "selected_feature_ids": ["hole-0"],
    })
    assert patched.status_code == 200, patched.get_json()
    part = patched.get_json()
    assert part["status"] == "quoted"
    assert int(part["tolerance_it"]) == 7

    confirmed = client.post(f"/api/v1/parts/{pid}/confirm")
    assert confirmed.status_code == 200
    assert confirmed.get_json()["status"] == "confirmed"
    locked = client.patch(f"/api/v1/parts/{pid}", json={"slider": "激进"})
    assert locked.status_code == 409


def test_geometry_parse_api_contract(client):
    data = {"step_file": (BytesIO(MINIMAL_STEP), "plate_hole_d8.step")}
    resp = client.post("/api/v1/geometry/parse", data=data, content_type="multipart/form-data")
    assert resp.status_code != 500, resp.get_data(as_text=True)
    body = resp.get_json()
    plugins = body.get("plugins") or []
    names = [item["name"] if isinstance(item, dict) else item for item in plugins]
    assert names == ["hole", "slot", "face"]
    by_name = {item["name"]: item for item in plugins if isinstance(item, dict)}
    assert by_name["hole"]["version"] == "hole-v3"
    assert by_name["slot"]["accepted"] is False
    assert by_name["face"]["accepted"] is False
    if "feature_count" in by_name["slot"]:
        assert by_name["slot"]["feature_count"] == 0
        assert by_name["face"]["feature_count"] == 0
    assert body.get("feature_schema") == "hole-v3"

