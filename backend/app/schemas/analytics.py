from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import ResponseModel
from app.schemas.graph import PaperSummary

PAGERANK_NOTE = (
    "PageRank measures structural influence inside this citation graph: a paper scores "
    "highly when it is cited by other highly-scored papers in the graph. It depends on "
    "which papers have been ingested, and it is not a measure of research quality, "
    "correctness or importance outside this graph."
)
BETWEENNESS_NOTE = (
    "Betweenness measures how often a node lies on shortest paths between other nodes "
    "(ignoring citation direction). High values indicate bridges between otherwise "
    "separate parts of the graph. Values are sampled estimates on large graphs."
)


class GraphSummary(ResponseModel):
    papers: int
    stub_papers: int
    authors: int
    citations: int
    topics: int
    venues: int
    institutions: int
    paper_communities: int
    author_communities: int
    analytics_computed_at: str | None


class YearCount(ResponseModel):
    year: int
    papers: int


class RankedPaper(ResponseModel):
    paper: PaperSummary
    score: float


class RankedAuthor(ResponseModel):
    id: str
    name: str
    score: float
    paper_count: int | None = None


class InfluentialResponse(ResponseModel):
    entity: Literal["paper", "author"]
    metric: str
    note: str
    papers: list[RankedPaper] = Field(default_factory=list)
    authors: list[RankedAuthor] = Field(default_factory=list)


class SimilarPaper(ResponseModel):
    paper: PaperSummary
    method: Literal["coupling", "cocitation", "ppr"]
    score: float
    shared: int | None = None
    explanation: str


class PathNode(ResponseModel):
    id: str
    label: str
    name: str | None = None
    year: int | None = None


class PathRelationship(ResponseModel):
    type: str
    source: str
    target: str


class PathResponse(ResponseModel):
    found: bool
    length: int | None = None
    nodes: list[PathNode] = Field(default_factory=list)
    relationships: list[PathRelationship] = Field(default_factory=list)
    explanation: str


class CommunitySummary(ResponseModel):
    id: str
    scope: Literal["papers", "authors"]
    rank: int
    size: int
    label: str | None = None
    top_topics: list[str] = Field(default_factory=list)
    algorithm: str
    computed_at: str | None = None


class CountItem(ResponseModel):
    id: str | None = None
    name: str
    count: int


class CommunityLink(ResponseModel):
    community_id: str
    label: str | None
    citations_out: int
    citations_in: int


class CommunityDetail(CommunitySummary):
    top_papers: list[PaperSummary] = Field(default_factory=list)
    top_authors: list[CountItem] = Field(default_factory=list)
    institutions: list[CountItem] = Field(default_factory=list)
    topics: list[CountItem] = Field(default_factory=list)
    papers_per_year: dict[int, int] = Field(default_factory=dict)
    connections: list[CommunityLink] = Field(default_factory=list)


class AnalyticsRunCreate(BaseModel):
    backend: Literal["auto", "gds", "networkx"] | None = None
    community_algorithm: Literal["louvain", "leiden"] = "louvain"
    min_community_size: int = Field(default=3, ge=1, le=1000)


class AnalyticsRunOut(ResponseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    backend: str | None
    options: dict[str, Any]
    report: dict[str, Any]
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
