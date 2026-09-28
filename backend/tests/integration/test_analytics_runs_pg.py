import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import ValidationFailedError
from app.db.models import JobStatus
from app.repositories.analytics_runs import AnalyticsRunRepository

pytestmark = pytest.mark.integration


async def test_analytics_run_lifecycle_on_postgres(
    pg_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    runs = AnalyticsRunRepository(pg_sessionmaker)
    run = await runs.create({"community_algorithm": "louvain"})
    with pytest.raises(ValidationFailedError):
        await runs.create({})
    await runs.start(run.id, "networkx")
    done = await runs.finish(run.id, JobStatus.SUCCEEDED, report={"papers": 3})
    assert done.report == {"papers": 3}
    assert (await runs.create({})).status is JobStatus.QUEUED
