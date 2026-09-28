from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.errors import DependencyUnavailableError
from app.db.session import create_engine, create_sessionmaker
from app.main import create_app


class _Graph:
    def __init__(self, fail: bool) -> None:
        self.fail = fail

    async def verify(self) -> None:
        if self.fail:
            raise DependencyUnavailableError("connection refused")

    async def close(self) -> None:
        pass


@pytest.fixture
def make_client() -> Iterator:  # type: ignore[type-arg]
    def _make(fail: bool, db_url: str = "sqlite+aiosqlite:///:memory:") -> TestClient:
        app = create_app(Settings(app_env="test", log_json=False))
        app.state.graph = _Graph(fail)
        app.state.sessions = create_sessionmaker(create_engine(db_url))
        return TestClient(app)

    yield _make


def test_ready_ok_when_dependencies_reachable(make_client) -> None:  # type: ignore[no-untyped-def]
    response = make_client(fail=False).get("/api/health/ready")
    assert response.status_code == 200
    assert response.json()["checks"] == {"neo4j": "ok", "postgres": "ok"}


def test_ready_degraded_when_neo4j_down(make_client) -> None:  # type: ignore[no-untyped-def]
    response = make_client(fail=True).get("/api/health/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"


def test_ready_degraded_when_postgres_down(make_client) -> None:  # type: ignore[no-untyped-def]
    client = make_client(fail=False, db_url="postgresql+asyncpg://u:p@127.0.0.1:1/none")
    response = client.get("/api/health/ready")
    assert response.status_code == 503
    assert response.json()["checks"]["postgres"].startswith("unavailable")
