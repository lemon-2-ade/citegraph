"""Graph analytics endpoints: summary, influence rankings, communities, paths, runs."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query, status

from app.analytics.queries import (
    MAX_PATH_HOPS,
    AnalyticsQueries,
    AuthorMetric,
    PaperMetric,
    PathRelationshipType,
)
from app.api.deps import AdminDep, GraphDep, QueueDep, SessionsDep
from app.repositories.analytics_runs import AnalyticsRunRepository
from app.schemas.analytics import (
    AnalyticsRunCreate,
    AnalyticsRunOut,
    CommunityDetail,
    CommunitySummary,
    GraphSummary,
    InfluentialResponse,
    PathResponse,
    YearCount,
)
from app.workers.tasks import ANALYTICS_TASK

router = APIRouter()


@router.get("/analytics/summary", tags=["analytics"], response_model=GraphSummary)
async def summary(graph: GraphDep) -> GraphSummary:
    return await AnalyticsQueries(graph).summary()


@router.get(
    "/analytics/years",
    tags=["analytics"],
    response_model=list[YearCount],
    summary="Number of ingested papers per publication year (stubs excluded)",
)
async def papers_per_year(graph: GraphDep) -> list[YearCount]:
    return await AnalyticsQueries(graph).papers_per_year()


@router.get(
    "/analytics/influential",
    tags=["analytics"],
    response_model=InfluentialResponse,
    summary="Most structurally influential papers or authors (see `note` in the response)",
)
async def influential(
    graph: GraphDep,
    entity: Literal["paper", "author"] = "paper",
    metric: Literal["pagerank", "betweenness", "in_degree", "paper_count"] = "pagerank",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> InfluentialResponse:
    queries = AnalyticsQueries(graph)
    if entity == "paper":
        if metric == "paper_count":
            metric = "in_degree"
        paper_metric: PaperMetric = metric
        return await queries.influential_papers(paper_metric, limit)
    author_metric: AuthorMetric = "paper_count" if metric == "in_degree" else metric
    return await queries.influential_authors(author_metric, limit)


@router.get("/communities", tags=["communities"], response_model=list[CommunitySummary])
async def list_communities(
    graph: GraphDep,
    scope: Literal["papers", "authors"] = "papers",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[CommunitySummary]:
    return await AnalyticsQueries(graph).communities(scope, (page - 1) * page_size, page_size)


@router.get("/communities/{community_id}", tags=["communities"], response_model=CommunityDetail)
async def get_community(community_id: str, graph: GraphDep) -> CommunityDetail:
    return await AnalyticsQueries(graph).community(community_id)


@router.get(
    "/graph/shortest-path",
    tags=["graph"],
    response_model=PathResponse,
    summary="Shortest undirected path between two nodes over selected relationship types",
)
async def shortest_path(
    graph: GraphDep,
    source: str,
    target: str,
    relationships: Annotated[
        list[PathRelationshipType] | None,
        Query(description="Relationship types to traverse (default: CITES)"),
    ] = None,
    max_hops: Annotated[int, Query(ge=1, le=MAX_PATH_HOPS)] = 6,
) -> PathResponse:
    return await AnalyticsQueries(graph).shortest_path(
        source, target, list(relationships or ["CITES"]), max_hops
    )


# -- runs (administrative) --------------------------------------------------------------
runs = APIRouter(prefix="/analytics/runs", tags=["analytics"], dependencies=[AdminDep])


@runs.post("", status_code=status.HTTP_202_ACCEPTED, response_model=AnalyticsRunOut)
async def create_run(
    body: AnalyticsRunCreate, sessions: SessionsDep, queue: QueueDep
) -> AnalyticsRunOut:
    run = await AnalyticsRunRepository(sessions).create(body.model_dump())
    await queue.enqueue_job(ANALYTICS_TASK, str(run.id), _job_id=f"analytics-{run.id}")
    return AnalyticsRunOut.model_validate(run)


@runs.get("", response_model=list[AnalyticsRunOut])
async def list_runs(
    sessions: SessionsDep, limit: Annotated[int, Query(ge=1, le=100)] = 20
) -> list[AnalyticsRunOut]:
    return [
        AnalyticsRunOut.model_validate(r)
        for r in await AnalyticsRunRepository(sessions).list(limit)
    ]


@runs.get("/{run_id}", response_model=AnalyticsRunOut)
async def get_run(run_id: uuid.UUID, sessions: SessionsDep) -> AnalyticsRunOut:
    return AnalyticsRunOut.model_validate(await AnalyticsRunRepository(sessions).get(run_id))
