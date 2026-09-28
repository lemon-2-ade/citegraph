"""Ingestion service: source registry and job execution shared by worker, API and CLI."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from app.core.config import Settings
from app.core.errors import ValidationFailedError
from app.core.resources import Resources
from app.db.models import IngestionJob
from app.ingestion.pipeline import IngestionParams, IngestionPipeline
from app.ingestion.sources.base import PaperSource
from app.ingestion.sources.openalex import OpenAlexSource
from app.repositories.jobs import JobRepository

SOURCES: dict[str, Callable[[Settings], PaperSource]] = {
    "openalex": OpenAlexSource.from_settings,
}


def build_source(name: str, settings: Settings) -> PaperSource:
    try:
        factory = SOURCES[name]
    except KeyError:
        raise ValidationFailedError(
            f"Unknown source {name!r}; available: {', '.join(sorted(SOURCES))}"
        ) from None
    return factory(settings)


async def create_job(resources: Resources, source: str, params: IngestionParams) -> IngestionJob:
    if source not in SOURCES:
        raise ValidationFailedError(f"Unknown source {source!r}")
    return await JobRepository(resources.sessions).create(source, params.model_dump())


async def run_job(resources: Resources, job_id: uuid.UUID) -> IngestionJob:
    jobs = JobRepository(resources.sessions)
    job = await jobs.get(job_id)
    source = build_source(job.source, resources.settings)
    try:
        return await IngestionPipeline(source, jobs, resources.graph).run(job_id)
    finally:
        await source.aclose()
