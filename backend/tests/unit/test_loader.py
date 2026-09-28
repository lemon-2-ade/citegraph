"""Orchestration tests for GraphLoader using a recording fake (no Neo4j).

Cypher behaviour itself is covered by tests/integration/test_loader.py.
"""

from typing import Any

from app.ingestion.loader import GraphLoader, institution_id, topic_id, venue_id
from app.models.domain import (
    AuthorRecord,
    ExternalIds,
    InstitutionRecord,
    PaperRecord,
    VenueRecord,
)
from tests.fakes import ScriptedGraph


def _rows(graph: ScriptedGraph, label: str) -> list[dict[str, Any]]:
    return [row for lbl, _, params in graph.calls if lbl == label for row in params["rows"]]


async def test_batch_internal_references_do_not_create_stubs() -> None:
    graph = ScriptedGraph()
    base = PaperRecord(source="t", ids=ExternalIds(arxiv="1600.00001"), title="Base", year=2016)
    child = PaperRecord(
        source="t",
        ids=ExternalIds(),
        title="Child",
        year=2018,
        references=[ExternalIds(arxiv="1600.00001"), ExternalIds(openalex="W5")],
    )
    stats = await GraphLoader(graph).load([base, child])  # type: ignore[arg-type]
    papers = _rows(graph, "loader.papers")
    ids = {p["title"]: p["id"] for p in papers}
    cites = _rows(graph, "loader.cites")
    stubs = _rows(graph, "loader.stubs")
    assert stats.papers_created == 2
    assert len(stubs) == 1 and stubs[0]["openalex_id"] == "W5"
    assert {(c["src"], c["dst"]) for c in cites} == {
        (ids["Child"], ids["Base"]),
        (ids["Child"], stubs[0]["id"]),
    }


async def test_duplicate_records_in_batch_are_collapsed() -> None:
    graph = ScriptedGraph()
    a = PaperRecord(source="t", ids=ExternalIds(doi="10.1000/a"), title="Same", year=2020)
    b = PaperRecord(source="t", ids=ExternalIds(doi="10.1000/a"), title="Same!", year=2020)
    stats = await GraphLoader(graph).load([a, b])  # type: ignore[arg-type]
    assert stats.duplicates_in_batch == 1
    assert len(_rows(graph, "loader.papers")) == 1


async def test_authors_within_batch_resolve_to_one_node() -> None:
    graph = ScriptedGraph()
    p1 = PaperRecord(
        source="t",
        ids=ExternalIds(),
        title="One",
        authors=[AuthorRecord(name="Wei Wang"), AuthorRecord(name="Li Zhang")],
    )
    p2 = PaperRecord(
        source="t",
        ids=ExternalIds(),
        title="Two",
        authors=[AuthorRecord(name="Li Zhang"), AuthorRecord(name="Wei Wang")],
    )
    stats = await GraphLoader(graph).load([p1, p2])  # type: ignore[arg-type]
    assert stats.authors_created == 2
    assert stats.authors_matched == 2
    wrote = _rows(graph, "loader.wrote")
    assert len({w["author_id"] for w in wrote}) == 2
    assert sorted(w["position"] for w in wrote) == [1, 1, 2, 2]


async def test_self_citation_edge_is_skipped() -> None:
    graph = ScriptedGraph()
    p = PaperRecord(
        source="t",
        ids=ExternalIds(openalex="W1"),
        title="Self",
        references=[ExternalIds(openalex="W1")],
    )
    await GraphLoader(graph).load([p])  # type: ignore[arg-type]
    assert _rows(graph, "loader.cites") == []


def test_vocabulary_ids_are_deterministic() -> None:
    assert topic_id("Graph Neural Networks") == "topic:graph-neural-networks"
    assert venue_id(VenueRecord(name="NeurIPS")) == "venue:neurips"
    assert venue_id(VenueRecord(name="X", openalex="S1")) == "venue:S1"
    assert institution_id(InstitutionRecord(name="U", ror="https://ror.org/05a28rw58")) == (
        "institution:ror:05a28rw58"
    )
    assert institution_id(InstitutionRecord(name="Some Uni", country="IN")) == (
        "institution:some-uni-in"
    )
