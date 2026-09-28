"""Resumable ingestion pipeline.

    External API -> raw payload (stored) -> validation/parsing -> normalisation
    -> in-batch dedup -> entity resolution -> graph construction -> checkpoint

A job has two stages:

``search``
    Page through the source's search results. After each page is written to Neo4j the
    job's checkpoint (source cursor + counters) is committed to PostgreSQL. A crashed or
    failed job restarts from the last committed cursor; because graph writes are
    idempotent MERGEs, re-processing the page that was in flight is harmless.
``hydrate``
    Optionally fetch full metadata for the most-cited *stub* papers (references seen but
    not yet ingested), expanding the graph one hop outwards.

Topic extraction, embeddings and analytics are separate steps (``researchgraph embed``
and ``researchgraph analyze``) so they can be re-run without re-fetching.
"""

from __future__ import annotations

import uuid
from typing import Any, LiteralString

import structlog
from pydantic import BaseModel, Field, ValidationError, model_validator

from app.core.logging import get_logger
from app.db.models import IngestionJob, JobStatus
from app.graph.client import GraphClient
from app.ingestion.loader import GraphLoader, LoadStats
from app.ingestion.sources.base import PaperSource, RawPayload, SearchFilters
from app.models.domain import PaperRecord
from app.repositories.jobs import JobRepository

log = get_logger(__name__)

HYDRATE_BATCH = 50

_STUBS_TO_HYDRATE: dict[str, LiteralString] = {
    "doi": """
        MATCH (s:Paper {is_stub: true}) WHERE s.doi IS NOT NULL
          AND coalesce(s.hydration_attempted, false) = false
        WITH s, COUNT { (:Paper)-[:CITES]->(s) } AS n ORDER BY n DESC LIMIT $limit
        RETURN s.id AS id, s.doi AS external_id""",
    "openalex": """
        MATCH (s:Paper {is_stub: true}) WHERE s.openalex_id IS NOT NULL
          AND coalesce(s.hydration_attempted, false) = false
        WITH s, COUNT { (:Paper)-[:CITES]->(s) } AS n ORDER BY n DESC LIMIT $limit
        RETURN s.id AS id, s.openalex_id AS external_id""",
    "arxiv": """
        MATCH (s:Paper {is_stub: true}) WHERE s.arxiv_id IS NOT NULL
          AND coalesce(s.hydration_attempted, false) = false
        WITH s, COUNT { (:Paper)-[:CITES]->(s) } AS n ORDER BY n DESC LIMIT $limit
        RETURN s.id AS id, s.arxiv_id AS external_id""",
    "s2": """
        MATCH (s:Paper {is_stub: true}) WHERE s.s2_id IS NOT NULL
          AND coalesce(s.hydration_attempted, false) = false
        WITH s, COUNT { (:Paper)-[:CITES]->(s) } AS n ORDER BY n DESC LIMIT $limit
        RETURN s.id AS id, s.s2_id AS external_id""",
}

_MARK_HYDRATION_ATTEMPTED = """
UNWIND $ids AS id
MATCH (s:Paper {id: id}) WHERE s.is_stub = true
SET s.hydration_attempted = true
"""


