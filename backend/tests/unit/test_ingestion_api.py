from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api.deps import get_queue
from app.core.config import Settings
from app.db.session import create_engine, create_sessionmaker, create_tables
from app.main import create_app
from tests.fakes import ScriptedGraph


class FakeQueue:
    def __init__(self) -> None:
        self.enqueued: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    async def enqueue_job(self, name: str, *args: Any, **kwargs: Any) -> None:
        self.enqueued.append((name, args, kwargs))


@pytest.fixture
async def setup():  # type: ignore[no-untyped-def]
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    await create_tables(engine)
    queue = FakeQueue()

    def make(**settings: Any) -> TestClient:
        app = create_app(Settings(log_json=False, **settings))
        app.state.graph = ScriptedGraph()
        app.state.sessions = create_sessionmaker(engine)
        app.dependency_overrides[get_queue] = lambda: queue
        return TestClient(app)

    yield make, queue
    await engine.dispose()


BODY = {"source": "openalex", "params": {"query": "graph neural networks fraud", "max_results": 50}}


async def test_create_job_enqueues_and_is_queryable(setup) -> None:  # type: ignore[no-untyped-def]
    make, queue = setup
    client = make(app_env="development")
    created = client.post("/api/ingestion/jobs", json=BODY)
    assert created.status_code == 202
    job = created.json()
    assert job["status"] == "queued"
    assert job["params"]["max_results"] == 50
    assert queue.enqueued[0][0] == "run_ingestion_job"
    assert queue.enqueued[0][1] == (job["id"],)

    fetched = client.get(f"/api/ingestion/jobs/{job['id']}")
    assert fetched.json()["id"] == job["id"]
    assert len(client.get("/api/ingestion/jobs").json()) == 1


async def test_invalid_params_rejected(setup) -> None:  # type: ignore[no-untyped-def]
    make, _ = setup
    client = make(app_env="development")
    bad = {"source": "openalex", "params": {"query": "x"}}
    assert client.post("/api/ingestion/jobs", json=bad).status_code == 422
    unknown = {"source": "nope", "params": {"query": "graphs"}}
    assert client.post("/api/ingestion/jobs", json=unknown).status_code == 422


async def test_admin_token_required_when_configured(setup) -> None:  # type: ignore[no-untyped-def]
    make, _ = setup
    client = make(app_env="development", admin_api_token=SecretStr("s3cret"))
    assert client.post("/api/ingestion/jobs", json=BODY).status_code == 401
    assert (
        client.post(
            "/api/ingestion/jobs", json=BODY, headers={"X-Admin-Token": "wrong"}
        ).status_code
        == 401
    )
    ok = client.post("/api/ingestion/jobs", json=BODY, headers={"X-Admin-Token": "s3cret"})
    assert ok.status_code == 202


async def test_admin_api_disabled_in_production_without_token(setup) -> None:  # type: ignore[no-untyped-def]
    make, _ = setup
    client = make(app_env="production")
    assert client.get("/api/ingestion/jobs").status_code == 403


async def test_resume_requeues_unfinished_job(setup) -> None:  # type: ignore[no-untyped-def]
    make, queue = setup
    client = make(app_env="development")
    job_id = client.post("/api/ingestion/jobs", json=BODY).json()["id"]
    assert client.post(f"/api/ingestion/jobs/{job_id}/resume").status_code == 202
    assert len(queue.enqueued) == 2
