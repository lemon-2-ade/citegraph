from __future__ import annotations

from typing import Any, LiteralString

from app.core.errors import NotFoundError
from app.graph.client import GraphClient
from app.repositories.papers import SUMMARY

_TOPIC: LiteralString = "MATCH (t:Topic {id: $id}) RETURN t.name AS name"
_PAPER: LiteralString = "MATCH (p:Paper {id: $id}) RETURN p.title AS title"

_TOPIC_CANDIDATES: LiteralString = (
    """
MATCH (p:Paper)-[:HAS_TOPIC]->(:Topic {id: $id})
WHERE coalesce(p.is_stub, false) = false
WITH DISTINCT p
ORDER BY coalesce(p.pagerank, 0.0) DESC, p.id
LIMIT $limit
RETURN"""
    + SUMMARY
)

_PAPER_CANDIDATES: LiteralString = (
    """
MATCH (s:Paper {id: $id})
OPTIONAL MATCH (s)-[:CITES*1..2]-(n:Paper)
WHERE coalesce(n.is_stub, false) = false
WITH s, collect(DISTINCT n) AS near
UNWIND (near + [s]) AS p
WITH DISTINCT p
ORDER BY coalesce(p.pagerank, 0.0) DESC, p.id
LIMIT $limit
RETURN"""
    + SUMMARY
)

_EDGES: LiteralString = """
MATCH (a:Paper)-[:CITES]->(b:Paper)
WHERE a.id IN $ids AND b.id IN $ids
RETURN a.id AS source, b.id AS target
"""


class PathRepository:
    def __init__(self, graph: GraphClient) -> None:
        self._graph = graph

    async def topic_name(self, topic_id: str) -> str:
        rows = await self._graph.read(_TOPIC, {"id": topic_id}, label="paths.topic")
        if not rows:
            raise NotFoundError(f"Topic {topic_id!r} not found")
        return str(rows[0]["name"])

    async def paper_title(self, paper_id: str) -> str:
        rows = await self._graph.read(_PAPER, {"id": paper_id}, label="paths.paper")
        if not rows:
            raise NotFoundError(f"Paper {paper_id!r} not found")
        return str(rows[0]["title"] or paper_id)

    async def candidates_for_topic(self, topic_id: str, limit: int) -> list[dict[str, Any]]:
        return await self._graph.read(
            _TOPIC_CANDIDATES, {"id": topic_id, "limit": limit}, label="paths.topic_candidates"
        )

    async def candidates_near_paper(self, paper_id: str, limit: int) -> list[dict[str, Any]]:
        return await self._graph.read(
            _PAPER_CANDIDATES, {"id": paper_id, "limit": limit}, label="paths.paper_candidates"
        )

    async def edges(self, ids: list[str]) -> list[tuple[str, str]]:
        if len(ids) < 2:
            return []
        rows = await self._graph.read(_EDGES, {"ids": ids}, label="paths.edges")
        return [(r["source"], r["target"]) for r in rows]
