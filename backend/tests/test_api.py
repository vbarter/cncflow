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
        assert processes == ["spot_drill", "u_drill", "semi_bore", "fine_bore", "chamfer", "chamfer"]
        u_drill = body["tool_chain"][1]
        assert u_drill["tool_attrs"]["nominal_diameter_mm"] == 49.5
        assert u_drill["match_status"] in {"matched", "missing"}
        assert u_drill["params"]["stable"]["vc_m_min"] == 150
        assert u_drill["params"]["aggressive"]["vc_m_min"] == 250
        assert body["match_status"] in {"全匹配成功"} or body["match_status"].startswith("部分匹配失败")

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
        assert set(body["features"]) >= {"hole", "face", "fixture"}
        assert body["parser"]["queued"] >= 0
        assert body["parser"]["available"] is False
        assert body["persist"]["r2"] is False
        assert isinstance(body["persist"]["db_exists"], bool)
        assert body["persist"]["last_backup_ok"] in (True, False, None)


class TestValidation:
    def test_invalid_material_400(self, client):
        resp = post(client, make_payload(material="木头"))
        assert resp.status_code == 400
        assert "material" in resp.get_json()["error"]

    def test_unsupported_feature_type_400(self, client):
        resp = post(client, make_payload(feature={"type": "unknown", "diameter_mm": 1, "depth_mm": 1}))
        assert resp.status_code == 400
        assert "暂不支持" in resp.get_json()["error"]

    def test_negative_diameter_400(self, client):
        resp = post(client, make_payload(feature={"type": "hole", "diameter_mm": -5, "depth_mm": 10}))
        assert resp.status_code == 400

    def test_non_json_400(self, client):
        resp = client.post("/api/v1/process-plan", data="not json", content_type="text/plain")
        assert resp.status_code == 400


class TestRiskGate:
    def test_hd_over_20_uses_special_route_instead_of_level4(self, client):
        # 冻结口径：H/D>20 是三级特种/EDM 路线，不得仅凭深径比自动 NA。
        resp = post(client, make_payload(
            feature={"type": "hole", "diameter_mm": 10.0, "depth_mm": 250.0}, tolerance_it=None,
        ))
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["machinability"]["level"] == 3
        processes = [step["process"] for step in body["tool_chain"]]
        assert "special_hole" in processes
        assert "gun_drill" not in processes


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
        attrs = ToolAttrs("钻头", 6, "标准", "硬质合金", "无涂层", "普通")
        skus, status, _ = match_with_status(seeded_conn, attrs)
        assert status == "matched" and "TK-003" in skus

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


R2_ENV_KEYS = (
    "CNCFLOW_R2_ACCOUNT_ID",
    "CNCFLOW_R2_ACCESS_KEY_ID",
    "CNCFLOW_R2_SECRET_ACCESS_KEY",
    "CNCFLOW_R2_BUCKET",
)


class TestPersistHealth:
    def test_persist_r2_false_without_env(self, client, monkeypatch):
        for key in R2_ENV_KEYS:
            monkeypatch.delenv(key, raising=False)
        monkeypatch.delenv("CNCFLOW_REQUIRE_PERSISTENT_DB", raising=False)
        body = client.get("/api/v1/health").get_json()
        assert body["persist"]["r2"] is False
        assert set(body["persist"]) == {"r2", "db_exists", "last_backup_ok"}

    def test_persist_r2_true_with_env(self, client, monkeypatch):
        monkeypatch.setenv("CNCFLOW_R2_ACCOUNT_ID", "acct")
        monkeypatch.setenv("CNCFLOW_R2_ACCESS_KEY_ID", "key")
        monkeypatch.setenv("CNCFLOW_R2_SECRET_ACCESS_KEY", "secret")
        monkeypatch.setenv("CNCFLOW_R2_BUCKET", "cncflow-files")
        body = client.get("/api/v1/health").get_json()
        assert body["persist"]["r2"] is True
        assert isinstance(body["persist"]["db_exists"], bool)
        assert body["persist"]["last_backup_ok"] in (True, False, None)

    def _with_live_parser(self, seeded_db_path):
        from cncflow_core.common.db import get_conn

        conn = get_conn(seeded_db_path)
        conn.execute(
            "INSERT OR REPLACE INTO parser_workers(worker_id,parser_version,heartbeat_at) "
            "VALUES(?,?,datetime('now'))",
            ("health-worker", "hole-v4"),
        )
        conn.commit()
        conn.close()
        try:
            yield
        finally:
            conn = get_conn(seeded_db_path)
            conn.execute("DELETE FROM parser_workers WHERE worker_id=?", ("health-worker",))
            conn.commit()
            conn.close()

    def test_degraded_when_persistent_db_required_without_r2(self, client, seeded_db_path, monkeypatch):
        for key in R2_ENV_KEYS:
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("CNCFLOW_REQUIRE_PERSISTENT_DB", "1")
        ctx = self._with_live_parser(seeded_db_path)
        next(ctx)
        try:
            body = client.get("/api/v1/health").get_json()
            assert body["parser"]["available"] is True
            assert body["persist"]["r2"] is False
            assert body["status"] == "degraded"
        finally:
            next(ctx, None)

    def test_ok_when_parser_up_and_r2_configured(self, client, seeded_db_path, monkeypatch):
        monkeypatch.setenv("CNCFLOW_R2_ACCOUNT_ID", "acct")
        monkeypatch.setenv("CNCFLOW_R2_ACCESS_KEY_ID", "key")
        monkeypatch.setenv("CNCFLOW_R2_SECRET_ACCESS_KEY", "secret")
        monkeypatch.setenv("CNCFLOW_R2_BUCKET", "cncflow-files")
        monkeypatch.setenv("CNCFLOW_REQUIRE_PERSISTENT_DB", "1")
        ctx = self._with_live_parser(seeded_db_path)
        next(ctx)
        try:
            body = client.get("/api/v1/health").get_json()
            assert body["parser"]["available"] is True
            assert body["persist"]["r2"] is True
            assert body["status"] == "ok"
        finally:
            next(ctx, None)

