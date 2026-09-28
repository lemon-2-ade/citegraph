"""Shared fixtures.

Integration tests talk to real services and are skipped unless the relevant
environment variables are set, e.g. with the Docker Compose stack running::

    RG_TEST_NEO4J_URI=bolt://localhost:7687 RG_TEST_NEO4J_PASSWORD=... \
    RG_TEST_DATABASE_URL=postgresql+asyncpg://user:pw@localhost:5432/db \
    uv run pytest -m integration

Integration tests WIPE the target databases — never point them at real data.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest

from app.core.config import Settings
from app.graph.client import GraphClient


@pytest.fixture
async def neo4j_graph() -> AsyncIterator[GraphClient]:
    uri = os.environ.get("RG_TEST_NEO4J_URI")
    if not uri:
        pytest.skip("RG_TEST_NEO4J_URI not set")
    settings = Settings(
        neo4j_uri=uri,
        neo4j_user=os.environ.get("RG_TEST_NEO4J_USER", "neo4j"),
        neo4j_password=os.environ.get("RG_TEST_NEO4J_PASSWORD", ""),  # type: ignore[arg-type]
    )
    graph = GraphClient.from_settings(settings)
    await graph.write("MATCH (n) DETACH DELETE n", label="test.wipe")
    try:
        yield graph
    finally:
        await graph.close()
