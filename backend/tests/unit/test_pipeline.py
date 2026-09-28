"""Pipeline orchestration: checkpoints, resume after failure, invalid records, hydration."""

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest

from app.db.models import JobStatus
from app.db.session import create_engine, create_sessionmaker, create_tables
from app.ingestion.loader import LoadStats
from app.ingestion.pipeline import IngestionParams, IngestionPipeline
from app.ingestion.sources.base import PaperSource, RawPayload, SearchFilters, SourcePage
from app.models.domain import AuthorRecord, ExternalIds, PaperRecord
from app.repositories.jobs import JobRepository
from tests.fakes import ScriptedGraph


class FakeSource(PaperSource):
    name = "fake"
    id_field = "openalex"

    def __init__(self, pages: list[list[RawPayload]], fail_on_page: int | None = None) -> None:
        self.pages = pages
        self.fail_on_page = fail_on_page
        self.requested_cursors: list[str | None] = []
        self.lookups: list[list[str]] = []

    async def search(
        self,
        query: str,
        *,
        cursor: str | None = None,
        per_page: int = 50,
        filters: SearchFilters | None = None,
    ) -> SourcePage:
        self.requested_cursors.append(cursor)
        index = int(cursor or 0)
        if index == self.fail_on_page:
            self.fail_on_page = None  # fail once
            raise ConnectionError("source went away")
        items = self.pages[index] if index < len(self.pages) else []
        nxt = str(index + 1) if index + 1 < len(self.pages) else None
        return SourcePage(items=items, next_cursor=nxt, total=sum(map(len, self.pages)))

    async def fetch_paper(self, external_id: str) -> RawPayload | None:
        return None

    async def fetch_papers(self, external_ids: list[str]) -> list[RawPayload]:
        self.lookups.append(external_ids)
        return [{"id": i, "title": f"Hydrated {i}"} for i in external_ids[:1]]

    async def fetch_citations(
        self, external_id: str, *, cursor: str | None = None, per_page: int = 50
    ) -> SourcePage:
        return SourcePage(items=[], next_cursor=None)

    async def fetch_authors(self, external_id: str) -> list[AuthorRecord]:
        return []

    def external_id(self, raw: RawPayload) -> str:
        return str(raw["id"])

    def parse(self, raw: RawPayload) -> PaperRecord:
        if not raw.get("title"):
            raise ValueError("no title")
        return PaperRecord(
            source=self.name, ids=ExternalIds(openalex=raw["id"]), title=raw["title"]
        )


class CountingLoader:
    def __init__(self) -> None:
        self.loaded: list[str] = []

    async def load(self, records: list[PaperRecord]) -> LoadStats:
        self.loaded += [r.title for r in records]
        return LoadStats(received=len(records), papers_created=len(records))


def pages(n_pages: int, per_page: int = 3) -> list[list[RawPayload]]:
    return [
        [{"id": f"W{p}{i}", "title": f"Paper {p}-{i}"} for i in range(per_page)]
        for p in range(n_pages)
    ]


@pytest.fixture
async def jobs() -> AsyncIterator[JobRepository]:
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    await create_tables(engine)
    yield JobRepository(create_sessionmaker(engine))
    await engine.dispose()


def _pipeline(source: FakeSource, jobs: JobRepository, loader: Any, graph: Any = None):  # type: ignore[no-untyped-def]
    return IngestionPipeline(source, jobs, graph or ScriptedGraph(), loader=loader)


async def _job(jobs: JobRepository, **params: Any) -> uuid.UUID:
    job = await jobs.create("fake", IngestionParams(query="graphs", **params).model_dump())
    return job.id


async def test_runs_all_pages_and_records_stats(jobs: JobRepository) -> None:
    loader = CountingLoader()
    job_id = await _job(jobs)
    job = await _pipeline(FakeSource(pages(3)), jobs, loader).run(job_id)
    assert job.status is JobStatus.SUCCEEDED
    assert len(loader.loaded) == 9
    stored = await jobs.get(job_id)
    assert stored.stats["fetched"] == 9
    assert stored.stats["pages"] == 3
    assert stored.stats["papers_created"] == 9
    assert stored.stats["total_available"] == 9
    assert stored.checkpoint == {"stage": "done"}


async def test_max_results_truncates(jobs: JobRepository) -> None:
    loader = CountingLoader()
    job_id = await _job(jobs, max_results=4)
    await _pipeline(FakeSource(pages(3)), jobs, loader).run(job_id)
    assert len(loader.loaded) == 4


async def test_failed_job_resumes_from_checkpoint(jobs: JobRepository) -> None:
    source = FakeSource(pages(4), fail_on_page=2)
    loader = CountingLoader()
    job_id = await _job(jobs)

    with pytest.raises(ConnectionError):
        await _pipeline(source, jobs, loader).run(job_id)
    failed = await jobs.get(job_id)
    assert failed.status is JobStatus.FAILED
    assert failed.checkpoint == {"stage": "search", "cursor": "2", "fetched": 6}
    assert "ConnectionError" in (failed.error or "")

    resumed = await _pipeline(source, jobs, loader).run(job_id)
    assert resumed.status is JobStatus.SUCCEEDED
    assert resumed.attempts == 2
    # Page 0 and 1 were not fetched again: the second run started at cursor "2".
    assert source.requested_cursors == [None, "1", "2", "2", "3"]
    assert len(loader.loaded) == 12
    assert len(set(loader.loaded)) == 12
    assert (await jobs.get(job_id)).stats["fetched"] == 12


async def test_invalid_records_are_counted_and_skipped(jobs: JobRepository) -> None:
    loader = CountingLoader()
    job_id = await _job(jobs)
    bad = [[{"id": "W1", "title": "ok"}, {"id": "W2", "title": ""}]]
    await _pipeline(FakeSource(bad), jobs, loader).run(job_id)
    assert loader.loaded == ["ok"]
    assert (await jobs.get(job_id)).stats["invalid"] == 1


async def test_hydration_fetches_most_cited_stubs_and_marks_them(jobs: JobRepository) -> None:
    graph = ScriptedGraph(
        {
            "ingestion.stubs": [
                {"id": "paper:s1", "external_id": "W9"},
                {"id": "paper:s2", "external_id": "W8"},
            ]
        }
    )
    source = FakeSource(pages(1))
    loader = CountingLoader()
    job_id = await _job(jobs, hydrate_references=2)
    await _pipeline(source, jobs, loader, graph).run(job_id)
    assert source.lookups == [["W9", "W8"]]
    assert "Hydrated W9" in loader.loaded
    marked = [params for label, _, params in graph.calls if label == "ingestion.mark_hydrated"]
    assert marked == [{"ids": ["paper:s1", "paper:s2"]}]
    assert (await jobs.get(job_id)).stats["hydrated"] == 1


def test_params_validation() -> None:
    with pytest.raises(ValueError):
        IngestionParams(query="x")
    with pytest.raises(ValueError):
        IngestionParams(query="graphs", year_from=2022, year_to=2020)
