"""Read access to papers and their citation neighbourhood."""

from __future__ import annotations

from typing import Any, Literal, LiteralString

from app.core.errors import NotFoundError
from app.graph.client import GraphClient
from app.schemas.common import Page, PageParams
from app.schemas.graph import (
    AuthorRef,
    GraphMetrics,
    PaperDetail,
    PaperSummary,
    TopicRef,
    VenueRef,
)

PaperSort = Literal["year", "pagerank", "cited_by"]

# Projection of a paper node ``p`` into the fields of ``PaperSummary``.
SUMMARY: LiteralString = """
    p.id AS id, p.title AS title, p.year AS year, p.doi AS doi, p.arxiv_id AS arxiv_id,
    p.citation_count AS citation_count, p.pagerank AS pagerank,
    coalesce(p.is_stub, false) AS is_stub,
    COUNT { (:Paper)-[:CITES]->(p) } AS cited_by_in_graph,
    COLLECT { MATCH (p)-[:PUBLISHED_IN]->(v:Venue) RETURN v.name LIMIT 1 }[0] AS venue,
    COLLECT {
        MATCH (a:Author)-[w:WROTE]->(p) RETURN a.name ORDER BY w.position LIMIT 6
    } AS authors
"""

_ORDER: dict[PaperSort, LiteralString] = {
    "year": "ORDER BY p.year DESC, p.title",
    "pagerank": "ORDER BY coalesce(p.pagerank, 0.0) DESC, p.year DESC",
    "cited_by": "ORDER BY COUNT { (:Paper)-[:CITES]->(p) } DESC, p.year DESC",
}

_LIST_FILTER: LiteralString = """
    MATCH (p:Paper)
    WHERE coalesce(p.is_stub, false) = false
      AND ($year_from IS NULL OR p.year >= $year_from)
      AND ($year_to IS NULL OR p.year <= $year_to)
      AND ($topic_id IS NULL OR EXISTS { (p)-[:HAS_TOPIC]->(:Topic {id: $topic_id}) })
"""

_DETAIL: LiteralString = """
    MATCH (p:Paper {id: $id})
    RETURN p {
        .id, .title, .abstract, .description, .year, .doi, .openalex_id, .arxiv_id, .url,
        .language, .citation_count, .authors_complete, .is_stub, .sources,
        .pagerank, .betweenness, .in_degree, .out_degree, .community_id,
        publication_date: toString(p.publication_date)
    } AS paper,
    COLLECT {
        MATCH (a:Author)-[w:WROTE]->(p)
        RETURN {id: a.id, name: a.name, orcid: a.orcid, position: w.position}
        ORDER BY w.position
    } AS authors,
    COLLECT {
        MATCH (p)-[:PUBLISHED_IN]->(v:Venue) RETURN v {.id, .name, .type} LIMIT 1
    } AS venues,
    COLLECT {
        MATCH (p)-[h:HAS_TOPIC]->(t:Topic)
        RETURN {id: t.id, name: t.name, score: h.score} ORDER BY h.score DESC
    } AS topics,
    COLLECT { MATCH (p)-[:HAS_KEYWORD]->(k:Keyword) RETURN k.name } AS keywords,
    COUNT { (:Paper)-[:CITES]->(p) } AS cited_by_in_graph,
    COUNT { (p)-[:CITES]->(:Paper) } AS references_in_graph
"""


def summary_from_row(row: dict[str, Any]) -> PaperSummary:
    return PaperSummary.model_validate(row)


