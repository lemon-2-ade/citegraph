"""Recommend papers from a reading list by combining graph and meaning signals.

* citation proximity: Personalized PageRank from all reading-list papers over their 2-hop
  citation neighbourhood (papers reachable through many short citation paths rank highest);
* similar meaning: embedding similarity to the centroid of the reading list.

The two rankings are merged by reciprocal rank fusion, because PageRank mass and cosine
similarity are not on comparable scales. Every recommendation carries the reasons it was
suggested, including which reading-list papers it is directly linked to.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from neo4j.exceptions import ClientError

from app.analytics.backends import NetworkXBackend
from app.analytics.queries import AnalyticsQueries
from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.graph.client import GraphClient
from app.repositories.embeddings import EmbeddingRepository
from app.repositories.recommend import RecommendRepository
from app.schemas.recommend import Reason, Recommendation, RecommendResponse
from app.services.paper_search import reciprocal_rank_fusion

log = get_logger(__name__)
POOL = 50


def centroid(vectors: Sequence[Sequence[float]]) -> list[float]:
    """Mean of unit-normalised vectors, re-normalised (cosine geometry)."""
    if not vectors:
        return []
    size = len(vectors[0])
    total = [0.0] * size
    for v in vectors:
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        for i, x in enumerate(v):
            total[i] += x / norm
    norm = math.sqrt(sum(x * x for x in total)) or 1.0
    return [x / norm for x in total]


async def recommend_papers(
    graph: GraphClient, paper_ids: Sequence[str], limit: int
) -> RecommendResponse:
    seed_ids = list(dict.fromkeys(paper_ids))
    queries = AnalyticsQueries(graph)
    summaries = await queries.paper_summaries(seed_ids)
    missing = [i for i in seed_ids if i not in summaries]
    if missing:
        raise NotFoundError(f"Paper(s) not found: {', '.join(missing[:5])}")
    seed_set = set(seed_ids)
    response = RecommendResponse(seeds=[summaries[i] for i in seed_ids])

    graph_scores = await NetworkXBackend(graph).personalized_pagerank(seed_ids, POOL)
    graph_ids = [i for i in graph_scores if i not in seed_set]

    semantic_ids: list[str] = []
    embeddings = EmbeddingRepository(graph)
    try:
        vectors = await embeddings.vectors(seed_ids)
        if vectors and await embeddings.config() is not None:
            rows = await embeddings.search(centroid(list(vectors.values())), POOL + len(seed_ids))
            semantic_ids = [r["id"] for r in rows if r["id"] not in seed_set][:POOL]
        else:
            response.semantic_available = False
            response.note = (
                "These papers have no embeddings yet (run `researchgraph embed`), so "
                "recommendations use citation links only."
            )
    except ClientError as exc:
        log.warning("recommend.semantic_failed", code=exc.code)
        response.semantic_available = False
        response.note = "Semantic similarity is unavailable; using citation links only."

    fused = reciprocal_rank_fusion({"graph": graph_ids, "semantic": semantic_ids})[:limit]
    top_ids = [i for i, _ in fused]
    info = await queries.paper_summaries(top_ids)
    linked = await RecommendRepository(graph).linked_seeds(seed_ids, top_ids)

    for paper_id, score in fused:
        paper = info.get(paper_id)
        if paper is None or paper.is_stub:
            continue
        reasons: list[Reason] = []
        links = [summaries[s].title or s for s in linked.get(paper_id, [])]
        if links:
            reasons.append(
                Reason(
                    kind="directly_linked",
                    text=f"Cites or is cited by {len(links)} paper(s) on your list.",
                )
            )
        if paper_id in graph_scores:
            reasons.append(
                Reason(
                    kind="citation_proximity",
                    text=(
                        f"Reachable through short citation paths from your list "
                        f"(Personalized PageRank {graph_scores[paper_id]:.4f})."
                    ),
                )
            )
        if paper_id in semantic_ids:
            reasons.append(
                Reason(
                    kind="similar_meaning",
                    text=(
                        f"Its title and abstract are close in meaning to your list "
                        f"(rank {semantic_ids.index(paper_id) + 1} by similarity)."
                    ),
                )
            )
        response.recommendations.append(
            Recommendation(paper=paper, score=score, reasons=reasons, linked_to=links)
        )
    return response
