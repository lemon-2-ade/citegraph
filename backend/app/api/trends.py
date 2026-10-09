from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import GraphDep
from app.schemas.trends import TrendsResponse
from app.services.trends import topic_trends

router = APIRouter(prefix="/trends", tags=["trends"])


@router.get(
    "/topics",
    summary="Topics gaining or losing share of papers: recent window vs the window before",
    response_model=TrendsResponse,
)
async def topics_trends(
    graph: GraphDep,
    window: Annotated[int, Query(ge=1, le=10)] = 3,
    min_papers: Annotated[int, Query(ge=1, le=100)] = 2,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> TrendsResponse:
    return await topic_trends(graph, window=window, min_papers=min_papers, limit=limit)
