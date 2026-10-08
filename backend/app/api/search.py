from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query

from app.api.deps import EmbedderDep, GraphDep
from app.repositories.search import MAX_QUERY_LENGTH, SearchRepository
from app.schemas.graph import PaperSearchResults, SearchResults
from app.services.paper_search import search_papers

router = APIRouter(tags=["search"])


@router.get(
    "/search",
    summary="Keyword search over papers, authors and topics",
    response_model=SearchResults,
)
async def search(
    graph: GraphDep,
    q: Annotated[str, Query(max_length=MAX_QUERY_LENGTH)],
    limit: Annotated[int, Query(ge=1, le=20)] = 6,
) -> SearchResults:
    return await SearchRepository(graph).search(q, limit)


@router.get(
    "/search/papers",
    summary="Search papers by keyword (BM25), meaning (embeddings) or both (hybrid)",
    response_model=PaperSearchResults,
)
async def search_paper_hits(
    graph: GraphDep,
    embedder: EmbedderDep,
    q: Annotated[str, Query(max_length=MAX_QUERY_LENGTH)],
    mode: Literal["keyword", "semantic", "hybrid"] = "hybrid",
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> PaperSearchResults:
    return await search_papers(graph, embedder, q, mode, limit)
