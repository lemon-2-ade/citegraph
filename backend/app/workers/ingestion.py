"""Arq worker: ``arq app.workers.ingestion.WorkerSettings``.

The queue message carries only the job ID; all durable state (params, checkpoint,
status) lives in PostgreSQL, so a lost Redis message never loses job history and a
re-enqueued job resumes from its checkpoint.
"""

from __future__ import annotations

import uuid
from typing import Any, ClassVar

from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.resources import Resources
from app.services.ingestion import run_job

log = get_logger(__name__)

INGESTION_TASK = "run_ingestion_job"


async def run_ingestion_job(ctx: dict[str, Any], job_id: str) -> dict[str, Any]:
    resources: Resources = ctx["resources"]
    job = await run_job(resources, uuid.UUID(job_id))
    return {"job_id": job_id, "status": job.status.value}


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    ctx["resources"] = Resources.create(settings)
    log.info("worker.startup")


async def shutdown(ctx: dict[str, Any]) -> None:
    await ctx["resources"].close()
    log.info("worker.shutdown")


class WorkerSettings:
    functions: ClassVar[list[Any]] = [run_ingestion_job]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 2
    job_timeout = 6 * 60 * 60
    # Pipeline failures are recorded on the job and resumed explicitly; do not let arq
    # retry blindly.
    max_tries = 1
