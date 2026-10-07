"""Bounded subgraphs for visualisation (read-only, parameterised, size-capped)."""

from __future__ import annotations

from typing import Any, LiteralString

from app.core.errors import NotFoundError
from app.graph.client import GraphClient
from app.schemas.graph import GraphEdge, GraphNode, GraphView

MAX_NODES = 300
MAX_NEIGHBOUR_DEPTH = 2
# At depth 2, expand only from this many first-hop papers so a heavily cited hub cannot
# make the expansion explode.
DEPTH2_FANOUT = 25

_NODE_PROJECTION: LiteralString = """
    p.id AS id, p.title AS title, p.year AS year, p.pagerank AS pagerank,
    COUNT { (:Paper)-[:CITES]->(p) } AS cited_by_in_graph,
    p.community_id AS community_id,
    COLLECT { MATCH (p)-[:IN_COMMUNITY]->(c:Community) RETURN c.label LIMIT 1 }[0]
        AS community_label,
    coalesce(p.is_stub, false) AS is_stub,
    COLLECT {
        MATCH (a:Author)-[w:WROTE]->(p) RETURN a.name ORDER BY w.position LIMIT 3
    } AS authors
"""

_TOP_PAPER_IDS: LiteralString = """
MATCH (p:Paper)
WHERE coalesce(p.is_stub, false) = false
WITH p
ORDER BY coalesce(p.pagerank, 0.0) DESC, COUNT { (:Paper)-[:CITES]->(p) } DESC, p.id
LIMIT $limit
RETURN p.id AS id
"""

_PAPER_COUNT: LiteralString = """
MATCH (p:Paper) WHERE coalesce(p.is_stub, false) = false
RETURN count(p) AS total
"""

_PAPER_EXISTS: LiteralString = "MATCH (p:Paper {id: $id}) RETURN p.id AS id"

_NEIGHBOUR_IDS: LiteralString = """
MATCH (s:Paper)-[:CITES]-(n:Paper)
WHERE s.id IN $seeds AND NOT n.id IN $exclude
WITH DISTINCT n
ORDER BY coalesce(n.pagerank, 0.0) DESC, n.id
LIMIT $limit
RETURN n.id AS id
"""

_NODES_BY_ID: LiteralString = (
    """
MATCH (p:Paper) WHERE p.id IN $ids
RETURN"""
    + _NODE_PROJECTION
)

_EDGES_AMONG: LiteralString = """
MATCH (a:Paper)-[:CITES]->(b:Paper)
WHERE a.id IN $ids AND b.id IN $ids
RETURN a.id AS source, b.id AS target
"""


class GraphViewRepository:
    def __init__(self, graph: GraphClient) -> None:
        self._graph = graph

    async def overview(self, limit: int) -> GraphView:
        """The most structurally influential papers and the citations among them."""
        limit = max(1, min(limit, MAX_NODES))
        total_rows = await self._graph.read(_PAPER_COUNT, label="graph.overview.count")
        total = int(total_rows[0]["total"]) if total_rows else 0
        rows = await self._graph.read(_TOP_PAPER_IDS, {"limit": limit}, label="graph.overview.ids")
        ids = [str(r["id"]) for r in rows]
        view = await self._assemble(ids, focus=None, order=ids)
        view.total_papers = total
        view.truncated = total > len(ids)
        view.note = (
            f"The {len(ids)} papers with the highest PageRank in this graph"
            + (f" (of {total})" if total > len(ids) else "")
            + ", and the citations among them. PageRank is structural influence within the "
            "ingested graph, not a measure of research quality."
        )
        return view

    async def neighbourhood(self, paper_id: str, depth: int, limit: int) -> GraphView:
        """A paper, the papers it cites or is cited by, and (depth 2) their neighbours."""
        depth = max(1, min(depth, MAX_NEIGHBOUR_DEPTH))
        limit = max(2, min(limit, MAX_NODES))
        exists = await self._graph.read(_PAPER_EXISTS, {"id": paper_id}, label="graph.nb.exists")
        if not exists:
            raise NotFoundError(f"Paper {paper_id!r} not found")

        room = limit - 1  # the focus paper takes one slot
        first = await self._neighbour_ids([paper_id], [paper_id], room + 1)
        truncated = len(first) > room
        first = first[:room]
        ids = [paper_id, *first]

        if depth >= 2 and first and len(ids) < limit:
            remaining = limit - len(ids)
            second = await self._neighbour_ids(first[:DEPTH2_FANOUT], list(ids), remaining + 1)
            truncated = truncated or len(second) > remaining
            ids.extend(second[:remaining])

        view = await self._assemble(ids, focus=paper_id, order=ids)
        view.truncated = truncated
        view.note = (
            f"Citation neighbourhood of this paper to depth {depth}: papers that cite it or are "
            "cited by it"
            + (" and their neighbours" if depth >= 2 else "")
            + ". Papers are ranked by PageRank when the view must be trimmed"
            + (f" to {limit}." if truncated else ".")
        )
        return view

    async def _neighbour_ids(self, seeds: list[str], exclude: list[str], limit: int) -> list[str]:
        rows = await self._graph.read(
            _NEIGHBOUR_IDS,
            {"seeds": seeds, "exclude": exclude, "limit": limit},
            label="graph.nb.neighbours",
        )
        return [str(r["id"]) for r in rows]

    async def _assemble(self, ids: list[str], focus: str | None, order: list[str]) -> GraphView:
        if not ids:
            return GraphView(nodes=[], edges=[], focus=focus, note="No papers to show.")
        node_rows: list[dict[str, Any]] = await self._graph.read(
            _NODES_BY_ID, {"ids": ids}, label="graph.nodes"
        )
        by_id = {str(r["id"]): GraphNode.model_validate(r) for r in node_rows}
        nodes = [by_id[i] for i in order if i in by_id]  # keep ranking order, focus first
        edge_rows = await self._graph.read(_EDGES_AMONG, {"ids": ids}, label="graph.edges")
        edges = [
            GraphEdge(source=str(r["source"]), target=str(r["target"]))
            for r in edge_rows
            if r["source"] in by_id and r["target"] in by_id
        ]
        return GraphView(nodes=nodes, edges=edges, focus=focus, note="")
