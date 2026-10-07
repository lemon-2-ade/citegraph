from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import GraphDep
from app.repositories.graph_view import MAX_NEIGHBOUR_DEPTH, MAX_NODES, GraphViewRepository
from app.schemas.graph import GraphView

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get(
    "/overview",
    summary="Most influential papers and the citations among them, for visualisation",
    response_model=GraphView,
)
async def overview(
    graph: GraphDep,
    limit: Annotated[int, Query(ge=5, le=MAX_NODES)] = 80,
) -> GraphView:
    return await GraphViewRepository(graph).overview(limit)


@router.get(
    "/neighborhood/{paper_id}",
    summary="Citation neighbourhood of a paper, for visualisation",
    response_model=GraphView,
)
async def neighborhood(
    paper_id: str,
    graph: GraphDep,
    depth: Annotated[int, Query(ge=1, le=MAX_NEIGHBOUR_DEPTH)] = 1,
    limit: Annotated[int, Query(ge=5, le=MAX_NODES)] = 60,
) -> GraphView:
    return await GraphViewRepository(graph).neighbourhood(paper_id, depth, limit)
