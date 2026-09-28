"""Analytics against a real Neo4j loaded with the seed dataset.

The GDS test additionally requires the Graph Data Science plugin (present in the
Docker Compose stack) and is skipped otherwise.
"""

import pytest

from app.analytics.backends import GdsBackend, NetworkXBackend, gds_available
from app.analytics.service import AnalyticsService
from app.graph.client import GraphClient
from app.graph.schema import apply_schema
from app.ingestion.seed import seed_graph

pytestmark = pytest.mark.integration


async def _seeded(graph: GraphClient) -> None:
    await apply_schema(graph)
    await seed_graph(graph)


async def _assert_results(graph: GraphClient) -> None:
    rows = await graph.read(
        "MATCH (p:Paper) WHERE p.pagerank IS NULL OR p.in_degree IS NULL RETURN count(p) AS n"
    )
    assert rows[0]["n"] == 0
    top = await graph.read(
        "MATCH (p:Paper) RETURN p.seed_key AS key ORDER BY p.pagerank DESC LIMIT 15"
    )
    # Heavily cited foundations in the seed should rank near the top.
    assert {"transformer", "gcn"} & {r["key"] for r in top}
    communities = await graph.read(
        "MATCH (c:Community {scope: 'papers'}) RETURN c.size AS size, c.top_topics AS topics"
    )
    assert len(communities) >= 2
    assert all(c["size"] >= 3 and c["topics"] for c in communities)
    collab = await graph.read("MATCH ()-[r:COLLABORATED_WITH]->() RETURN count(r) AS n")
    assert collab[0]["n"] > 0


async def test_networkx_analytics_on_seed(neo4j_graph: GraphClient) -> None:
    await _seeded(neo4j_graph)
    report = await AnalyticsService(neo4j_graph, NetworkXBackend(neo4j_graph)).run()
    assert report.papers > 0
    await _assert_results(neo4j_graph)
    # Re-running replaces (not duplicates) communities.
    await AnalyticsService(neo4j_graph, NetworkXBackend(neo4j_graph)).run()
    rows = await neo4j_graph.read(
        "MATCH (p:Paper)-[r:IN_COMMUNITY]->() WITH p, count(r) AS n "
        "WHERE n > 1 RETURN count(p) AS n"
    )
    assert rows[0]["n"] == 0


async def test_gds_analytics_on_seed(neo4j_graph: GraphClient) -> None:
    if not await gds_available(neo4j_graph):
        pytest.skip("Neo4j Graph Data Science plugin not installed")
    await _seeded(neo4j_graph)
    report = await AnalyticsService(neo4j_graph, GdsBackend(neo4j_graph)).run()
    assert report.backend == "gds"
    await _assert_results(neo4j_graph)
