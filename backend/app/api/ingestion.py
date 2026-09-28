"""Ingestion job management (administrative)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import AdminDep, QueueDep, SessionsDep
from app.core.errors import ValidationFailedError
from app.core.logging import get_logger
from app.db.models import JobStatus
from app.repositories.jobs import JobRepository
from app.schemas.ingestion import IngestionJobCreate, IngestionJobOut
from app.services.ingestion import SOURCES
from app.workers.tasks import INGESTION_TASK

log = get_logger(__name__)

router = APIRouter(prefix="/ingestion", tags=["ingestion"], dependencies=[AdminDep])


@router.post(
    "/jobs",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=IngestionJobOut,
    summary="Create and enqueue an ingestion job",
)
async def create_job(
    body: IngestionJobCreate, sessions: SessionsDep, queue: QueueDep
) -> IngestionJobOut:
    if body.source not in SOURCES:
        raise ValidationFailedError(f"Unknown source {body.source!r}")
    job = await JobRepository(sessions).create(body.source, body.params.model_dump())
    await queue.enqueue_job(INGESTION_TASK, str(job.id), _job_id=f"ingest-{job.id}")
    log.info("ingestion.job_enqueued", job_id=str(job.id), source=body.source)
    return IngestionJobOut.model_validate(job)


@router.get("/jobs", response_model=list[IngestionJobOut], summary="Recent ingestion jobs")
async def list_jobs(
    sessions: SessionsDep, limit: Annotated[int, Query(ge=1, le=200)] = 50
) -> list[IngestionJobOut]:
    return [IngestionJobOut.model_validate(j) for j in await JobRepository(sessions).list(limit)]


@router.get("/jobs/{job_id}", response_model=IngestionJobOut, summary="Ingestion job status")
async def get_job(job_id: uuid.UUID, sessions: SessionsDep) -> IngestionJobOut:
    return IngestionJobOut.model_validate(await JobRepository(sessions).get(job_id))


@router.post(
    "/jobs/{job_id}/resume",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=IngestionJobOut,
    summary="Re-enqueue a failed or interrupted job; it continues from its checkpoint",
)
async def resume_job(job_id: uuid.UUID, sessions: SessionsDep, queue: QueueDep) -> IngestionJobOut:
    job = await JobRepository(sessions).get(job_id)
    if job.status not in {JobStatus.FAILED, JobStatus.RUNNING, JobStatus.QUEUED}:
        raise ValidationFailedError(f"Job is {job.status.value}; nothing to resume")
    await queue.enqueue_job(
        INGESTION_TASK, str(job.id), _job_id=f"ingest-{job.id}-{job.attempts + 1}"
    )
    return IngestionJobOut.model_validate(job)
