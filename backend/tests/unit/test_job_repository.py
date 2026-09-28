"""JobRepository against SQLite (same code path as PostgreSQL via SQLAlchemy)."""

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import func, select

from app.core.errors import NotFoundError, ValidationFailedError
from app.db.models import JobStatus, RawRecord
from app.db.session import create_engine, create_sessionmaker, create_tables
from app.repositories.jobs import JobRepository


@pytest.fixture
async def repo() -> AsyncIterator[JobRepository]:
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    await create_tables(engine)
    yield JobRepository(create_sessionmaker(engine))
    await engine.dispose()


async def test_job_lifecycle(repo: JobRepository) -> None:
    job = await repo.create("openalex", {"query": "graph neural networks"})
    assert job.status is JobStatus.QUEUED

    started = await repo.start(job.id)
    assert started.status is JobStatus.RUNNING
    assert started.attempts == 1

    await repo.save_checkpoint(job.id, {"cursor": "abc"}, {"fetched": 25})
    loaded = await repo.get(job.id)
    assert loaded.checkpoint == {"cursor": "abc"}
    assert loaded.stats == {"fetched": 25}

    done = await repo.finish(job.id, JobStatus.SUCCEEDED)
    assert done.finished_at is not None
    with pytest.raises(ValidationFailedError):
        await repo.start(job.id)


async def test_failed_job_can_be_resumed_with_checkpoint(repo: JobRepository) -> None:
    job = await repo.create("openalex", {})
    await repo.start(job.id)
    await repo.save_checkpoint(job.id, {"cursor": "page-3"}, {"fetched": 50})
    await repo.finish(job.id, JobStatus.FAILED, error="HTTP 503")

    resumed = await repo.start(job.id)
    assert resumed.attempts == 2
    assert resumed.error is None
    assert resumed.checkpoint == {"cursor": "page-3"}


async def test_unknown_job(repo: JobRepository) -> None:
    import uuid

    with pytest.raises(NotFoundError):
        await repo.get(uuid.uuid4())


async def test_raw_records_are_upserted(repo: JobRepository) -> None:
    await repo.store_raw("openalex", [("W1", {"v": 1}), ("W2", {"v": 2})], None)
    await repo.store_raw("openalex", [("W1", {"v": 3})], None)
    async with repo._sessions() as session:
        count = await session.scalar(select(func.count()).select_from(RawRecord))
        w1 = await session.scalar(select(RawRecord).where(RawRecord.external_id == "W1"))
    assert count == 2
    assert w1 is not None
    assert w1.payload == {"v": 3}
