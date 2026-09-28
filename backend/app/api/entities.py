"""Author and topic endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import GraphDep
from app.repositories.authors import AuthorRepository
from app.repositories.topics import TopicRepository
from app.schemas.common import Page, PageParams
from app.schemas.graph import AuthorDetail, TopicDetail, TopicListItem

router = APIRouter()


@router.get("/authors/{author_id}", tags=["authors"], response_model=AuthorDetail)
async def get_author(author_id: str, graph: GraphDep) -> AuthorDetail:
    return await AuthorRepository(graph).get(author_id)


@router.get("/topics", tags=["topics"], response_model=Page[TopicListItem])
async def list_topics(
    graph: GraphDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> Page[TopicListItem]:
    return await TopicRepository(graph).list(PageParams(page=page, page_size=page_size))


@router.get("/topics/{topic_id}", tags=["topics"], response_model=TopicDetail)
async def get_topic(topic_id: str, graph: GraphDep) -> TopicDetail:
    return await TopicRepository(graph).get(topic_id)