class PaperRepository:
    def __init__(self, graph: GraphClient) -> None:
        self._graph = graph

    async def get(self, paper_id: str) -> PaperDetail:
        rows = await self._graph.read(_DETAIL, {"id": paper_id}, label="papers.get")
        if not rows:
            raise NotFoundError(f"Paper {paper_id!r} not found")
        row = rows[0]
        paper = row["paper"]
        metrics = GraphMetrics(
            pagerank=paper.pop("pagerank", None),
            betweenness=paper.pop("betweenness", None),
            in_degree=paper.pop("in_degree", None),
            out_degree=paper.pop("out_degree", None),
            community_id=paper.pop("community_id", None),
        )
        return PaperDetail(
            **{k: v for k, v in paper.items() if v is not None},
            authors=[AuthorRef.model_validate(a) for a in row["authors"]],
            venue=VenueRef.model_validate(row["venues"][0]) if row["venues"] else None,
            topics=[TopicRef.model_validate(t) for t in row["topics"]],
            keywords=row["keywords"],
            cited_by_in_graph=row["cited_by_in_graph"],
            references_in_graph=row["references_in_graph"],
            metrics=metrics,
        )

    async def list(
        self,
        page: PageParams,
        *,
        year_from: int | None = None,
        year_to: int | None = None,
        topic_id: str | None = None,
        sort: PaperSort = "year",
    ) -> Page[PaperSummary]:
        params = {
            "year_from": year_from,
            "year_to": year_to,
            "topic_id": topic_id,
            "skip": page.skip,
            "limit": page.page_size,
        }
        query = (
            _LIST_FILTER + "WITH p " + _ORDER[sort] + " SKIP $skip LIMIT $limit RETURN " + SUMMARY
        )
        rows = await self._graph.read(query, params, label=f"papers.list.{sort}")
        total_rows = await self._graph.read(
            _LIST_FILTER + "RETURN count(p) AS total", params, label="papers.count"
        )
        return Page(
            items=[summary_from_row(r) for r in rows],
            total=total_rows[0]["total"] if total_rows else 0,
            page=page.page,
            page_size=page.page_size,
        )

    async def citations(self, paper_id: str, page: PageParams) -> Page[PaperSummary]:
        """Papers in the graph that cite ``paper_id`` (incoming CITES)."""
        await self._ensure_exists(paper_id)
        rows = await self._graph.read(
            """
            MATCH (p:Paper)-[:CITES]->(:Paper {id: $id})
            WITH p ORDER BY p.year DESC, p.title SKIP $skip LIMIT $limit
            RETURN """
            + SUMMARY,
            {"id": paper_id, "skip": page.skip, "limit": page.page_size},
            label="papers.citations",
        )
        total = await self._graph.read(
            "MATCH (:Paper)-[r:CITES]->(:Paper {id: $id}) RETURN count(r) AS total",
            {"id": paper_id},
        )
        return Page(
            items=[summary_from_row(r) for r in rows],
            total=total[0]["total"],
            page=page.page,
            page_size=page.page_size,
        )

    async def references(self, paper_id: str, page: PageParams) -> Page[PaperSummary]:
        """Papers cited by ``paper_id`` (outgoing CITES), including not-yet-ingested stubs."""
        await self._ensure_exists(paper_id)
        rows = await self._graph.read(
            """
            MATCH (:Paper {id: $id})-[:CITES]->(p:Paper)
            WITH p ORDER BY coalesce(p.is_stub, false), p.year DESC, p.title
            SKIP $skip LIMIT $limit
            RETURN """
            + SUMMARY,
            {"id": paper_id, "skip": page.skip, "limit": page.page_size},
            label="papers.references",
        )
        total = await self._graph.read(
            "MATCH (:Paper {id: $id})-[r:CITES]->(:Paper) RETURN count(r) AS total",
            {"id": paper_id},
        )
        return Page(
            items=[summary_from_row(r) for r in rows],
            total=total[0]["total"],
            page=page.page,
            page_size=page.page_size,
        )

    async def _ensure_exists(self, paper_id: str) -> None:
        rows = await self._graph.read(
            "MATCH (p:Paper {id: $id}) RETURN p.id AS id", {"id": paper_id}, label="papers.exists"
        )
        if not rows:
            raise NotFoundError(f"Paper {paper_id!r} not found")
