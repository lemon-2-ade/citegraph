"""GraphLoader against a real Neo4j (run with the Docker Compose stack)."""

import pytest

from app.graph.client import GraphClient
from app.graph.schema import apply_schema
from app.ingestion.loader import GraphLoader
from app.models.domain import AuthorRecord, ExternalIds, PaperRecord, TopicRecord, VenueRecord

pytestmark = pytest.mark.integration


def _paper(title: str, year: int, authors: list[str], refs: list[ExternalIds], **ids: str):  # type: ignore[no-untyped-def]
    return PaperRecord(
        source="test",
        ids=ExternalIds(**ids),
        title=title,
        year=year,
        authors=[AuthorRecord(name=a) for a in authors],
        venue=VenueRecord(name="Test Venue", type="conference"),
        topics=[TopicRecord(name="Graph Learning", score=0.9)],
        keywords=["graphs"],
        references=refs,
    )


async def _count(graph: GraphClient, query: str) -> int:
    rows = await graph.read(query)
    return int(rows[0]["n"])


async def test_load_is_idempotent_and_creates_stubs(neo4j_graph: GraphClient) -> None:
    await apply_schema(neo4j_graph)
    loader = GraphLoader(neo4j_graph)
    base = _paper("Base Method", 2016, ["Ann Author"], [], arxiv="1600.00001")
    child = _paper(
        "Improved Method",
        2018,
        ["Ann Author", "Ben Builder"],
        [ExternalIds(arxiv="1600.00001"), ExternalIds(openalex="W999")],
        doi="10.1000/improved",
    )
    stats = await loader.load([base, child])
    assert stats.papers_created == 2
    assert stats.stubs_created == 1

    again = await loader.load([base, child])
    assert again.papers_created == 0
    assert again.papers_matched == 2
    assert again.stubs_created == 0

    assert await _count(neo4j_graph, "MATCH (p:Paper) RETURN count(p) AS n") == 3
    assert await _count(neo4j_graph, "MATCH ()-[r:CITES]->() RETURN count(r) AS n") == 2
    assert await _count(neo4j_graph, "MATCH (a:Author) RETURN count(a) AS n") == 2
    assert await _count(neo4j_graph, "MATCH (:Author)-[w:WROTE]->() RETURN count(w) AS n") == 3


async def test_stub_is_filled_when_referenced_paper_arrives(neo4j_graph: GraphClient) -> None:
    await apply_schema(neo4j_graph)
    loader = GraphLoader(neo4j_graph)
    citing = _paper("Citing", 2020, ["C Person"], [ExternalIds(openalex="W42")])
    await loader.load([citing])
    cited = _paper("Cited Work", 2015, ["D Person"], [], openalex="W42")
    stats = await loader.load([cited])
    assert stats.papers_matched == 1  # matched the stub by OpenAlex id
    rows = await neo4j_graph.read(
        "MATCH (:Paper {title: 'Citing'})-[:CITES]->(p:Paper) RETURN p.title AS t, p.is_stub AS s"
    )
    assert rows == [{"t": "Cited Work", "s": False}]


async def test_nodes_split_across_identifiers_are_merged(neo4j_graph: GraphClient) -> None:
    await apply_schema(neo4j_graph)
    loader = GraphLoader(neo4j_graph)
    # Seed knows the paper by arXiv id; another paper references it by OpenAlex id (stub).
    await loader.load([_paper("Transformer Paper", 2017, ["A V"], [], arxiv="1706.03762")])
    await loader.load([_paper("Follow Up", 2019, ["B W"], [ExternalIds(openalex="W7")])])
    assert await _count(neo4j_graph, "MATCH (p:Paper) RETURN count(p) AS n") == 3
    # OpenAlex now delivers the paper with both identifiers -> stub merged into seed node.
    stats = await loader.load(
        [_paper("Transformer Paper", 2017, ["A V"], [], arxiv="1706.03762", openalex="W7")]
    )
    assert stats.papers_merged == 1
    assert await _count(neo4j_graph, "MATCH (p:Paper) RETURN count(p) AS n") == 2
    rows = await neo4j_graph.read(
        "MATCH (:Paper {title: 'Follow Up'})-[:CITES]->(p:Paper) "
        "RETURN p.arxiv_id AS arxiv, p.openalex_id AS oa"
    )
    assert rows == [{"arxiv": "1706.03762", "oa": "W7"}]


async def test_authors_with_shared_coauthor_are_unified(neo4j_graph: GraphClient) -> None:
    await apply_schema(neo4j_graph)
    loader = GraphLoader(neo4j_graph)
    await loader.load([_paper("P1", 2019, ["Wei Wang", "Li Zhang"], [])])
    await loader.load([_paper("P2", 2020, ["Wei Wang", "Li Zhang"], [])])
    await loader.load([_paper("P3", 2021, ["Wei Wang", "Someone Else"], [])])
    rows = await neo4j_graph.read("MATCH (a:Author {name: 'Wei Wang'}) RETURN count(a) AS n")
    # P1/P2 share a co-author -> one node; P3 has no evidence -> separate node.
    assert rows[0]["n"] == 2


async def test_seed_dataset_loads_idempotently(neo4j_graph: GraphClient) -> None:
    from app.ingestion.seed import load_dataset, seed_graph

    await apply_schema(neo4j_graph)
    dataset = load_dataset()
    await seed_graph(neo4j_graph)
    second = await seed_graph(neo4j_graph)
    assert second.papers_created == 0
    assert second.authors_created == 0
    assert await _count(neo4j_graph, "MATCH (p:Paper) RETURN count(p) AS n") == len(dataset.papers)
    assert await _count(neo4j_graph, "MATCH (p:Paper {is_stub: true}) RETURN count(p) AS n") == 0
    assert await _count(neo4j_graph, "MATCH ()-[r:CITES]->() RETURN count(r) AS n") == sum(
        len(p.cites) for p in dataset.papers
    )
