from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import GraphDep
from app.repositories.search import MAX_QUERY_LENGTH, SearchRepository
from app.schemas.graph import SearchResults

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
