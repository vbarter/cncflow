"""Hole recognition fields vs hole pipeline (D/H, through/blind, position_type)."""
from io import BytesIO

import pytest

from cncflow_core.common.db import get_conn
from cncflow_core.features.hole.models import HoleSpec
from cncflow_core.features.hole.process_chain import generate_chain
from cncflow_core.ingestion.jobs import finish_job
from cncflow_core.ingestion.step_parser import (
    classify_by_containment, classify_cylinder_side, classify_position,
    classify_through_blind, classify_through_by_ends, coaxial_cavity_span,
    is_quote_hole, likely_outer_od, likely_plate_hole, override_false_outer,
    recover_through_depth, through_cut_depth, through_into_cavity,
    through_wall_depth, _hole_feature,
)
from cncflow_core.inquiries.api import _hole_for_pipeline, _review_and_quote_features


MINIMAL_STEP = (
    b"ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('AUTOMOTIVE_DESIGN'));\n"
    b"ENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;"
)


def test_inner_vs_outer_by_normal():
    assert classify_cylinder_side((-1, 0, 0), (1, 0, 0)) == "inner"
    assert classify_cylinder_side((1, 0, 0), (1, 0, 0)) == "outer"
    assert classify_cylinder_side((0, 1, 0), (1, 0, 0)) is None


def test_position_type_from_axis():
    plate = (80, 60, 12)
    assert classify_position((0, 0, 1), plate) == "垂直"
    assert classify_position((1, 0, 0), plate) == "侧向"
    assert classify_position((0.7, 0.7, 0.1), plate) == "倾斜"
    assert classify_position((0, 0, 1), plate, entry_curved=True) == "曲面"
    assert classify_position((0, 0, 1), plate, entry_recessed=True) == "深腔"


def test_through_vs_blind_span():
    assert classify_through_blind(0, 12, 0, 12) == "through"
    assert classify_through_blind(0, 8, 0, 20) == "blind"
    assert classify_through_blind(0.2, 11.8, 0, 12) == "through"


def test_through_cut_depth_adds_point_three_d():
    assert through_cut_depth(10, 20, "through") == 23.0
    assert through_cut_depth(10, 20, "blind") == 20.0
    hole = HoleSpec(diameter_mm=10, depth_mm=20, hole_type="through")
    assert hole.h_over_d == 2.0
    assert hole.cut_depth_mm == 23.0


def test_pipeline_uses_hd_not_cut_depth():
    hole = HoleSpec(diameter_mm=10, depth_mm=80, hole_type="through")
    assert hole.h_over_d == 8.0
    assert hole.cut_depth_mm == 83.0
    chain = generate_chain(hole, "不锈钢", 11)
    drill = [s for s in chain if s["process"] == "drill"][0]
    assert drill["cycle"] == "G83"


def test_map_recognized_hole_to_pipeline_fields():
    feat = {
        "type": "hole", "feature_id": "hole-0", "selected": True,
        "diameter_mm": 8, "depth_mm": 12, "hole_type": "blind",
        "position_type": "侧向", "bottom_shape": "cone",
    }
    mapped = _hole_for_pipeline(feat, "hole-0")
    assert mapped["hole_type"] == "blind"
    assert mapped["surface"] == "side"
    assert mapped["cut_depth_mm"] == 12
    review, features = _review_and_quote_features([feat], None, 80, 60)
    holes = [f for f in features if f["type"] == "hole"]
    assert holes[0]["hole_type"] == "blind"
    assert holes[0]["surface"] == "side"


def test_outer_cylinder_not_quoted():
    feats = [
        {"type": "outer_cylinder", "feature_id": "od-1", "selected": False,
         "diameter_mm": 40, "depth_mm": 12},
        {"type": "hole", "feature_id": "hole-0", "selected": True,
         "diameter_mm": 6, "depth_mm": 12, "hole_type": "through", "position_type": "垂直"},
    ]
    _, features = _review_and_quote_features(feats, None, 80, 60)
    holes = [f for f in features if f["type"] == "hole"]
    assert len(holes) == 1
    assert holes[0]["cut_depth_mm"] == pytest.approx(12 + 0.3 * 6)


