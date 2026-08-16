"""GLB export and part mesh endpoint. Does not change hole-v3 fields."""
from io import BytesIO

from cncflow_core.common.db import get_conn
from cncflow_core.geometry.mesh import triangles_to_glb
from cncflow_core.ingestion.jobs import finish_job
from cncflow_core.ingestion.step_parser import _hole_feature


MINIMAL_STEP = (
    b"ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('AUTOMOTIVE_DESIGN'));\n"
    b"ENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;"
)


def test_triangles_to_glb_magic():
    data = triangles_to_glb([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [0, 1, 2])
    assert data[:4] == b"glTF"
    assert data[4:8] == b"\x02\x00\x00\x00"
    assert len(data) >= 12


def test_hole_feature_pose_does_not_change_v3_fields():
    class BBox:
        xlen, ylen, zlen = 80.0, 60.0, 12.0

    hole = {
        "diameter_mm": 8.0, "axis_t": (0.0, 0.0, 1.0), "origin": (0.0, 0.0, 0.0),
        "cyl_min": 0.0, "cyl_max": 12.0, "solid_min": 0.0, "solid_max": 12.0,
        "location": {"x": 0.0, "y": 0.0, "z": 0.0}, "helix": False, "hole_type": "through",
    }
    feat = _hole_feature([hole], BBox(), [], 0, cavities=[hole])
    assert feat["diameter_mm"] == 8.0
    assert feat["depth_mm"] == 12.0
    assert feat["hole_type"] == "through"
    assert feat["position_type"] == "垂直"
    assert feat["cut_depth_mm"] == 14.4
    assert feat["pose"]["diameter_mm"] == 8.0
    assert feat["pose"]["length_mm"] == 12.0
    assert feat["pose"]["axis"]["z"] == 1.0


def test_part_mesh_empty_state(client, seeded_db_path):
    inq = client.post("/api/v1/inquiries", json={"customer": "mesh"}).get_json()
    pid = client.post(
        f"/api/v1/inquiries/{inq['id']}/parts", json={"name": "块"},
    ).get_json()["id"]
    part = client.get(f"/api/v1/parts/{pid}").get_json()
    assert part["mesh"]["available"] is False
    assert part["mesh"]["url"] is None
    empty = client.get(f"/api/v1/parts/{pid}/mesh")
    assert empty.status_code == 404


def test_part_mesh_serves_glb(client, seeded_db_path, tmp_path):
    inq = client.post("/api/v1/inquiries", json={"customer": "mesh"}).get_json()
    pid = client.post(
        f"/api/v1/inquiries/{inq['id']}/parts", json={"name": "块"},
    ).get_json()["id"]
    data = {"step_file": (BytesIO(MINIMAL_STEP), "part.step"), "part_id": pid}
    job_id = client.post(
        "/api/v1/parse-jobs", data=data, content_type="multipart/form-data",
    ).get_json()["job_id"]
    glb = triangles_to_glb([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [0, 1, 2])
    mesh_path = tmp_path / f"{job_id}.glb"
    mesh_path.write_bytes(glb)
    conn = get_conn(seeded_db_path)
    finish_job(conn, job_id, {
        "geometry": {"volume_cm3": 1, "bounding_box_mm": {"x": 10, "y": 10, "z": 10}},
        "features": [{
            "type": "hole", "feature_id": "hole-0", "subtype": "recognized_hole",
            "selected": True, "diameter_mm": 8, "depth_mm": 12,
            "hole_type": "through", "position_type": "垂直", "cut_depth_mm": 14.4,
        }],
        "mesh": {"key": f"meshes/{job_id}.glb", "path": str(mesh_path), "bytes": len(glb), "format": "glb"},
        "warnings": [],
    })
    conn.close()
    part = client.get(f"/api/v1/parts/{pid}").get_json()
    assert part["mesh"]["available"] is True
    assert part["mesh"]["url"] == f"/api/v1/parts/{pid}/mesh"
    hole = [f for f in part["parsed_features"] if f["feature_id"] == "hole-0"][0]
    assert hole["diameter_mm"] == 8
    assert hole["depth_mm"] == 12
    assert hole["hole_type"] == "through"
    resp = client.get(f"/api/v1/parts/{pid}/mesh")
    assert resp.status_code == 200
    assert resp.data[:4] == b"glTF"
    assert resp.mimetype == "model/gltf-binary"
