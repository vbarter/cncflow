"""材料中心、标准规格、案例检索与机床校核测试。"""
from app import create_app
from cncflow_core.common.case_retrieval import insert_process_case, retrieve_process_cases
from cncflow_core.common.db import get_conn, init_schema
from cncflow_core.common.materials import resolve_material, search_knowledge, seed_material_catalog
from cncflow_core.features.hole.tool_attrs import derive_requirement
from data.seed_tools import seed


def test_material_alias_resolves_to_canonical_profile(seeded_conn):
    seed_material_catalog(seeded_conn)
    profile = resolve_material(seeded_conn, "AL6061")
    assert profile.material_code == "AL-6061-T6"
    assert profile.family == "铝合金"
    assert profile.verification_status == "community_unverified"
    assert profile.planning_enabled


def test_material_catalog_endpoint(client):
    body = client.get("/api/v1/materials?q=304").get_json()
    assert body["count"] >= 1
    assert any(item["material_code"] == "SUS-304" for item in body["items"])


def test_local_knowledge_search(seeded_conn):
    seed_material_catalog(seeded_conn)
    rows = search_knowledge(seeded_conn, "高压内冷", material_code="TI-6AL4V")
    assert rows and rows[0]["authority"] == "community_unverified"


def test_grade_material_uses_verified_family_rules(client):
    resp = client.post("/api/v1/process-plan", json={
        "feature": {"type": "hole", "diameter_mm": 10, "depth_mm": 20},
        "material": "304不锈钢", "tolerance_it": 11,
    })
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["material_profile"]["material_code"] == "SUS-304"
    drill = next(step for step in body["tool_chain"] if step["process"] == "drill")
    assert drill["params"]["stable"]["vc_m_min"] == 70
    assert body["evidence"][0]["authority"] == "community_unverified"


def test_known_but_unsupported_material_does_not_fallback(client):
    resp = client.post("/api/v1/process-plan", json={
        "feature": {"type": "hole", "diameter_mm": 10, "depth_mm": 20},
        "material": "POM", "tolerance_it": 11,
    })
    assert resp.status_code == 400
    assert "planning_status=unsupported" in resp.get_json()["error"]


def test_rough_tool_requirement_uses_allowance_intersection():
    req = derive_requirement("drill", 10, 2, "铝合金", 7, True)
    assert req.diameter_min_mm == 9.6
    assert req.diameter_max_mm == 9.7
    assert req.preferred_attrs.nominal_diameter_mm == 9.7


def test_catalog_only_when_no_inventory(tmp_path):
    db_path = tmp_path / "catalog.db"
    app = create_app(str(db_path))
    app.testing = True
    resp = app.test_client().post("/api/v1/process-plan", json={
        "feature": {"type": "hole", "diameter_mm": 10, "depth_mm": 20},
        "material": "45#钢", "tolerance_it": 11,
    })
    drill = next(step for step in resp.get_json()["tool_chain"] if step["process"] == "drill")
    assert drill["match_status"] == "missing"  # v1兼容字段
    assert drill["match_tier"] == "catalog_only"
    assert drill["candidates"][0]["candidate_type"] == "catalog_spec"
    assert drill["sku_candidates"] == []


def test_incompatible_catalog_coating_is_not_presented_as_candidate(tmp_path):
    app = create_app(str(tmp_path / "catalog-al.db"))
    app.testing = True
    resp = app.test_client().post("/api/v1/process-plan", json={
        "feature": {"type": "hole", "diameter_mm": 10, "depth_mm": 20},
        "material": "铝合金", "tolerance_it": 11,
    })
    drill = next(step for step in resp.get_json()["tool_chain"] if step["process"] == "drill")
    # 文档3麻花钻只有TiN，与文档2的铝材无涂层/DLC约束冲突。
    assert drill["match_tier"] == "custom_required"


def test_verified_case_retrieval_and_draft_isolation(tmp_path):
    conn = get_conn(tmp_path / "cases.db")
    init_schema(conn)
    seed_material_catalog(conn)
    base = {
        "material_code": "AL-6061-T6", "material_family": "铝合金",
        "diameter_mm": 10, "depth_mm": 20, "tolerance_it": 7,
        "actual_chain": ["drill", "ream"], "outcome": {"result": "pass"},
    }
    insert_process_case(conn, {**base, "case_id": "VERIFIED-1", "status": "verified", "reviewed_by": "qa"})
    insert_process_case(conn, {**base, "case_id": "DRAFT-1", "status": "draft"})
    rows = retrieve_process_cases(
        conn, material_code="AL-6061-T6", material_family="铝合金", diameter_mm=10,
        depth_mm=20, hole_type="through", tolerance_it=7,
    )
    assert [row["case_id"] for row in rows] == ["VERIFIED-1"]
    assert rows[0]["similarity"] > 0.9
    conn.close()


def test_strategy_and_machine_adjustment(client):
    resp = client.post("/api/v1/process-plan", json={
        "feature": {"type": "hole", "diameter_mm": 10, "depth_mm": 20},
        "material": "铝合金", "tolerance_it": 11, "strategy": "stable",
        "machine_profile": {"max_spindle_rpm": 3000, "max_feed_mm_min": 200,
                            "through_spindle_coolant": True, "coolant_pressure_bar": 40},
    })
    drill = next(step for step in resp.get_json()["tool_chain"] if step["process"] == "drill")
    assert list(drill["params"]) == ["stable"]
    assert drill["params"]["stable"]["feed_rate_mm_min"] == 382.0
    assert drill["machine_adjusted"]["strategies"]["stable"]["spindle_rpm"] == 3000
    assert drill["machine_adjusted"]["strategies"]["stable"]["feed_rate_mm_min"] == 200.0
