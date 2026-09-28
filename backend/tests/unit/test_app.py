from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def _client() -> TestClient:
    return TestClient(create_app(Settings(app_env="test", log_json=False)))


def test_health_returns_ok() -> None:
    response = _client().get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_request_id_is_generated_and_echoed() -> None:
    client = _client()
    generated = client.get("/api/health").headers["X-Request-ID"]
    assert len(generated) == 32

    echoed = client.get("/api/health", headers={"X-Request-ID": "abc-123"})
    assert echoed.headers["X-Request-ID"] == "abc-123"


def test_malformed_request_id_is_replaced() -> None:
    response = _client().get("/api/health", headers={"X-Request-ID": "bad id\nwith newline"})
    assert response.headers["X-Request-ID"] != "bad id\nwith newline"


def test_security_headers_present() -> None:
    response = _client().get("/api/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"


def test_openapi_is_served_under_api_prefix() -> None:
    response = _client().get("/api/openapi.json")
    assert response.status_code == 200
    assert response.json()["info"]["title"] == "ResearchGraph API"
