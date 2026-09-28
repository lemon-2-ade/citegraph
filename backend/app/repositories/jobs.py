"""Persistence for ingestion jobs and raw payloads (PostgreSQL)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import NotFoundError, ValidationFailedError
from app.db.models import IngestionJob, JobStatus, RawRecord, utcnow

_RESUMABLE = {JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.FAILED}


class JobRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def create(self, source: str, params: dict[str, Any]) -> IngestionJob:
        async with self._sessions.begin() as session:
            job = IngestionJob(source=source, params=params, checkpoint={}, stats={})
            session.add(job)
        return job

    async def get(self, job_id: uuid.UUID) -> IngestionJob:
        async with self._sessions() as session:
            job = await session.get(IngestionJob, job_id)
        if job is None:
            raise NotFoundError(f"Ingestion job {job_id} not found")
        return job

    async def list(self, limit: int = 50) -> Sequence[IngestionJob]:
        async with self._sessions() as session:
            result = await session.scalars(
                select(IngestionJob).order_by(IngestionJob.created_at.desc()).limit(limit)
            )
            return result.all()

    async def start(self, job_id: uuid.UUID) -> IngestionJob:
        """Mark a job running. Allowed from queued, failed (retry) or running (crash resume)."""
        async with self._sessions.begin() as session:
            job = await session.get(IngestionJob, job_id, with_for_update=True)
            if job is None:
                raise NotFoundError(f"Ingestion job {job_id} not found")
            if job.status not in _RESUMABLE:
                raise ValidationFailedError(f"Job {job_id} is {job.status.value}; cannot start")
            job.status = JobStatus.RUNNING
            job.attempts += 1
            job.error = None
            job.started_at = job.started_at or utcnow()
        return job

    async def save_checkpoint(
        self, job_id: uuid.UUID, checkpoint: dict[str, Any], stats: dict[str, Any]
    ) -> None:
        """Persist progress after a batch has been durably written to the graph."""
        async with self._sessions.begin() as session:
            job = await session.get(IngestionJob, job_id, with_for_update=True)
            if job is None:
                raise NotFoundError(f"Ingestion job {job_id} not found")
            job.checkpoint = dict(checkpoint)
            job.stats = dict(stats)

    async def finish(
        self, job_id: uuid.UUID, status: JobStatus, *, error: str | None = None
    ) -> IngestionJob:
        async with self._sessions.begin() as session:
            job = await session.get(IngestionJob, job_id, with_for_update=True)
            if job is None:
                raise NotFoundError(f"Ingestion job {job_id} not found")
            job.status = status
            job.error = error
            job.finished_at = utcnow()
        return job

    async def store_raw(
        self, source: str, records: Sequence[tuple[str, dict[str, Any]]], job_id: uuid.UUID | None
    ) -> None:
        """Upsert raw payloads keyed by (source, external_id)."""
        if not records:
            return
        async with self._sessions.begin() as session:
            existing = {
                r.external_id: r
                for r in await session.scalars(
                    select(RawRecord).where(
                        RawRecord.source == source,
                        RawRecord.external_id.in_([eid for eid, _ in records]),
                    )
                )
            }
            for external_id, payload in records:
                row = existing.get(external_id)
                if row is None:
                    session.add(
                        RawRecord(
                            source=source, external_id=external_id, payload=payload, job_id=job_id
                        )
                    )
                else:
                    row.payload = payload
                    row.job_id = job_id
                    row.fetched_at = utcnow()
