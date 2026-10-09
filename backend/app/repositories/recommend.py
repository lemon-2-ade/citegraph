from __future__ import annotations

from collections.abc import Sequence
from typing import LiteralString

from app.graph.client import GraphClient

_LINKED: LiteralString = """
MATCH (s:Paper)-[:CITES]-(c:Paper)
WHERE s.id IN $seeds AND c.id IN $candidates
RETURN c.id AS candidate, collect(DISTINCT s.id) AS seeds
"""


class RecommendRepository:
    def __init__(self, graph: GraphClient) -> None:
        self._graph = graph

    async def linked_seeds(
        self, seeds: Sequence[str], candidates: Sequence[str]
    ) -> dict[str, list[str]]:
        """For each candidate, which reading-list papers it cites or is cited by."""
        if not candidates:
            return {}
        rows = await self._graph.read(
            _LINKED,
            {"seeds": list(seeds), "candidates": list(candidates)},
            label="recommend.linked",
        )
        return {r["candidate"]: list(r["seeds"]) for r in rows}
