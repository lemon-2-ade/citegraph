from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import GraphDep
from app.schemas.paths import ReadingPath
from app.services.reading_path import build_reading_path

router = APIRouter(tags=["reading-paths"])


@router.get(
    "/reading-path",
    summary="An ordered reading path (foundational to recent) for a topic or around a paper",
    response_model=ReadingPath,
)
async def reading_path(
    graph: GraphDep,
    topic_id: str | None = None,
    paper_id: str | None = None,
    length: Annotated[int, Query(ge=2, le=20)] = 8,
) -> ReadingPath:
    return await build_reading_path(graph, topic_id=topic_id, paper_id=paper_id, length=length)