def test_quote_recognized_through_hole_runs_chain(client, seeded_db_path):
    inq = client.post("/api/v1/inquiries", json={"customer": "华科"}).get_json()
    iid = inq["id"]
    pid = client.post(
        f"/api/v1/inquiries/{iid}/parts",
        json={"name": "底板", "material": "铝合金"},
    ).get_json()["id"]
    data = {"step_file": (BytesIO(MINIMAL_STEP), "part.step"), "part_id": pid}
    job_id = client.post(
        "/api/v1/parse-jobs", data=data, content_type="multipart/form-data",
    ).get_json()["job_id"]
    conn = get_conn(seeded_db_path)
    finish_job(conn, job_id, {
        "geometry": {"volume_cm3": 12.5, "bounding_box_mm": {"x": 80, "y": 40, "z": 12}},
        "features": [{
            "type": "hole", "feature_id": "hole-0", "subtype": "recognized_hole",
            "selected": True, "diameter_mm": 10, "depth_mm": 80,
            "hole_type": "through", "position_type": "垂直", "surface": "top",
            "bottom_shape": "cone", "cut_depth_mm": 83, "h_over_d": 8,
            "dimensions": {"diameter_mm": 10, "depth_mm": 80},
        }],
        "drawing": None, "warnings": [],
    })
    conn.close()
    q = client.post(f"/api/v1/inquiries/{iid}/quote", json={})
    assert q.status_code == 200, q.get_json()
    part = q.get_json()["parts"][0]
    assert part["status"] == "quoted"
    quote = part.get("quote") or {}
    plans = quote.get("features") or quote.get("feature_plans") or quote.get("plans") or []
    hole_plans = [p for p in plans if p.get("type") == "hole" or (p.get("plan") or {}).get("hole")]
    assert hole_plans, quote
    hole = (hole_plans[0].get("plan") or {}).get("hole") or {}
    assert hole.get("hole_type") == "through"
    assert hole.get("h_over_d") == pytest.approx(8)
    assert hole.get("cut_depth_mm") == pytest.approx(83)
    chain = (hole_plans[0].get("plan") or {}).get("process_chain") or []
    procs = [s.get("process") for s in chain]
    assert "drill" in procs or "gun_drill" in procs


def test_cadquery_plate_with_through_hole():
    cadquery = pytest.importorskip("cadquery")
    from cncflow_core.ingestion.step_parser import parse_step
    import os
    import tempfile
    part = cadquery.Workplane("XY").box(80, 60, 12).faces(">Z").workplane().hole(8)
    fd, path = tempfile.mkstemp(suffix=".step")
    os.close(fd)
    try:
        cadquery.exporters.export(part, path)
        result = parse_step(path)
    finally:
        os.unlink(path)
    holes = [f for f in result["features"] if f.get("subtype") == "recognized_hole"]
    assert holes, result["features"]
    hole = holes[0]
    assert hole["diameter_mm"] == pytest.approx(8, abs=0.2)
    assert hole["depth_mm"] == pytest.approx(12, abs=0.6)
    assert hole["hole_type"] == "through"
    assert hole["position_type"] in {"垂直", "侧向"}
    assert hole["cut_depth_mm"] == pytest.approx(
        hole["depth_mm"] + 0.3 * hole["diameter_mm"], abs=0.3,
    )
    ods = [f for f in result["features"] if f.get("type") == "outer_cylinder"]
    assert not any(f.get("selected") for f in ods)



def test_containment_inner_vs_outer():
    assert classify_by_containment(False, True) == "inner"
    assert classify_by_containment(True, False) == "outer"
    assert classify_by_containment(True, True) is None
    assert classify_by_containment(None, True) is None


def test_plate_through_cylinder_is_hole():
    assert likely_plate_hole(8, 0, 12, 0, 12, (80, 60, 12)) is True
    assert likely_plate_hole(80, 0, 12, 0, 12, (80, 60, 12)) is False
    assert likely_plate_hole(8, 0, 6, 0, 12, (80, 60, 12)) is False


def test_short_span_plate_still_hole():
    assert likely_plate_hole(8, 0, 10, 0, 12, (80, 60, 12)) is True
    assert likely_plate_hole(8, 0, 5, 0, 12, (80, 60, 12)) is False



def test_point_accepts_tuple_and_dict():
    from cncflow_core.ingestion.step_parser import _point, _xyz
    assert _xyz((1.23456, 2, 3)) == (1.23456, 2.0, 3.0)
    assert _point((1.23456, 2, 3)) == {"x": 1.2346, "y": 2.0, "z": 3.0}
    assert _point({"x": 1, "y": 2, "z": 3}) == {"x": 1.0, "y": 2.0, "z": 3.0}

    class Vec:
        def __init__(self):
            self.x, self.y, self.z = 4.0, 5.0, 6.0

    assert _point(Vec()) == {"x": 4.0, "y": 5.0, "z": 6.0}



