"""Thin async wrapper around the Neo4j driver.

All graph access goes through :class:`GraphClient` so that
* reads run in managed *read* transactions (routed to read replicas in a cluster and
  unable to write — important once LLM-generated Cypher is executed in Phase 10),
* writes run in managed write transactions with automatic retry on transient errors,
* every query is timed and logged with a short, parameter-free label.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any, LiteralString

from neo4j import AsyncDriver, AsyncGraphDatabase, AsyncManagedTransaction, unit_of_work
from neo4j.exceptions import ServiceUnavailable

from app.core.config import Settings
from app.core.errors import DependencyUnavailableError
from app.core.logging import get_logger

log = get_logger(__name__)

Record = dict[str, Any]


class GraphClient:
    def __init__(self, driver: AsyncDriver, database: str) -> None:
        self._driver = driver
        self._database = database

    @classmethod
    def from_settings(cls, settings: Settings) -> GraphClient:
        driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
            max_connection_pool_size=settings.neo4j_max_pool_size,
        )
        return cls(driver, settings.neo4j_database)

    async def close(self) -> None:
        await self._driver.close()

    async def verify(self) -> None:
        try:
            await self._driver.verify_connectivity()
        except (ServiceUnavailable, OSError) as exc:
            raise DependencyUnavailableError(f"Neo4j is unavailable: {exc}") from exc

    async def read(
        self, query: LiteralString, params: Mapping[str, Any] | None = None, *, label: str = ""
    ) -> list[Record]:
        async def work(tx: AsyncManagedTransaction) -> list[Record]:
            result = await tx.run(query, dict(params or {}))
            return [record.data() async for record in result]

        return await self._timed("read", label, work)

    async def write(
        self, query: LiteralString, params: Mapping[str, Any] | None = None, *, label: str = ""
    ) -> list[Record]:
        async def work(tx: AsyncManagedTransaction) -> list[Record]:
            result = await tx.run(query, dict(params or {}))
            return [record.data() async for record in result]

        return await self._timed("write", label, work)

    async def run_readonly_unchecked(
        self,
        query: str,
        params: Mapping[str, Any] | None = None,
        *,
        label: str = "",
        tx_timeout: float | None = None,
    ) -> list[Record]:
        """Execute a dynamically built query in a READ transaction.

        Only for queries that were constructed or validated by trusted code (e.g. the
        Cypher validator). The read transaction is a second line of defence: Neo4j
        rejects writes inside it. ``tx_timeout`` (seconds) is enforced by the server.
        """

        async def work(tx: AsyncManagedTransaction) -> list[Record]:
            result = await tx.run(query, dict(params or {}))
            return [record.data() async for record in result]

        if tx_timeout is not None:
            work = unit_of_work(timeout=tx_timeout)(work)
        return await self._timed("read", label, work)

    async def query_type(self, query: str) -> str:
        """Neo4j's own classification of a query: "r", "w", "rw" or "s", via ``EXPLAIN``.

        Nothing is executed. Raises ``neo4j.exceptions.Neo4jError`` on a syntax error.
        """

        async def work(tx: AsyncManagedTransaction) -> str:
            result = await tx.run("EXPLAIN " + query)
            summary = await result.consume()
            return summary.query_type or ""

        try:
            async with self._driver.session(database=self._database) as session:
                query_type: str = await session.execute_read(work)
        except (ServiceUnavailable, OSError) as exc:
            raise DependencyUnavailableError(f"Neo4j is unavailable: {exc}") from exc
        return query_type

    async def _timed(self, mode: str, label: str, work: Any) -> list[Record]:
        start = time.perf_counter()
        try:
            async with self._driver.session(database=self._database) as session:
                if mode == "read":
                    records: list[Record] = await session.execute_read(work)
                else:
                    records = await session.execute_write(work)
        except (ServiceUnavailable, OSError) as exc:
            raise DependencyUnavailableError(f"Neo4j is unavailable: {exc}") from exc
        log.debug(
            "neo4j.query",
            mode=mode,
            label=label,
            rows=len(records),
            latency_ms=round((time.perf_counter() - start) * 1000, 2),
        )
        return records
