"""API 层测试：统一入口、校验、四级拦截、SKU 匹配状态、审计日志。"""
import json

from cncflow_core.common.db import get_conn
from cncflow_core.common.models import ToolAttrs
from cncflow_core.common.sku_match import match_with_status


def post(client, payload):
    return client.post("/api/v1/process-plan", json=payload)


def make_payload(**overrides):
    payload = {
        "feature": {"type": "hole", "diameter_mm": 50.0, "depth_mm": 200.0},
        "material": "铝合金",
        "tolerance_it": 7,
    }
    payload.update(overrides)
    return payload


class TestHappyPath:
    def test_alu_d50_full_response(self, client):
        resp = post(client, make_payload())
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["machinability"]["level"] == 2          # IT7 追加精加工 → 二级
        processes = [s["process"] for s in body["tool_chain"]]
        assert processes == ["spot_drill", "u_drill", "semi_bore", "fine_bore", "chamfer"]
        u_drill = body["tool_chain"][1]
        assert u_drill["tool_attrs"]["nominal_diameter_mm"] == 49.5
        assert u_drill["match_status"] == "matched"
        assert u_drill["params"]["stable"]["vc_m_min"] == 150
        assert u_drill["params"]["aggressive"]["vc_m_min"] == 250
        assert body["match_status"] == "全匹配成功"

    def test_stainless_deep_hole(self, client):
        resp = post(client, make_payload(
            feature={"type": "hole", "diameter_mm": 10.0, "depth_mm": 80.0},
            material="不锈钢", tolerance_it=None,
        ))
        body = resp.get_json()
        assert body["machinability"]["level"] == 2
        drill = next(s for s in body["tool_chain"] if s["process"] == "drill")
        assert drill["cycle"] == "G83"
        assert drill["tool_attrs"]["structure"] == "内冷"
        assert drill["tool_attrs"]["coating"] == "TiAlN"
        assert drill["params"]["stable"]["vc_m_min"] == 70
        assert drill["params"]["stable"]["feed_per_rev_mm"] == 0.056

    def test_health(self, client):
        resp = client.get("/api/v1/health")
        body = resp.get_json()
        assert body["status"] == "degraded"  # 测试环境未启动独立解析Worker
        assert body["features"] == ["hole"]
        assert body["parser"]["queued"] >= 0
        assert body["parser"]["available"] is False


class TestValidation:
    def test_invalid_material_400(self, client):
        resp = post(client, make_payload(material="木头"))
        assert resp.status_code == 400
        assert "material" in resp.get_json()["error"]

    def test_unsupported_feature_type_400(self, client):
        resp = post(client, make_payload(feature={"type": "face", "diameter_mm": 1, "depth_mm": 1}))
        assert resp.status_code == 400
        assert "暂不支持" in resp.get_json()["error"]

    def test_negative_diameter_400(self, client):
        resp = post(client, make_payload(feature={"type": "hole", "diameter_mm": -5, "depth_mm": 10}))
        assert resp.status_code == 400

    def test_non_json_400(self, client):
        resp = client.post("/api/v1/process-plan", data="not json", content_type="text/plain")
        assert resp.status_code == 400


class TestRiskGate:
    def test_level4_returns_empty_chain(self, client):
        # H/D=25 > 20 → 四级不建议加工
        resp = post(client, make_payload(
            feature={"type": "hole", "diameter_mm": 10.0, "depth_mm": 250.0}, tolerance_it=None,
        ))
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["machinability"]["level"] == 4
        assert body["tool_chain"] == []
        assert "不建议加工" in body["match_status"]


class TestSkuMissing:
    def test_nonstandard_d14_reports_missing(self, client):
        # 种子库刻意不含 14mm 系（Ø13.7 非标钻头，文档2 §1.4.2 示例）
        resp = post(client, make_payload(
            feature={"type": "hole", "diameter_mm": 14.0, "depth_mm": 30.0},
        ))
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["match_status"].startswith("部分匹配失败")
        drill = next(s for s in body["tool_chain"] if s["process"] == "drill")
        assert drill["match_status"] == "missing"
        assert drill["sku_candidates"] == []

    def test_exact_match_five_fields(self, seeded_conn):
        attrs = ToolAttrs("钻头", 9.7, "内冷", "硬质合金", "TiAlN", "普通")
        skus, status, _ = match_with_status(seeded_conn, attrs)
        assert status == "matched" and skus

    def test_any_field_mismatch_rejects(self, seeded_conn):
        attrs = ToolAttrs("钻头", 9.7, "内冷", "硬质合金", "TiAlN", "超精密")  # 精度不符
        skus, status, detail = match_with_status(seeded_conn, attrs)
        assert status == "missing" and not skus and "库存无匹配" in detail


class TestAuditLog:
    def test_audit_written(self, client, seeded_db_path):
        post(client, make_payload())
        conn = get_conn(seeded_db_path)
        row = conn.execute(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        assert row is not None
        assert row["machinability_level"] == 2
        assert "HOLE-PREC-IT7" in json.loads(row["fired_rules"])
        assert row["rules_version"]
