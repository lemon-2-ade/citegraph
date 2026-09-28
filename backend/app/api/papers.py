from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import GraphDep
from app.repositories.papers import PaperRepository, PaperSort
from app.schemas.common import Page, PageParams
from app.schemas.graph import PaperDetail, PaperSummary

router = APIRouter(prefix="/papers", tags=["papers"])


@router.get("", summary="List papers", response_model=Page[PaperSummary])
async def list_papers(
    graph: GraphDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    year_from: Annotated[int | None, Query(ge=1600, le=2100)] = None,
    year_to: Annotated[int | None, Query(ge=1600, le=2100)] = None,
    topic_id: str | None = None,
    sort: PaperSort = "year",
) -> Page[PaperSummary]:
    return await PaperRepository(graph).list(
        PageParams(page=page, page_size=page_size),
        year_from=year_from,
        year_to=year_to,
        topic_id=topic_id,
        sort=sort,
    )


@router.get("/{paper_id}", summary="Paper details", response_model=PaperDetail)
async def get_paper(paper_id: str, graph: GraphDep) -> PaperDetail:
    return await PaperRepository(graph).get(paper_id)


@router.get(
    "/{paper_id}/citations",
    summary="Papers citing this paper",
    response_model=Page[PaperSummary],
)
async def get_citations(
    paper_id: str,
    graph: GraphDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[PaperSummary]:
    return await PaperRepository(graph).citations(
        paper_id, PageParams(page=page, page_size=page_size)
    )


@router.get(
    "/{paper_id}/references",
    summary="Papers cited by this paper",
    response_model=Page[PaperSummary],
)
async def get_references(
    paper_id: str,
    graph: GraphDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[PaperSummary]:
    return await PaperRepository(graph).references(
        paper_id, PageParams(page=page, page_size=page_size)
    )
