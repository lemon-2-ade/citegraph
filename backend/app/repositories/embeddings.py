"""Paper embeddings in Neo4j: vector index, bookkeeping and nearest-neighbour queries.

Vectors live on ``Paper.embedding`` with a native vector index (HNSW). A single
``(:EmbeddingConfig {id: 'paper'})`` node records which model produced them, because vectors
from different models cannot be compared even when their sizes match.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, LiteralString

from app.core.errors import NotFoundError, ResearchGraphError
from app.graph.client import GraphClient
from app.repositories.papers import SUMMARY

INDEX_NAME = "paper_embedding"


class SemanticUnavailableError(ResearchGraphError):
    status_code = 409
    code = "semantic_unavailable"


_CONFIG_GET: LiteralString = """
MATCH (c:EmbeddingConfig {id: 'paper'})
RETURN c.model AS model, c.dimensions AS dimensions, c.provider AS provider,
       c.updated_at AS updated_at
"""

_CONFIG_SET: LiteralString = """
MERGE (c:EmbeddingConfig {id: 'paper'})
SET c.model = $model, c.dimensions = $dimensions, c.provider = $provider,
    c.updated_at = toString(datetime())
"""

_CONFIG_CLEAR: LiteralString = "MATCH (c:EmbeddingConfig {id: 'paper'}) DETACH DELETE c"

_INDEX_DIMENSIONS: LiteralString = """
SHOW VECTOR INDEXES YIELD name, options
WHERE name = $name
RETURN options.indexConfig['vector.dimensions'] AS dimensions
"""

_DROP_INDEX: LiteralString = "DROP INDEX paper_embedding IF EXISTS"

_CLEAR_VECTORS: LiteralString = """
MATCH (p:Paper) WHERE p.embedding IS NOT NULL
REMOVE p.embedding, p.embedding_model, p.embedding_hash
"""

_CANDIDATES: LiteralString = """
MATCH (p:Paper)
WHERE coalesce(p.is_stub, false) = false AND p.id > $after
RETURN p.id AS id, p.title AS title, p.abstract AS abstract, p.description AS description,
       p.embedding_hash AS hash, p.embedding_model AS model,
       p.embedding IS NOT NULL AS has_vector
ORDER BY p.id
LIMIT $limit
"""

_STORE: LiteralString = """
UNWIND $rows AS row
MATCH (p:Paper {id: row.id})
CALL db.create.setNodeVectorProperty(p, 'embedding', row.vector)
SET p.embedding_model = $model, p.embedding_hash = row.hash
"""

_COUNT_EMBEDDED: LiteralString = """
MATCH (p:Paper) WHERE p.embedding IS NOT NULL RETURN count(p) AS embedded
"""

_SEMANTIC: LiteralString = (
    """
CALL db.index.vector.queryNodes('paper_embedding', $k, $vector) YIELD node AS p, score
WHERE coalesce(p.is_stub, false) = false
RETURN"""
    + SUMMARY
    + """, score
ORDER BY score DESC, id
"""
)

_SIMILAR: LiteralString = (
    """
MATCH (s:Paper {id: $id})
WHERE s.embedding IS NOT NULL
CALL db.index.vector.queryNodes('paper_embedding', $k, s.embedding) YIELD node AS p, score
WHERE p <> s AND coalesce(p.is_stub, false) = false
RETURN"""
    + SUMMARY
    + """, score
ORDER BY score DESC, id
LIMIT $limit
"""
)

_VECTORS: LiteralString = """
MATCH (p:Paper) WHERE p.id IN $ids AND p.embedding IS NOT NULL
RETURN p.id AS id, p.embedding AS vector
"""

_PAPER_EXISTS: LiteralString = "MATCH (p:Paper {id: $id}) RETURN p.id AS id"


def index_ddl(dimensions: int) -> LiteralString:
    """``CREATE VECTOR INDEX`` for a given size (DDL cannot take parameters)."""
    if not 1 <= dimensions <= 4096:
        raise ValueError(f"unsupported embedding size: {dimensions}")
    return (
        f"CREATE VECTOR INDEX {INDEX_NAME} IF NOT EXISTS FOR (p:Paper) ON (p.embedding) "
        f"OPTIONS {{indexConfig: {{`vector.dimensions`: {int(dimensions)}, "
        "`vector.similarity_function`: 'cosine'}}"
    )


class EmbeddingRepository:
    def __init__(self, graph: GraphClient) -> None:
        self._graph = graph

    async def config(self) -> dict[str, Any] | None:
        rows = await self._graph.read(_CONFIG_GET, label="embeddings.config")
        return rows[0] if rows else None

    async def set_config(self, *, model: str, dimensions: int, provider: str) -> None:
        await self._graph.write(
            _CONFIG_SET,
            {"model": model, "dimensions": dimensions, "provider": provider},
            label="embeddings.set_config",
        )

    async def index_dimensions(self) -> int | None:
        rows = await self._graph.read(
            _INDEX_DIMENSIONS, {"name": INDEX_NAME}, label="embeddings.index_dimensions"
        )
        return int(rows[0]["dimensions"]) if rows and rows[0]["dimensions"] else None

    async def ensure_index(self, dimensions: int) -> None:
        existing = await self.index_dimensions()
        if existing is not None and existing != dimensions:
            raise SemanticUnavailableError(
                f"The vector index has {existing} dimensions but the configured model "
                f"produces {dimensions}. Run `researchgraph embed --rebuild`."
            )
        await self._graph.write(index_ddl(dimensions), label="embeddings.ensure_index")

    async def reset(self) -> None:
        """Drop the index, all stored vectors and the config (for a model change)."""
        await self._graph.write(_DROP_INDEX, label="embeddings.drop_index")
        await self._graph.write(_CLEAR_VECTORS, label="embeddings.clear_vectors")
        await self._graph.write(_CONFIG_CLEAR, label="embeddings.clear_config")

    async def candidates(self, after: str, limit: int) -> list[dict[str, Any]]:
        return await self._graph.read(
            _CANDIDATES, {"after": after, "limit": limit}, label="embeddings.candidates"
        )

    async def store(self, rows: Sequence[dict[str, Any]], model: str) -> None:
        if rows:
            await self._graph.write(
                _STORE, {"rows": list(rows), "model": model}, label="embeddings.store"
            )

    async def embedded_count(self) -> int:
        rows = await self._graph.read(_COUNT_EMBEDDED, label="embeddings.count")
        return int(rows[0]["embedded"]) if rows else 0

    async def search(self, vector: Sequence[float], k: int) -> list[dict[str, Any]]:
        return await self._graph.read(
            _SEMANTIC, {"k": k, "vector": list(vector)}, label="embeddings.search"
        )

    async def vectors(self, ids: Sequence[str]) -> dict[str, list[float]]:
        rows = await self._graph.read(_VECTORS, {"ids": list(ids)}, label="embeddings.vectors")
        return {r["id"]: [float(x) for x in r["vector"]] for r in rows}

    async def similar_to(self, paper_id: str, limit: int) -> list[dict[str, Any]]:
        if not await self._graph.read(_PAPER_EXISTS, {"id": paper_id}, label="embeddings.exists"):
            raise NotFoundError(f"Paper {paper_id!r} not found")
        return await self._graph.read(
            _SIMILAR, {"id": paper_id, "k": limit + 1, "limit": limit}, label="embeddings.similar"
        )
