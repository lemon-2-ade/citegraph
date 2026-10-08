"""Keyword, semantic and hybrid paper search.

Hybrid ranking uses reciprocal rank fusion: BM25 scores (Lucene) and cosine similarities are
on different scales, so results are merged by *rank*, not by adding scores.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

from neo4j.exceptions import ClientError

from app.ai.embeddings import EmbedderCache, EmbeddingProvider
from app.core.errors import DependencyUnavailableError
from app.core.logging import get_logger
from app.graph.client import GraphClient
from app.repositories.embeddings import EmbeddingRepository, SemanticUnavailableError
from app.repositories.search import SearchRepository, to_lucene
from app.schemas.analytics import SimilarPaper
from app.schemas.graph import PaperHit, PaperSearchResults, PaperSummary

log = get_logger(__name__)

SearchMode = Literal["keyword", "semantic", "hybrid"]
RRF_K = 60  # standard constant from the original RRF paper; damps the top ranks
CANDIDATES = 50


def reciprocal_rank_fusion(
    rankings: Mapping[str, Sequence[str]], k: int = RRF_K
) -> list[tuple[str, float]]:
    """Merge ranked id lists: score(id) = sum over lists of 1 / (k + rank), rank from 1."""
    scores: dict[str, float] = {}
    for ids in rankings.values():
        for rank, item in enumerate(ids, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))


def _summary(row: Mapping[str, Any]) -> PaperSummary:
    return PaperSummary.model_validate({k: v for k, v in row.items() if k != "score"})


async def _semantic_rows(
    graph: GraphClient, provider: EmbeddingProvider, query: str, k: int
) -> list[dict[str, Any]]:
    repo = EmbeddingRepository(graph)
    config = await repo.config()
    if config is None:
        raise SemanticUnavailableError(
            "Semantic search is not set up yet. Run `researchgraph embed` first."
        )
    if config["model"] != provider.model or int(config["dimensions"]) != provider.dimensions:
        raise SemanticUnavailableError(
            f"Papers are embedded with {config['model']!r} but the server is configured for "
            f"{provider.model!r}. Run `researchgraph embed --rebuild`."
        )
    (vector,) = await provider.embed([query])
    try:
        return await repo.search(vector, k)
    except ClientError as exc:
        log.warning("semantic.query_failed", code=exc.code)
        raise SemanticUnavailableError(
            "The vector index is missing or does not match the model. "
            "Run `researchgraph embed --rebuild`."
        ) from exc


async def search_papers(
    graph: GraphClient,
    embedder: EmbedderCache | None,
    query: str,
    mode: SearchMode,
    limit: int,
) -> PaperSearchResults:
    text = query.strip()
    results = PaperSearchResults(query=text, mode=mode)
    if len(text) < 2:
        return results

    keyword_rows: list[dict[str, Any]] = []
    semantic_rows: list[dict[str, Any]] = []
    note: str | None = None

    if mode in {"keyword", "hybrid"} and to_lucene(text) is not None:
        keyword_rows = await SearchRepository(graph).keyword_papers(text, CANDIDATES)

    if mode in {"semantic", "hybrid"}:
        try:
            if embedder is None:
                raise SemanticUnavailableError("No embedding provider is configured.")
            provider = await embedder.get()
            semantic_rows = await _semantic_rows(graph, provider, text, CANDIDATES)
        except (SemanticUnavailableError, DependencyUnavailableError) as exc:
            if mode == "semantic":
                raise
            # Hybrid degrades to keyword search rather than failing the whole request.
            note = f"Semantic search is unavailable: {exc.message} Showing keyword matches only."
            results.semantic_available = False

    keyword_ids = [r["id"] for r in keyword_rows]
    semantic_ids = [r["id"] for r in semantic_rows]
    rows = {r["id"]: r for r in (*semantic_rows, *keyword_rows)}

    if mode == "keyword":
        ranked = [(i, float(rows[i]["score"])) for i in keyword_ids]
    elif mode == "semantic":
        ranked = [(i, float(rows[i]["score"])) for i in semantic_ids]
    else:
        ranked = reciprocal_rank_fusion({"keyword": keyword_ids, "semantic": semantic_ids})

    for paper_id, score in ranked[:limit]:
        matched: list[Literal["keyword", "semantic"]] = []
        if paper_id in keyword_ids:
            matched.append("keyword")
        if paper_id in semantic_ids:
            matched.append("semantic")
        results.hits.append(
            PaperHit(
                paper=_summary(rows[paper_id]),
                score=score,
                matched_by=matched,
                keyword_rank=keyword_ids.index(paper_id) + 1 if paper_id in keyword_ids else None,
                semantic_rank=(
                    semantic_ids.index(paper_id) + 1 if paper_id in semantic_ids else None
                ),
            )
        )
    results.note = note
    return results


async def semantic_similar(graph: GraphClient, paper_id: str, limit: int) -> list[SimilarPaper]:
    """Nearest neighbours of a paper's stored vector (no embedding call needed)."""
    repo = EmbeddingRepository(graph)
    try:
        rows = await repo.similar_to(paper_id, limit)
    except ClientError as exc:
        log.warning("semantic.similar_failed", code=exc.code)
        raise SemanticUnavailableError(
            "Semantic search is not set up yet. Run `researchgraph embed` first."
        ) from exc
    return [
        SimilarPaper(
            paper=_summary(r),
            method="semantic",
            score=float(r["score"]),
            explanation=f"Similar title and abstract (cosine similarity {float(r['score']):.2f})",
        )
        for r in rows
    ]
