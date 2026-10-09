from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import GraphDep
from app.schemas.recommend import RecommendRequest, RecommendResponse
from app.services.recommend import recommend_papers

router = APIRouter(tags=["recommendations"])


@router.post(
    "/recommendations",
    summary="Recommend papers from a reading list (citation proximity + similar meaning)",
    response_model=RecommendResponse,
)
async def recommendations(body: RecommendRequest, graph: GraphDep) -> RecommendResponse:
    return await recommend_papers(graph, body.paper_ids, body.limit)
