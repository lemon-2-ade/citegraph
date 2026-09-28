"""Persistence for analytics runs (PostgreSQL)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import NotFoundError, ValidationFailedError
from app.db.models import AnalyticsRun, JobStatus, utcnow

# A run still "running" after this long is assumed dead (worker crash) and does not block.
STALE_AFTER = timedelta(hours=6)


class AnalyticsRunRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def create(self, options: dict[str, Any]) -> AnalyticsRun:
        async with self._sessions.begin() as session:
            active = await session.scalar(
                select(AnalyticsRun).where(
                    AnalyticsRun.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
                    AnalyticsRun.created_at > utcnow() - STALE_AFTER,
                )
            )
            if active is not None:
                raise ValidationFailedError(
                    f"Analytics run {active.id} is already {active.status.value}"
                )
            run = AnalyticsRun(options=options, report={})
            session.add(run)
        return run

    async def get(self, run_id: uuid.UUID) -> AnalyticsRun:
        async with self._sessions() as session:
            run = await session.get(AnalyticsRun, run_id)
        if run is None:
            raise NotFoundError(f"Analytics run {run_id} not found")
        return run

    async def list(self, limit: int = 20) -> Sequence[AnalyticsRun]:
        async with self._sessions() as session:
            result = await session.scalars(
                select(AnalyticsRun).order_by(AnalyticsRun.created_at.desc()).limit(limit)
            )
            return result.all()

    async def start(self, run_id: uuid.UUID, backend: str) -> None:
        async with self._sessions.begin() as session:
            run = await session.get(AnalyticsRun, run_id, with_for_update=True)
            if run is None:
                raise NotFoundError(f"Analytics run {run_id} not found")
            run.status = JobStatus.RUNNING
            run.backend = backend
            run.started_at = utcnow()

    async def finish(
        self,
        run_id: uuid.UUID,
        status: JobStatus,
        *,
        report: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> AnalyticsRun:
        async with self._sessions.begin() as session:
            run = await session.get(AnalyticsRun, run_id, with_for_update=True)
            if run is None:
                raise NotFoundError(f"Analytics run {run_id} not found")
            run.status = status
            run.report = report or {}
            run.error = error
            run.finished_at = utcnow()
        return run
