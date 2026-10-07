"""Analytics backends: Neo4j Graph Data Science, or NetworkX over a projection.

Both implement :class:`AnalyticsBackend`. ``auto`` selects GDS when the plugin is
installed (``gds.version()`` succeeds) and NetworkX otherwise, so the same code runs
against the Docker stack (GDS) and in environments without the plugin.
"""

from __future__ import annotations

from typing import LiteralString, Protocol

import networkx as nx
from neo4j.exceptions import ClientError

from app.analytics import algorithms
from app.analytics.algorithms import CommunityAlgorithm
from app.analytics.projection import GraphKind, load_citation_neighbourhood, load_projection
from app.core.logging import get_logger
from app.graph.client import GraphClient

log = get_logger(__name__)


class AnalyticsBackend(Protocol):
    name: str

    async def pagerank(self, kind: GraphKind) -> dict[str, float]: ...

    async def betweenness(self, kind: GraphKind, sample_size: int | None) -> dict[str, float]: ...

    async def communities(
        self, kind: GraphKind, algorithm: CommunityAlgorithm
    ) -> dict[str, int]: ...

    async def personalized_pagerank(self, sources: list[str], limit: int) -> dict[str, float]: ...

    async def close(self) -> None: ...


# --------------------------------------------------------------------------- NetworkX
class NetworkXBackend:
    """Loads each projection once per backend instance and runs algorithms in-process."""

    name = "networkx"

    def __init__(self, graph: GraphClient) -> None:
        self._graph = graph
        self._cache: dict[GraphKind, nx.Graph | nx.DiGraph] = {}

    async def _projection(self, kind: GraphKind) -> nx.Graph | nx.DiGraph:
        if kind not in self._cache:
            self._cache[kind] = await load_projection(self._graph, kind)
            g = self._cache[kind]
            log.info(
                "analytics.projection_loaded",
                kind=kind,
                nodes=g.number_of_nodes(),
                edges=g.number_of_edges(),
            )
        return self._cache[kind]

    async def pagerank(self, kind: GraphKind) -> dict[str, float]:
        weight = "weight" if kind == "collaboration" else None
        return algorithms.pagerank(await self._projection(kind), weight=weight)

    async def betweenness(self, kind: GraphKind, sample_size: int | None) -> dict[str, float]:
        return algorithms.betweenness(await self._projection(kind), sample_size=sample_size)

    async def communities(self, kind: GraphKind, algorithm: CommunityAlgorithm) -> dict[str, int]:
        return algorithms.communities(await self._projection(kind), algorithm=algorithm)

    async def personalized_pagerank(self, sources: list[str], limit: int) -> dict[str, float]:
        sub = await load_citation_neighbourhood(self._graph, sources, hops=2)
        # Undirected view: related work lies both upstream (references) and downstream.
        undirected = sub.to_undirected()
        present = [s for s in sources if s in undirected]
        if not present:
            return {}
        scores = algorithms.pagerank(undirected, personalization={s: 1.0 for s in present})
        return dict(algorithms.top_k(scores, limit, exclude=present))

    async def close(self) -> None:
        self._cache.clear()


# --------------------------------------------------------------------------- GDS
_GDS_PROJECTIONS: dict[str, LiteralString] = {
    "rg_citations": """
        CALL gds.graph.project('rg_citations', 'Paper', {CITES: {orientation: 'NATURAL'}})
        YIELD nodeCount RETURN nodeCount""",
    "rg_citations_undirected": """
        CALL gds.graph.project('rg_citations_undirected', 'Paper',
                               {CITES: {orientation: 'UNDIRECTED'}})
        YIELD nodeCount RETURN nodeCount""",
    # Cypher-aggregation projection (GDS >= 2.4): one undirected edge per co-author pair,
    # weighted by the number of shared papers; OPTIONAL MATCH keeps solo authors.
    "rg_collaboration": """
        MATCH (a:Author)
        OPTIONAL MATCH (a)-[:WROTE]->(p:Paper)<-[:WROTE]-(b:Author) WHERE a.id < b.id
        WITH a, b, count(DISTINCT p) AS shared
        WITH gds.graph.project('rg_collaboration', a, b,
                               {relationshipProperties: {weight: toFloat(shared)}},
                               {undirectedRelationshipTypes: ['*']}) AS g
        RETURN g.nodeCount AS nodeCount""",
}

_GDS_DROP = "CALL gds.graph.drop($name, false) YIELD graphName RETURN graphName"

_GDS_PAGERANK: dict[str, LiteralString] = {
    "rg_citations": """
        CALL gds.pageRank.stream('rg_citations', {dampingFactor: 0.85, maxIterations: 200})
        YIELD nodeId, score RETURN gds.util.asNode(nodeId).id AS id, score""",
    "rg_collaboration": """
        CALL gds.pageRank.stream('rg_collaboration',
                                 {dampingFactor: 0.85, maxIterations: 200,
                                  relationshipWeightProperty: 'weight'})
        YIELD nodeId, score RETURN gds.util.asNode(nodeId).id AS id, score""",
}

_GDS_BETWEENNESS: dict[str, LiteralString] = {
    "rg_citations_undirected": """
        CALL gds.betweenness.stream('rg_citations_undirected', $config)
        YIELD nodeId, score RETURN gds.util.asNode(nodeId).id AS id, score""",
    "rg_collaboration": """
        CALL gds.betweenness.stream('rg_collaboration', $config)
        YIELD nodeId, score RETURN gds.util.asNode(nodeId).id AS id, score""",
}

