"""Graph-view queries against a real Neo4j loaded with the seed dataset."""

import pytest

from app.analytics.backends import NetworkXBackend
from app.analytics.service import AnalyticsService
from app.core.errors import NotFoundError
from app.graph.client import GraphClient
from app.graph.schema import apply_schema
from app.ingestion.seed import seed_graph
from app.repositories.graph_view import GraphViewRepository

pytestmark = pytest.mark.integration


async def _prepared(graph: GraphClient) -> GraphViewRepository:
    await apply_schema(graph)
    await seed_graph(graph)
    await AnalyticsService(graph, NetworkXBackend(graph)).run()
    return GraphViewRepository(graph)


async def test_overview_is_bounded_and_self_consistent(neo4j_graph: GraphClient) -> None:
    repo = await _prepared(neo4j_graph)
    view = await repo.overview(30)
    assert len(view.nodes) == 30
    assert view.truncated and view.total_papers and view.total_papers > 30
    ids = {n.id for n in view.nodes}
    assert view.edges and all(e.source in ids and e.target in ids for e in view.edges)
    ranks = [n.pagerank or 0.0 for n in view.nodes]
    assert ranks == sorted(ranks, reverse=True)
    assert any(n.community_id for n in view.nodes)


async def test_neighbourhood_contains_focus_and_only_direct_links_at_depth_one(
    neo4j_graph: GraphClient,
) -> None:
    repo = await _prepared(neo4j_graph)
    rows = await neo4j_graph.read("MATCH (p:Paper {seed_key: 'transformer'}) RETURN p.id AS id")
    focus = rows[0]["id"]
    view = await repo.neighbourhood(focus, depth=1, limit=60)
    assert view.nodes[0].id == focus
    neighbours = await neo4j_graph.read(
        "MATCH (:Paper {id: $id})-[:CITES]-(n:Paper) RETURN DISTINCT n.id AS id", {"id": focus}
    )
    assert {n.id for n in view.nodes} == {focus} | {r["id"] for r in neighbours}

    deeper = await repo.neighbourhood(focus, depth=2, limit=60)
    assert len(deeper.nodes) >= len(view.nodes)


async def test_unknown_paper_raises(neo4j_graph: GraphClient) -> None:
    repo = await _prepared(neo4j_graph)
    with pytest.raises(NotFoundError):
        await repo.neighbourhood("paper:missing", 1, 10)


async def test_search_finds_seed_papers_authors_and_topics(neo4j_graph: GraphClient) -> None:
    from app.repositories.search import SearchRepository

    await apply_schema(neo4j_graph)
    await seed_graph(neo4j_graph)
    await neo4j_graph.write("CALL db.awaitIndexes(30)")
    repo = SearchRepository(neo4j_graph)
    papers = (await repo.search("attention is all", 5)).papers
    assert any("Attention Is All You Need" in h.title for h in papers)
    assert (await repo.search("vaswani", 5)).authors
    assert (await repo.search("attention mech", 5)).topics
    assert (await repo.search("title:(", 5)).papers == []  # syntax is escaped, not executed
