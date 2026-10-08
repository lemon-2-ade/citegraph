"""Vector index, embedding and semantic search against a real Neo4j (seed dataset)."""

import pytest

from app.ai.embeddings import EmbedderCache, HashingEmbeddings
from app.core.config import Settings
from app.graph.client import GraphClient
from app.graph.schema import apply_schema
from app.ingestion.seed import seed_graph
from app.repositories.embeddings import EmbeddingRepository, SemanticUnavailableError
from app.services.embedding import embed_papers
from app.services.paper_search import search_papers, semantic_similar

pytestmark = pytest.mark.integration


async def _embedded(graph: GraphClient) -> HashingEmbeddings:
    await apply_schema(graph)
    await seed_graph(graph)
    provider = HashingEmbeddings()
    stats = await embed_papers(graph, provider, batch_size=20)
    assert stats.embedded > 50
    await graph.write("CALL db.awaitIndex('paper_embedding', 60)", label="test.await_index")
    return provider


async def test_embedding_is_incremental_and_search_finds_relevant_papers(
    neo4j_graph: GraphClient,
) -> None:
    provider = await _embedded(neo4j_graph)
    again = await embed_papers(neo4j_graph, provider)
    assert again.embedded == 0 and again.unchanged > 50

    embedder = EmbedderCache(Settings(embedding_provider="hashing"), provider)
    semantic = await search_papers(
        neo4j_graph, embedder, "attention is all you need", "semantic", 5
    )
    assert any("Attention Is All You Need" in (h.paper.title or "") for h in semantic.hits)
    assert all(0.0 <= h.score <= 1.0 for h in semantic.hits)

    hybrid = await search_papers(neo4j_graph, embedder, "attention transformer", "hybrid", 10)
    assert hybrid.semantic_available and hybrid.hits
    assert any(len(h.matched_by) == 2 for h in hybrid.hits)  # both methods agree somewhere


async def test_similar_papers_use_the_stored_vector(neo4j_graph: GraphClient) -> None:
    await _embedded(neo4j_graph)
    rows = await neo4j_graph.read(
        "MATCH (p:Paper {title: 'Attention Is All You Need'}) RETURN p.id AS id", label="test.id"
    )
    similar = await semantic_similar(neo4j_graph, rows[0]["id"], 5)
    assert similar and all(s.paper.id != rows[0]["id"] for s in similar)
    assert [s.score for s in similar] == sorted((s.score for s in similar), reverse=True)


async def test_changing_model_requires_a_rebuild(neo4j_graph: GraphClient) -> None:
    provider = await _embedded(neo4j_graph)

    class Other(HashingEmbeddings):
        model = "other-model"
        dimensions = 64

    with pytest.raises(SemanticUnavailableError, match="--rebuild"):
        await embed_papers(neo4j_graph, Other())
    stats = await embed_papers(neo4j_graph, Other(), rebuild=True)
    assert stats.embedded > 50
    repo = EmbeddingRepository(neo4j_graph)
    assert (await repo.config() or {})["model"] == "other-model"
    assert await repo.index_dimensions() == 64

    # Queries from the old model are now refused instead of silently compared.
    old = EmbedderCache(Settings(embedding_provider="hashing"), provider)
    with pytest.raises(SemanticUnavailableError):
        await search_papers(neo4j_graph, old, "attention", "semantic", 3)