_GDS_COMMUNITIES: dict[tuple[str, str], LiteralString] = {
    ("rg_citations_undirected", "louvain"): """
        CALL gds.louvain.stream('rg_citations_undirected', {concurrency: 1})
        YIELD nodeId, communityId RETURN gds.util.asNode(nodeId).id AS id, communityId""",
    ("rg_citations_undirected", "leiden"): """
        CALL gds.leiden.stream('rg_citations_undirected', {randomSeed: 42})
        YIELD nodeId, communityId RETURN gds.util.asNode(nodeId).id AS id, communityId""",
    ("rg_collaboration", "louvain"): """
        CALL gds.louvain.stream('rg_collaboration',
                                {concurrency: 1, relationshipWeightProperty: 'weight'})
        YIELD nodeId, communityId RETURN gds.util.asNode(nodeId).id AS id, communityId""",
    ("rg_collaboration", "leiden"): """
        CALL gds.leiden.stream('rg_collaboration',
                               {randomSeed: 42, relationshipWeightProperty: 'weight'})
        YIELD nodeId, communityId RETURN gds.util.asNode(nodeId).id AS id, communityId""",
}

_GDS_PPR = """
MATCH (s:Paper) WHERE s.id IN $sources
WITH collect(s) AS sources
CALL gds.pageRank.stream('rg_citations_undirected',
                         {sourceNodes: sources, dampingFactor: 0.85, maxIterations: 100})
YIELD nodeId, score
WITH gds.util.asNode(nodeId) AS node, score
WHERE NOT node.id IN $sources AND score > 0
RETURN node.id AS id, score ORDER BY score DESC, id LIMIT $limit
"""

_GDS_VERSION = "RETURN gds.version() AS version"


def _normalise_communities(raw: dict[str, int]) -> dict[str, int]:
    """Re-index GDS community IDs by size so both backends produce comparable output."""
    groups: dict[int, list[str]] = {}
    for node, community in raw.items():
        groups.setdefault(community, []).append(node)
    ordered = sorted((sorted(m) for m in groups.values()), key=lambda m: (-len(m), m[0]))
    return {node: index for index, members in enumerate(ordered) for node in members}


class GdsBackend:
    name = "gds"

    def __init__(self, graph: GraphClient) -> None:
        self._graph = graph
        self._projected: set[str] = set()

    async def _ensure(self, name: str) -> None:
        if name in self._projected:
            return
        await self._graph.write(_GDS_DROP, {"name": name}, label="gds.drop")
        await self._graph.write(_GDS_PROJECTIONS[name], label=f"gds.project.{name}")
        self._projected.add(name)

    @staticmethod
    def _names(kind: GraphKind) -> tuple[str, str]:
        """(directed-or-weighted projection, undirected projection) for a graph kind."""
        if kind == "citations":
            return "rg_citations", "rg_citations_undirected"
        return "rg_collaboration", "rg_collaboration"

    async def pagerank(self, kind: GraphKind) -> dict[str, float]:
        name, _ = self._names(kind)
        await self._ensure(name)
        rows = await self._graph.read(_GDS_PAGERANK[name], label="gds.pagerank")
        return {r["id"]: float(r["score"]) for r in rows}

    async def betweenness(self, kind: GraphKind, sample_size: int | None) -> dict[str, float]:
        _, name = self._names(kind)
        await self._ensure(name)
        config: dict[str, object] = {}
        if sample_size is not None:
            config = {"samplingSize": sample_size, "samplingSeed": 42}
        rows = await self._graph.read(
            _GDS_BETWEENNESS[name], {"config": config}, label="gds.betweenness"
        )
        raw = {r["id"]: float(r["score"]) for r in rows}
        # GDS streams unnormalised scores. Scale by 1/((n-1)(n-2)) so values are in a
        # comparable range; absolute values may still differ from NetworkX by a constant
        # factor depending on how undirected pairs are counted. Rankings are unaffected,
        # and only rankings are used downstream.
        n = len(raw)
        scale = 1.0 / ((n - 1) * (n - 2)) if n > 2 else 1.0
        return {k: v * scale for k, v in raw.items()}

    async def communities(self, kind: GraphKind, algorithm: CommunityAlgorithm) -> dict[str, int]:
        _, name = self._names(kind)
        await self._ensure(name)
        rows = await self._graph.read(_GDS_COMMUNITIES[(name, algorithm)], label=f"gds.{algorithm}")
        return _normalise_communities({r["id"]: int(r["communityId"]) for r in rows})

    async def personalized_pagerank(self, sources: list[str], limit: int) -> dict[str, float]:
        await self._ensure("rg_citations_undirected")
        rows = await self._graph.read(
            _GDS_PPR, {"sources": sources, "limit": limit}, label="gds.ppr"
        )
        return {r["id"]: float(r["score"]) for r in rows}

    async def close(self) -> None:
        for name in sorted(self._projected):
            await self._graph.write(_GDS_DROP, {"name": name}, label="gds.drop")
        self._projected.clear()


async def gds_available(graph: GraphClient) -> bool:
    try:
        await graph.read(_GDS_VERSION, label="gds.version")
    except ClientError:
        return False
    return True


async def select_backend(graph: GraphClient, preference: str = "auto") -> AnalyticsBackend:
    if preference == "networkx":
        return NetworkXBackend(graph)
    if preference == "gds":
        return GdsBackend(graph)
    backend: AnalyticsBackend = (
        GdsBackend(graph) if await gds_available(graph) else NetworkXBackend(graph)
    )
    log.info("analytics.backend_selected", backend=backend.name)
    return backend