class IngestionParams(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    max_results: int = Field(default=200, ge=1, le=50_000)
    per_page: int = Field(default=50, ge=1, le=200)
    year_from: int | None = Field(default=None, ge=1600, le=2100)
    year_to: int | None = Field(default=None, ge=1600, le=2100)
    # Fetch metadata for up to N of the most-cited referenced-but-missing papers.
    hydrate_references: int = Field(default=0, ge=0, le=10_000)

    @model_validator(mode="after")
    def _years(self) -> IngestionParams:
        if self.year_from and self.year_to and self.year_from > self.year_to:
            raise ValueError("year_from must be <= year_to")
        return self


class IngestionPipeline:
    def __init__(
        self,
        source: PaperSource,
        jobs: JobRepository,
        graph: GraphClient,
        loader: GraphLoader | None = None,
    ) -> None:
        self._source = source
        self._jobs = jobs
        self._graph = graph
        self._loader = loader or GraphLoader(graph)

    async def run(self, job_id: uuid.UUID) -> IngestionJob:
        job = await self._jobs.start(job_id)
        structlog.contextvars.bind_contextvars(job_id=str(job_id), source=self._source.name)
        params = IngestionParams.model_validate(job.params)
        checkpoint: dict[str, Any] = dict(job.checkpoint or {})
        stats: dict[str, Any] = dict(job.stats or {})
        log.info("ingestion.job_started", attempt=job.attempts, resume_from=checkpoint or None)
        try:
            if checkpoint.get("stage", "search") == "search":
                checkpoint, stats = await self._search_stage(job_id, params, checkpoint, stats)
                checkpoint = {"stage": "hydrate", "hydrated": 0}
                await self._jobs.save_checkpoint(job_id, checkpoint, stats)
            if params.hydrate_references:
                checkpoint, stats = await self._hydrate_stage(job_id, params, checkpoint, stats)
            await self._jobs.save_checkpoint(job_id, {"stage": "done"}, stats)
            finished = await self._jobs.finish(job_id, JobStatus.SUCCEEDED)
            log.info("ingestion.job_succeeded", **_numeric(stats))
            return finished
        except BaseException as exc:
            # Progress up to the last checkpoint is kept; the job can be resumed.
            await self._jobs.finish(job_id, JobStatus.FAILED, error=f"{type(exc).__name__}: {exc}")
            log.exception("ingestion.job_failed", checkpoint=checkpoint)
            raise
        finally:
            structlog.contextvars.unbind_contextvars("job_id", "source")

    # ------------------------------------------------------------------ stages
    async def _search_stage(
        self,
        job_id: uuid.UUID,
        params: IngestionParams,
        checkpoint: dict[str, Any],
        stats: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        filters = SearchFilters(year_from=params.year_from, year_to=params.year_to)
        fetched = int(checkpoint.get("fetched", 0))
        cursor: str | None = checkpoint.get("cursor")
        while fetched < params.max_results:
            page = await self._source.search(
                params.query, cursor=cursor, per_page=params.per_page, filters=filters
            )
            if stats.get("total_available") is None and page.total is not None:
                stats["total_available"] = page.total
            items = page.items[: params.max_results - fetched]
            if not items:
                break
            batch_stats = await self._process(job_id, items, stats)
            fetched += len(items)
            cursor = page.next_cursor
            stats["pages"] = stats.get("pages", 0) + 1
            checkpoint = {"stage": "search", "cursor": cursor, "fetched": fetched}
            await self._jobs.save_checkpoint(job_id, checkpoint, stats)
            log.info("ingestion.page_done", fetched=fetched, **batch_stats.as_dict())
            if cursor is None:
                break
        return checkpoint, stats

    async def _hydrate_stage(
        self,
        job_id: uuid.UUID,
        params: IngestionParams,
        checkpoint: dict[str, Any],
        stats: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        hydrated = int(checkpoint.get("hydrated", 0))
        query = _STUBS_TO_HYDRATE.get(self._source.id_field)
        if query is None:
            raise ValueError(f"Source {self._source.name!r} does not support hydration")
        while hydrated < params.hydrate_references:
            limit = min(HYDRATE_BATCH, params.hydrate_references - hydrated)
            stubs = await self._graph.read(query, {"limit": limit}, label="ingestion.stubs")
            if not stubs:
                break
            raws = await self._source.fetch_papers([s["external_id"] for s in stubs])
            await self._process(job_id, raws, stats)
            # Stubs the source could not return must not be selected forever.
            await self._graph.write(
                _MARK_HYDRATION_ATTEMPTED,
                {"ids": [s["id"] for s in stubs]},
                label="ingestion.mark_hydrated",
            )
            hydrated += len(stubs)
            stats["hydrated"] = stats.get("hydrated", 0) + len(raws)
            checkpoint = {"stage": "hydrate", "hydrated": hydrated}
            await self._jobs.save_checkpoint(job_id, checkpoint, stats)
        return checkpoint, stats

    # ------------------------------------------------------------------ helpers
    async def _process(
        self, job_id: uuid.UUID, items: list[RawPayload], stats: dict[str, Any]
    ) -> LoadStats:
        raw_rows: list[tuple[str, RawPayload]] = []
        records: list[PaperRecord] = []
        for raw in items:
            try:
                raw_rows.append((self._source.external_id(raw), raw))
                records.append(self._source.parse(raw))
            except (ValueError, ValidationError) as exc:
                stats["invalid"] = stats.get("invalid", 0) + 1
                log.warning("ingestion.invalid_record", error=str(exc)[:300])
        await self._jobs.store_raw(self._source.name, raw_rows, job_id)
        batch_stats = await self._loader.load(records)
        stats["fetched"] = stats.get("fetched", 0) + len(items)
        for key, value in batch_stats.as_dict().items():
            stats[key] = stats.get(key, 0) + value
        return batch_stats


def _numeric(stats: dict[str, Any]) -> dict[str, int]:
    return {k: v for k, v in stats.items() if isinstance(v, int)}
