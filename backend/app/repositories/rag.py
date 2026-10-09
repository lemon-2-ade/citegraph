"""Graph queries for retrieval-augmented answering."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, LiteralString

from app.graph.client import GraphClient
from app.repositories.papers import SUMMARY

_PASSAGES: LiteralString = (
    """
MATCH (p:Paper) WHERE p.id IN $ids
RETURN"""
    + SUMMARY
    + """, p.abstract AS abstract, p.description AS description
"""
)

# Papers one citation hop from the retrieved set, ranked by how many retrieved papers they
# touch (in either direction) and then by PageRank. Stubs and papers without text are skipped
# because there is nothing to quote.
_EXPAND: LiteralString = (
    """
MATCH (s:Paper) WHERE s.id IN $seeds
MATCH (s)-[:CITES]-(p:Paper)
WHERE NOT p.id IN $seeds AND coalesce(p.is_stub, false) = false
  AND (p.abstract IS NOT NULL OR p.description IS NOT NULL)
WITH p, count(DISTINCT s) AS links
ORDER BY links DESC, coalesce(p.pagerank, 0.0) DESC, p.id
LIMIT $limit
RETURN"""
    + SUMMARY
    + """, p.abstract AS abstract, p.description AS description, links
"""
)

_RELATIONS: LiteralString = """
MATCH (a:Paper)-[:CITES]->(b:Paper)
WHERE a.id IN $ids AND b.id IN $ids
RETURN a.id AS source, b.id AS target
"""


class RagRepository:
    def __init__(self, graph: GraphClient) -> None:
        self._graph = graph

    async def passages(self, ids: Sequence[str]) -> dict[str, dict[str, Any]]:
        rows = await self._graph.read(_PASSAGES, {"ids": list(ids)}, label="rag.passages")
        return {r["id"]: r for r in rows}

    async def expand(self, seeds: Sequence[str], limit: int) -> list[dict[str, Any]]:
        if not seeds or limit <= 0:
            return []
        return await self._graph.read(
            _EXPAND, {"seeds": list(seeds), "limit": limit}, label="rag.expand"
        )

    async def relations(self, ids: Sequence[str]) -> list[dict[str, Any]]:
        if len(ids) < 2:
            return []
        return await self._graph.read(_RELATIONS, {"ids": list(ids)}, label="rag.relations")
