"""Analytics run execution shared by the worker and the CLI."""

from __future__ import annotations

import uuid

from app.analytics.backends import select_backend
from app.analytics.service import AnalyticsOptions, AnalyticsService
from app.core.resources import Resources
from app.db.models import AnalyticsRun, JobStatus
from app.repositories.analytics_runs import AnalyticsRunRepository


async def execute_run(resources: Resources, run_id: uuid.UUID) -> AnalyticsRun:
    runs = AnalyticsRunRepository(resources.sessions)
    run = await runs.get(run_id)
    options = dict(run.options)
    preference = str(options.pop("backend", None) or resources.settings.analytics_backend)
    backend = await select_backend(resources.graph, preference)
    await runs.start(run_id, backend.name)
    try:
        report = await AnalyticsService(resources.graph, backend, AnalyticsOptions(**options)).run()
    except Exception as exc:
        await runs.finish(run_id, JobStatus.FAILED, error=f"{type(exc).__name__}: {exc}")
        raise
    return await runs.finish(run_id, JobStatus.SUCCEEDED, report=report.as_dict())
