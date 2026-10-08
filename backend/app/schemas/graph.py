"""API response models for graph entities."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import Field

from app.schemas.common import ResponseModel


class AuthorRef(ResponseModel):
    id: str
    name: str
    orcid: str | None = None
    position: int | None = None


class TopicRef(ResponseModel):
    id: str
    name: str
    score: float | None = None


class VenueRef(ResponseModel):
    id: str
    name: str
    type: str | None = None


class InstitutionRef(ResponseModel):
    id: str
    name: str
    country: str | None = None


class GraphMetrics(ResponseModel):
    """Structural metrics from graph analytics. ``None`` until analytics have run."""

    pagerank: float | None = None
    betweenness: float | None = None
    in_degree: int | None = None
    out_degree: int | None = None
    community_id: str | None = None


class PaperSummary(ResponseModel):
    id: str
    title: str | None
    year: int | None = None
    venue: str | None = None
    authors: list[str] = Field(default_factory=list)
    doi: str | None = None
    arxiv_id: str | None = None
    # Count reported by the external source (may be None); see ``cited_by_in_graph``.
    citation_count: int | None = None
    cited_by_in_graph: int = 0
    pagerank: float | None = None
    is_stub: bool = False


class PaperDetail(ResponseModel):
    id: str
    title: str | None
    abstract: str | None = None
    description: str | None = None
    year: int | None = None
    publication_date: date | None = None
    doi: str | None = None
    openalex_id: str | None = None
    arxiv_id: str | None = None
    url: str | None = None
    language: str | None = None
    citation_count: int | None = None
    authors_complete: bool = True
    is_stub: bool = False
    sources: list[str] = Field(default_factory=list)
    authors: list[AuthorRef] = Field(default_factory=list)
    venue: VenueRef | None = None
    topics: list[TopicRef] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    cited_by_in_graph: int = 0
    references_in_graph: int = 0
    metrics: GraphMetrics = Field(default_factory=GraphMetrics)


class CollaboratorRef(ResponseModel):
    id: str
    name: str
    shared_papers: int


class AuthorDetail(ResponseModel):
    id: str
    name: str
    orcid: str | None = None
    openalex_id: str | None = None
    institutions: list[InstitutionRef] = Field(default_factory=list)
    papers: list[PaperSummary] = Field(default_factory=list)
    collaborators: list[CollaboratorRef] = Field(default_factory=list)
    topics: list[TopicRef] = Field(default_factory=list)
    metrics: GraphMetrics = Field(default_factory=GraphMetrics)


class AuthorActivity(ResponseModel):
    id: str
    name: str
    paper_count: int


class TopicListItem(ResponseModel):
    id: str
    name: str
    paper_count: int


class RelatedTopic(ResponseModel):
    id: str
    name: str
    shared_papers: int


class TopicDetail(ResponseModel):
    id: str
    name: str
    description: str | None = None
    paper_count: int = 0
    top_papers: list[PaperSummary] = Field(default_factory=list)
    related_topics: list[RelatedTopic] = Field(default_factory=list)
    top_authors: list[AuthorActivity] = Field(default_factory=list)
    papers_per_year: dict[int, int] = Field(default_factory=dict)


class GraphNode(ResponseModel):
    """A paper as drawn in the graph view."""

    id: str
    title: str | None
    year: int | None = None
    pagerank: float | None = None
    cited_by_in_graph: int = 0
    community_id: str | None = None
    community_label: str | None = None
    is_stub: bool = False
    authors: list[str] = Field(default_factory=list)


class GraphEdge(ResponseModel):
    source: str
    target: str
    type: str = "CITES"


class GraphView(ResponseModel):
    """A bounded subgraph for visualisation. Edges point from the citing to the cited paper."""

    nodes: list[GraphNode]
    edges: list[GraphEdge]
    focus: str | None = None
    # True when more papers matched than are shown.
    truncated: bool = False
    total_papers: int | None = None
    note: str


class SearchHit(ResponseModel):
    kind: Literal["paper", "author", "topic"]
    id: str
    title: str
    subtitle: str | None = None
    score: float


class SearchResults(ResponseModel):
    query: str
    papers: list[SearchHit] = Field(default_factory=list)
    authors: list[SearchHit] = Field(default_factory=list)
    topics: list[SearchHit] = Field(default_factory=list)


class PaperHit(ResponseModel):
    paper: PaperSummary
    # Keyword: BM25; semantic: cosine similarity; hybrid: reciprocal-rank-fusion score.
    score: float
    matched_by: list[Literal["keyword", "semantic"]] = Field(default_factory=list)
    keyword_rank: int | None = None
    semantic_rank: int | None = None


class PaperSearchResults(ResponseModel):
    query: str
    mode: Literal["keyword", "semantic", "hybrid"]
    hits: list[PaperHit] = Field(default_factory=list)
    semantic_available: bool = True
    note: str | None = None
