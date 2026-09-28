import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import JobStatus
from app.repositories.jobs import JobRepository

pytestmark = pytest.mark.integration


async def test_job_checkpoint_roundtrip_on_postgres(
    pg_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    repo = JobRepository(pg_sessionmaker)
    job = await repo.create("openalex", {"query": "knowledge graphs", "max_results": 100})
    await repo.start(job.id)
    await repo.save_checkpoint(job.id, {"cursor": "IlsxLjAsIDEwXSI="}, {"fetched": 25})
    await repo.finish(job.id, JobStatus.FAILED, error="network")
    resumed = await repo.start(job.id)
    assert resumed.checkpoint["cursor"] == "IlsxLjAsIDEwXSI="
    assert resumed.attempts == 2
    await repo.store_raw("openalex", [("W1", {"id": "W1", "nested": {"a": [1, 2]}})], job.id)
    await repo.store_raw("openalex", [("W1", {"id": "W1", "nested": {"a": [3]}})], job.id)
