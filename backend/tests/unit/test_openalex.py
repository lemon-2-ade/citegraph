import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.ingestion.http import HttpFetcher, RateLimiter
from app.ingestion.sources.base import SearchFilters
from app.ingestion.sources.openalex import (
    OpenAlexSource,
    extract_arxiv_id,
    reconstruct_abstract,
    short_id,
)

PAGE = json.loads(
    (Path(__file__).parent.parent / "fixtures" / "openalex_works_page.json").read_text()
)


def _source(handler: Any) -> tuple[OpenAlexSource, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def recording(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(recording))
    fetcher = HttpFetcher(client, RateLimiter(1000), max_attempts=2, max_backoff=0.01)
    return OpenAlexSource(fetcher, "https://api.openalex.org", mailto="me@example.org"), seen


def test_short_id() -> None:
    assert short_id("https://openalex.org/W1000000001") == "W1000000001"
    assert short_id("w42") == "W42"
    assert short_id(None) is None


def test_reconstruct_abstract_orders_by_position() -> None:
    assert reconstruct_abstract({"world": [1], "hello": [0], "again": [3], "hello,": [2]}) == (
        "hello world hello, again"
    )
    assert reconstruct_abstract(None) is None
    assert reconstruct_abstract({}) is None


def test_extract_arxiv_from_doi_and_locations() -> None:
    assert extract_arxiv_id(PAGE["results"][1]) == "1901.00002"
    assert extract_arxiv_id(PAGE["results"][0]) == "2101.00001"
    assert extract_arxiv_id({"doi": None, "locations": []}) is None


def test_parse_full_work() -> None:
    source, _ = _source(lambda r: httpx.Response(200))
    paper = source.parse(PAGE["results"][0])
    assert paper.source == "openalex"
    assert paper.ids.openalex == "W1000000001"
    assert paper.ids.doi == "10.9999/synth.001"
    assert paper.ids.arxiv == "2101.00001"
    assert paper.title == "Synthetic Graph Networks for Testing"
    assert paper.abstract == "We test graphs."
    assert paper.year == 2021
    assert paper.citation_count == 12
    assert [a.name for a in paper.authors] == ["Ada Example", "Bo Sample"]
    assert paper.authors[0].orcid == "0000-0002-1825-0097"
    assert paper.authors[0].institutions[0].country == "IN"
    assert paper.venue is not None and paper.venue.type == "journal"
    assert paper.topics[0].name == "Graph Neural Networks"
    assert paper.topics[0].score == pytest.approx(0.98)
    assert paper.keywords == ["Message passing"]
    assert [r.openalex for r in paper.references] == ["W1000000002", "W1000000003"]


def test_parse_sparse_work_falls_back_gracefully() -> None:
    source, _ = _source(lambda r: httpx.Response(200))
    paper = source.parse(PAGE["results"][1])
    assert paper.title == "Synthetic Preprint & Baseline"  # display_name, HTML unescaped
    assert paper.authors[0].name == "Chen Placeholder"  # raw_author_name fallback
    assert paper.authors[0].openalex is None
    assert paper.venue is not None and paper.venue.type == "repository"
    assert paper.abstract is None


def test_parse_rejects_untitled_work() -> None:
    source, _ = _source(lambda r: httpx.Response(200))
    with pytest.raises(ValueError, match="no title"):
        source.parse({"id": "https://openalex.org/W1", "title": None, "display_name": None})


async def test_search_sends_filters_cursor_and_mailto() -> None:
    source, seen = _source(lambda r: httpx.Response(200, json=PAGE))
    page = await source.search(
        "graph neural networks", per_page=500, filters=SearchFilters(year_from=2018, year_to=2021)
    )
    params = seen[0].url.params
    assert params["search"] == "graph neural networks"
    assert params["filter"] == "from_publication_date:2018-01-01,to_publication_date:2021-12-31"
    assert params["cursor"] == "*"
    assert params["per-page"] == "200"  # clamped to the API maximum
    assert params["mailto"] == "me@example.org"
    assert page.next_cursor == "CURSOR-2"
    assert page.total == 2
    assert len(page.items) == 2


async def test_empty_page_ends_pagination() -> None:
    body = {"meta": {"count": 2, "next_cursor": "still-here"}, "results": []}
    source, _ = _source(lambda r: httpx.Response(200, json=body))
    page = await source.search("x", cursor="CURSOR-2")
    assert page.next_cursor is None


async def test_fetch_papers_chunks_or_filters() -> None:
    source, seen = _source(lambda r: httpx.Response(200, json={"meta": {}, "results": []}))
    await source.fetch_papers([f"W{i}" for i in range(120)])
    assert len(seen) == 3
    assert seen[0].url.params["filter"].startswith("openalex:W0|W1|")


async def test_fetch_paper_404_is_none() -> None:
    source, _ = _source(lambda r: httpx.Response(404))
    assert await source.fetch_paper("W404") is None


async def test_fetch_citations_uses_cites_filter() -> None:
    source, seen = _source(lambda r: httpx.Response(200, json=PAGE))
    await source.fetch_citations("https://openalex.org/W1000000001")
    assert seen[0].url.params["filter"] == "cites:W1000000001"