def test_through_by_open_ends():
    assert classify_through_by_ends(False, False) == "through"
    assert classify_through_by_ends(True, False) == "blind"
    assert classify_through_by_ends(None, False) is None


def test_o8_plate_acceptance():
    assert through_cut_depth(8, 12, "through") == 14.4
    assert is_quote_hole(8, 12, "through", (80, 60, 12)) is True
    assert likely_plate_hole(8, 0, 12, 0, 12, (80, 60, 12)) is True
    assert likely_outer_od(8, (80, 60, 12), (0, 0, 1)) is False


def test_zn010_acceptance_fields():
    extents = (50, 50, 44)
    axis = (0, 0, 1)
    assert likely_outer_od(50, extents, axis) is True
    assert likely_outer_od(3.30, extents, axis) is False
    assert likely_outer_od(33.40, extents, axis) is False
    assert override_false_outer("outer", 3.30, extents, axis) == "inner"
    assert override_false_outer("outer", 50, extents, axis) == "outer"
    assert override_false_outer("inner", 33.40, extents, axis) == "inner"
    assert through_wall_depth(24.625, 44, 18) == 26
    assert through_wall_depth(24.625, 44, 44) == 24.625
    assert recover_through_depth(24.625, 26) == 26
    assert recover_through_depth(12, 12) == 12
    assert recover_through_depth(24.625, 44) == 24.625
    assert through_into_cavity(24.625, 44, 18) is True
    assert through_into_cavity(10, 44, 18) is False
    assert through_cut_depth(3.30, 26, "through") == 26.99
    assert is_quote_hole(3.30, 26, "through", extents, axis) is True
    assert is_quote_hole(50, 44, "through", extents, axis) is False
    assert is_quote_hole(33.40, 18, "blind", extents, axis) is False
    assert is_quote_hole(33.40, 18, "through", extents, axis) is False
    hole = _hole_for_pipeline({
        "type": "hole", "diameter_mm": 3.30, "depth_mm": 26,
        "hole_type": "through", "position_type": "垂直",
    }, "hole-0")
    assert hole["cut_depth_mm"] == 26.99
    assert hole["surface"] == "top"


def _cyl(diameter, cyl_min, cyl_max, solid_max=44.0):
    return {
        "diameter_mm": diameter,
        "axis_t": (0.0, 0.0, 1.0),
        "origin": (0.0, 0.0, 0.0),
        "cyl_min": cyl_min,
        "cyl_max": cyl_max,
        "solid_min": 0.0,
        "solid_max": solid_max,
        "location": {"x": 0.0, "y": 0.0, "z": 0.0},
        "helix": False,
    }


def test_coaxial_cavity_skips_od():
    extents = (50, 50, 44)
    hole = _cyl(3.3, 0.0, 24.625)
    cavity = _cyl(33.4, 26.0, 44.0)
    od = _cyl(50.0, 0.0, 44.0)
    assert coaxial_cavity_span(hole, [hole, cavity, od], 44.0, extents) == 18
    assert coaxial_cavity_span(hole, [hole, od], 44.0, extents) is None


def test_zn010_hole_feature_from_cylinders():
    class BBox:
        xlen, ylen, zlen = 50.0, 50.0, 44.0

    hole = _cyl(3.3, 0.0, 24.625)
    hole["hole_type"] = "through"
    cavity = _cyl(33.4, 26.0, 44.0)
    od = _cyl(50.0, 0.0, 44.0)
    feat = _hole_feature([hole], BBox(), [], 0, cavities=[hole, cavity, od])
    assert feat["subtype"] == "recognized_hole"
    assert feat["selected"] is True
    assert feat["diameter_mm"] == pytest.approx(3.30, abs=0.01)
    assert feat["depth_mm"] == pytest.approx(26, abs=0.05)
    assert feat["hole_type"] == "through"
    assert feat["position_type"] == "垂直"
    assert feat["cut_depth_mm"] == pytest.approx(26.99, abs=0.05)


def test_o8_hole_feature_keeps_plate_thickness():
    class BBox:
        xlen, ylen, zlen = 80.0, 60.0, 12.0

    hole = _cyl(8.0, 0.0, 12.0, solid_max=12.0)
    hole["hole_type"] = "through"
    feat = _hole_feature([hole], BBox(), [], 0, cavities=[hole])
    assert feat["diameter_mm"] == pytest.approx(8, abs=0.01)
    assert feat["depth_mm"] == pytest.approx(12, abs=0.05)
    assert feat["hole_type"] == "through"
    assert feat["position_type"] == "垂直"
    assert feat["cut_depth_mm"] == pytest.approx(14.4, abs=0.05)
