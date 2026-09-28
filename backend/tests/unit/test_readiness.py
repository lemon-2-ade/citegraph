from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.errors import DependencyUnavailableError
from app.main import create_app


class _Graph:
    def __init__(self, fail: bool) -> None:
        self.fail = fail

    async def verify(self) -> None:
        if self.fail:
            raise DependencyUnavailableError("connection refused")

    async def close(self) -> None:
        pass


def _client(fail: bool) -> TestClient:
    app = create_app(Settings(app_env="test", log_json=False))
    app.state.graph = _Graph(fail)
    return TestClient(app)


def test_ready_ok_when_neo4j_reachable() -> None:
    response = _client(fail=False).get("/api/health/ready")
    assert response.status_code == 200
    assert response.json()["checks"]["neo4j"] == "ok"


def test_ready_degraded_when_neo4j_down() -> None:
    response = _client(fail=True).get("/api/health/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
