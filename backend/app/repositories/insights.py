"""Cached LLM paper insights stored as a JSON string on the Paper node."""

from __future__ import annotations

from typing import Any, LiteralString

from app.core.errors import NotFoundError
from app.graph.client import GraphClient

_GET: LiteralString = """
MATCH (p:Paper {id: $id})
RETURN p.id AS id, p.title AS title, p.abstract AS abstract, p.description AS description,
       p.insight_json AS insight_json, p.insight_hash AS hash, p.insight_model AS model,
       p.insight_at AS generated_at
"""

_STORE: LiteralString = """
MATCH (p:Paper {id: $id})
SET p.insight_json = $json, p.insight_hash = $hash, p.insight_model = $model,
    p.insight_at = toString(datetime())
RETURN p.insight_at AS generated_at
"""

_CANDIDATES: LiteralString = """
MATCH (p:Paper)
WHERE coalesce(p.is_stub, false) = false AND p.id > $after
RETURN p.id AS id, p.title AS title, p.abstract AS abstract, p.description AS description,
       p.insight_hash AS hash
ORDER BY p.id
LIMIT $limit
"""

_COUNT: LiteralString = "MATCH (p:Paper) WHERE p.insight_json IS NOT NULL RETURN count(p) AS n"


class InsightRepository:
    def __init__(self, graph: GraphClient) -> None:
        self._graph = graph

    async def get(self, paper_id: str) -> dict[str, Any]:
        rows = await self._graph.read(_GET, {"id": paper_id}, label="insights.get")
        if not rows:
            raise NotFoundError(f"Paper {paper_id!r} not found")
        return rows[0]

    async def store(self, paper_id: str, *, json: str, hash: str, model: str) -> str:
        rows = await self._graph.write(
            _STORE, {"id": paper_id, "json": json, "hash": hash, "model": model},
            label="insights.store",
        )  # fmt: skip
        return str(rows[0]["generated_at"]) if rows else ""

    async def candidates(self, after: str, limit: int) -> list[dict[str, Any]]:
        return await self._graph.read(
            _CANDIDATES, {"after": after, "limit": limit}, label="insights.candidates"
        )

    async def count(self) -> int:
        rows = await self._graph.read(_COUNT, label="insights.count")
        return int(rows[0]["n"]) if rows else 0
