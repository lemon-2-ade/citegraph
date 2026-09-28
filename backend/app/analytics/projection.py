"""Load graph projections from Neo4j into NetworkX."""

from __future__ import annotations

from typing import Literal

import networkx as nx

from app.graph.client import GraphClient

GraphKind = Literal["citations", "collaboration"]

_PAPER_NODES = "MATCH (p:Paper) RETURN p.id AS id"
_CITATION_EDGES = "MATCH (a:Paper)-[:CITES]->(b:Paper) RETURN a.id AS source, b.id AS target"
_AUTHOR_NODES = "MATCH (a:Author) RETURN a.id AS id"
_COLLABORATION_EDGES = """
MATCH (a:Author)-[:WROTE]->(p:Paper)<-[:WROTE]-(b:Author)
WHERE a.id < b.id
RETURN a.id AS source, b.id AS target, count(DISTINCT p) AS weight
"""

_NEIGHBOURHOOD_STEP = """
UNWIND $frontier AS id
MATCH (p:Paper {id: id})-[:CITES]-(q:Paper)
RETURN DISTINCT q.id AS id
LIMIT $limit
"""

_EDGES_AMONG = """
MATCH (a:Paper)-[:CITES]->(b:Paper)
WHERE a.id IN $ids AND b.id IN $ids
RETURN a.id AS source, b.id AS target
"""


async def load_citation_graph(graph: GraphClient) -> nx.DiGraph:
    g = nx.DiGraph()
    g.add_nodes_from(r["id"] for r in await graph.read(_PAPER_NODES, label="proj.papers"))
    g.add_edges_from(
        (r["source"], r["target"]) for r in await graph.read(_CITATION_EDGES, label="proj.cites")
    )
    return g


async def load_collaboration_graph(graph: GraphClient) -> nx.Graph:
    g = nx.Graph()
    g.add_nodes_from(r["id"] for r in await graph.read(_AUTHOR_NODES, label="proj.authors"))
    for r in await graph.read(_COLLABORATION_EDGES, label="proj.collab"):
        g.add_edge(r["source"], r["target"], weight=float(r["weight"]))
    return g


async def load_projection(graph: GraphClient, kind: GraphKind) -> nx.Graph | nx.DiGraph:
    if kind == "citations":
        return await load_citation_graph(graph)
    return await load_collaboration_graph(graph)


async def load_citation_neighbourhood(
    graph: GraphClient, seeds: list[str], *, hops: int = 2, max_nodes: int = 5000
) -> nx.DiGraph:
    """Citation subgraph within ``hops`` undirected steps of ``seeds`` (capped at max_nodes).

    Used for per-request computations (e.g. Personalized PageRank) so the whole graph is
    never loaded for one query.
    """
    nodes: set[str] = set(seeds)
    frontier = list(seeds)
    for _ in range(hops):
        if not frontier or len(nodes) >= max_nodes:
            break
        rows = await graph.read(
            _NEIGHBOURHOOD_STEP,
            {"frontier": frontier, "limit": max_nodes - len(nodes)},
            label="proj.neighbourhood",
        )
        frontier = [r["id"] for r in rows if r["id"] not in nodes]
        nodes.update(frontier)
    g = nx.DiGraph()
    g.add_nodes_from(nodes)
    g.add_edges_from(
        (r["source"], r["target"])
        for r in await graph.read(_EDGES_AMONG, {"ids": sorted(nodes)}, label="proj.edges_among")
    )
    return g
