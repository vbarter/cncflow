"""Pages 跨域：仅在配置了 CNCFLOW_CORS_ORIGINS 时回显 Origin。"""


def test_cors_headers_when_origin_allowed(monkeypatch, seeded_db_path):
    monkeypatch.setenv("CNCFLOW_CORS_ORIGINS", "https://cncflow.pages.dev")
    from app import create_app
    client = create_app(db_path=seeded_db_path).test_client()
    response = client.get("/api/v1/health", headers={"Origin": "https://cncflow.pages.dev"})
    assert response.headers["Access-Control-Allow-Origin"] == "https://cncflow.pages.dev"


def test_cors_preflight(monkeypatch, seeded_db_path):
    monkeypatch.setenv("CNCFLOW_CORS_ORIGINS", "*")
    from app import create_app
    client = create_app(db_path=seeded_db_path).test_client()
    response = client.options("/api/v1/quotes", headers={"Origin": "https://example.com"})
    assert response.status_code == 204
    assert response.headers["Access-Control-Allow-Origin"] == "https://example.com"


def test_no_cors_by_default(client):
    response = client.get("/api/v1/health", headers={"Origin": "https://evil.example"})
    assert "Access-Control-Allow-Origin" not in response.headers
