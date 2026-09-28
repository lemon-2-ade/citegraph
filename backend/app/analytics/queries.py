"""Read-side analytics queries (backend-independent Cypher)."""

from __future__ import annotations

from typing import Literal, LiteralString, get_args

from app.core.errors import NotFoundError, ValidationFailedError
from app.graph.client import GraphClient
from app.repositories.papers import SUMMARY, summary_from_row
from app.schemas.analytics import (
    BETWEENNESS_NOTE,
    PAGERANK_NOTE,
    CommunityDetail,
    CommunityLink,
    CommunitySummary,
    CountItem,
    GraphSummary,
    InfluentialResponse,
    PathNode,
    PathRelationship,
    PathResponse,
    RankedAuthor,
    RankedPaper,
    SimilarPaper,
)
from app.schemas.graph import PaperSummary

PaperMetric = Literal["pagerank", "betweenness", "in_degree"]
AuthorMetric = Literal["pagerank", "betweenness", "paper_count"]

_SUMMARY_COUNTS = """
RETURN
  COUNT { (p:Paper) WHERE coalesce(p.is_stub, false) = false } AS papers,
  COUNT { (p:Paper {is_stub: true}) } AS stub_papers,
  COUNT { (:Author) } AS authors,
  COUNT { (:Paper)-[:CITES]->(:Paper) } AS citations,
  COUNT { (:Topic) } AS topics,
  COUNT { (:Venue) } AS venues,
  COUNT { (:Institution) } AS institutions,
  COUNT { (:Community {scope: 'papers'}) } AS paper_communities,
  COUNT { (:Community {scope: 'authors'}) } AS author_communities,
  COLLECT {
      MATCH (c:Community) RETURN toString(c.computed_at) ORDER BY c.computed_at DESC LIMIT 1
  }[0] AS analytics_computed_at
"""

_INFLUENTIAL_PAPERS: dict[PaperMetric, LiteralString] = {
    "pagerank": "MATCH (p:Paper) WHERE p.pagerank IS NOT NULL"
    " AND coalesce(p.is_stub, false) = false"
    " WITH p ORDER BY p.pagerank DESC, p.id LIMIT $limit"
    " RETURN p.pagerank AS score, " + SUMMARY,
    "betweenness": "MATCH (p:Paper) WHERE p.betweenness IS NOT NULL"
    " AND coalesce(p.is_stub, false) = false"
    " WITH p ORDER BY p.betweenness DESC, p.id LIMIT $limit"
    " RETURN p.betweenness AS score, " + SUMMARY,
    "in_degree": "MATCH (p:Paper) WHERE p.in_degree IS NOT NULL"
    " AND coalesce(p.is_stub, false) = false"
    " WITH p ORDER BY p.in_degree DESC, p.id LIMIT $limit"
    " RETURN toFloat(p.in_degree) AS score, " + SUMMARY,
}

_INFLUENTIAL_AUTHORS: dict[AuthorMetric, LiteralString] = {
    "pagerank": """
        MATCH (a:Author) WHERE a.pagerank IS NOT NULL
        RETURN a.id AS id, a.name AS name, a.pagerank AS score, a.paper_count AS paper_count
        ORDER BY score DESC, id LIMIT $limit""",
    "betweenness": """
        MATCH (a:Author) WHERE a.betweenness IS NOT NULL
        RETURN a.id AS id, a.name AS name, a.betweenness AS score, a.paper_count AS paper_count
        ORDER BY score DESC, id LIMIT $limit""",
    "paper_count": """
        MATCH (a:Author)
        WITH a, COUNT { (a)-[:WROTE]->(:Paper) } AS n
        RETURN a.id AS id, a.name AS name, toFloat(n) AS score, n AS paper_count
        ORDER BY score DESC, id LIMIT $limit""",
}

_COUPLING = (
    """
MATCH (src:Paper {id: $id})-[:CITES]->(r:Paper)<-[:CITES]-(q:Paper)
WHERE q <> src
WITH src, q, count(DISTINCT r) AS shared
WITH q, shared, COUNT { (src)-[:CITES]->(:Paper) } AS mine,
     COUNT { (q)-[:CITES]->(:Paper) } AS theirs
WITH q AS p, shared, toFloat(shared) / (mine + theirs - shared) AS score
ORDER BY score DESC, shared DESC, p.id LIMIT $limit
RETURN shared, score, """
    + SUMMARY
)

_COCITATION = (
    """
MATCH (src:Paper {id: $id})<-[:CITES]-(c:Paper)-[:CITES]->(q:Paper)
WHERE q <> src
WITH src, q, count(DISTINCT c) AS shared
WITH q, shared, COUNT { (:Paper)-[:CITES]->(src) } AS mine,
     COUNT { (:Paper)-[:CITES]->(q) } AS theirs
WITH q AS p, shared, toFloat(shared) / (mine + theirs - shared) AS score
ORDER BY score DESC, shared DESC, p.id LIMIT $limit
RETURN shared, score, """
    + SUMMARY
)

_SUMMARIES_BY_ID = (
    """
UNWIND $ids AS id
MATCH (p:Paper {id: id})
RETURN """
    + SUMMARY
)

_PAPER_EXISTS = "MATCH (p:Paper {id: $id}) RETURN p.id AS id"

_COMMUNITIES = """
MATCH (c:Community {scope: $scope})
RETURN c {.id, .scope, .rank, .size, .label, .top_topics, .algorithm,
          computed_at: toString(c.computed_at)} AS community
ORDER BY c.rank SKIP $skip LIMIT $limit
"""

_COMMUNITY = """
MATCH (c:Community {id: $id})
RETURN c {.id, .scope, .rank, .size, .label, .top_topics, .algorithm,
          computed_at: toString(c.computed_at)} AS community
"""

_PAPER_COMMUNITY_DETAIL = """
MATCH (c:Community {id: $id})
RETURN
COLLECT {
    MATCH (c)<-[:IN_COMMUNITY]-(:Paper)<-[:WROTE]-(a:Author)
    WITH a, count(*) AS n ORDER BY n DESC, a.name LIMIT 15
    RETURN {id: a.id, name: a.name, count: n}
} AS authors,
COLLECT {
    MATCH (c)<-[:IN_COMMUNITY]-(:Paper)<-[:WROTE]-(:Author)-[:AFFILIATED_WITH]->(i:Institution)
    WITH i, count(*) AS n ORDER BY n DESC, i.name LIMIT 15
    RETURN {id: i.id, name: i.name, count: n}
} AS institutions,
COLLECT {
    MATCH (c)<-[:IN_COMMUNITY]-(:Paper)-[:HAS_TOPIC]->(t:Topic)
    WITH t, count(*) AS n ORDER BY n DESC, t.name LIMIT 15
    RETURN {id: t.id, name: t.name, count: n}
} AS topics,
COLLECT {
    MATCH (c)<-[:IN_COMMUNITY]-(p:Paper) WHERE p.year IS NOT NULL
    WITH p.year AS year, count(*) AS n ORDER BY year
    RETURN [year, n]
} AS per_year,
COLLECT {
    MATCH (c)<-[:IN_COMMUNITY]-(:Paper)-[:CITES]->(:Paper)-[:IN_COMMUNITY]->(o:Community)
    WHERE o <> c
    WITH o, count(*) AS n
    RETURN {community_id: o.id, label: o.label, n: n}
} AS cites_out,
COLLECT {
    MATCH (c)<-[:IN_COMMUNITY]-(:Paper)<-[:CITES]-(:Paper)-[:IN_COMMUNITY]->(o:Community)
    WHERE o <> c
    WITH o, count(*) AS n
    RETURN {community_id: o.id, label: o.label, n: n}
} AS cites_in
"""

_PAPER_COMMUNITY_TOP = (
    """
MATCH (:Community {id: $id})<-[:IN_COMMUNITY]-(p:Paper)
WITH p ORDER BY coalesce(p.pagerank, 0.0) DESC, p.id LIMIT $limit
RETURN """
    + SUMMARY
)

_AUTHOR_COMMUNITY_DETAIL = """
MATCH (c:Community {id: $id})
RETURN
COLLECT {
    MATCH (c)<-[:IN_COMMUNITY]-(a:Author)
    WITH a ORDER BY coalesce(a.pagerank, 0.0) DESC, a.name LIMIT 15
    RETURN {id: a.id, name: a.name, count: COUNT { (a)-[:WROTE]->(:Paper) }}
} AS authors,
COLLECT {
    MATCH (c)<-[:IN_COMMUNITY]-(:Author)-[:AFFILIATED_WITH]->(i:Institution)
    WITH i, count(*) AS n ORDER BY n DESC, i.name LIMIT 15
    RETURN {id: i.id, name: i.name, count: n}
} AS institutions,
COLLECT {
    MATCH (c)<-[:IN_COMMUNITY]-(:Author)-[:WROTE]->(:Paper)-[:HAS_TOPIC]->(t:Topic)
    WITH t, count(*) AS n ORDER BY n DESC, t.name LIMIT 15
    RETURN {id: t.id, name: t.name, count: n}
} AS topics,
COLLECT {
    MATCH (c)<-[:IN_COMMUNITY]-(:Author)-[:WROTE]->(p:Paper) WHERE p.year IS NOT NULL
    WITH p.year AS year, count(DISTINCT p) AS n ORDER BY year
    RETURN [year, n]
} AS per_year
"""

_AUTHOR_COMMUNITY_TOP_PAPERS = (
    """
MATCH (:Community {id: $id})<-[:IN_COMMUNITY]-(:Author)-[:WROTE]->(p:Paper)
WITH DISTINCT p ORDER BY coalesce(p.pagerank, 0.0) DESC, p.id LIMIT $limit
RETURN """
    + SUMMARY
)

# Shortest paths --------------------------------------------------------------------------
ID_PREFIX_LABELS = {
    "paper": "Paper",
    "author": "Author",
    "topic": "Topic",
    "venue": "Venue",
    "institution": "Institution",
    "keyword": "Keyword",
}
PathRelationshipType = Literal[
    "CITES",
    "WROTE",
    "HAS_TOPIC",
    "PUBLISHED_IN",
    "HAS_KEYWORD",
    "AFFILIATED_WITH",
    "COLLABORATED_WITH",
    "RELATED_TO",
]
PATH_RELATIONSHIPS: tuple[str, ...] = get_args(PathRelationshipType)
MAX_PATH_HOPS = 8


def label_for_id(node_id: str) -> str:
    prefix = node_id.split(":", 1)[0]
    label = ID_PREFIX_LABELS.get(prefix)
    if label is None:
        raise ValidationFailedError(f"Unsupported node id {node_id!r}")
    return label


def build_shortest_path_query(
    source_label: str, target_label: str, relationships: list[str], max_hops: int
) -> str:
    """Build a shortestPath query from whitelisted parts only.

    Labels, relationship types and the hop bound cannot be Cypher parameters, so they
    are validated against fixed whitelists here; node IDs remain parameters.
    """
    if (
        source_label not in ID_PREFIX_LABELS.values()
        or target_label not in ID_PREFIX_LABELS.values()
    ):
        raise ValidationFailedError("unsupported node label")
    if not relationships or any(r not in PATH_RELATIONSHIPS for r in relationships):
        raise ValidationFailedError(f"relationships must be a subset of {PATH_RELATIONSHIPS}")
    if not 1 <= max_hops <= MAX_PATH_HOPS:
        raise ValidationFailedError(f"max_hops must be between 1 and {MAX_PATH_HOPS}")
    types = "|".join(dict.fromkeys(relationships))
    return (
        f"MATCH (a:{source_label} {{id: $source}}), (b:{target_label} {{id: $target}}) "
        f"MATCH path = shortestPath((a)-[:{types}*..{max_hops}]-(b)) "
        "RETURN [n IN nodes(path) | {id: n.id, label: labels(n)[0], "
        "name: coalesce(n.title, n.name), year: n.year}] AS nodes, "
        "[r IN relationships(path) | {type: type(r), source: startNode(r).id, "
        "target: endNode(r).id}] AS relationships"
    )


_REL_PHRASES = {
    "CITES": "cites",
    "WROTE": "wrote",
    "HAS_TOPIC": "has topic",
    "PUBLISHED_IN": "published in",
    "HAS_KEYWORD": "has keyword",
    "AFFILIATED_WITH": "affiliated with",
    "COLLABORATED_WITH": "collaborated with",
    "RELATED_TO": "co-occurs with",
}


def describe_path(nodes: list[PathNode], rels: list[PathRelationship]) -> str:
    names = {n.id: n.name or n.id for n in nodes}
    steps = [
        f"{names[r.source]} {_REL_PHRASES.get(r.type, r.type)} {names[r.target]}" for r in rels
    ]
    return "; ".join(steps)


class AnalyticsQueries:
    def __init__(self, graph: GraphClient) -> None:
        self._graph = graph

    async def summary(self) -> GraphSummary:
        rows = await self._graph.read(_SUMMARY_COUNTS, label="analytics.summary")
        return GraphSummary.model_validate(rows[0])

    async def influential_papers(self, metric: PaperMetric, limit: int) -> InfluentialResponse:
        rows = await self._graph.read(
            _INFLUENTIAL_PAPERS[metric], {"limit": limit}, label=f"analytics.top_papers.{metric}"
        )
        return InfluentialResponse(
            entity="paper",
            metric=metric,
            note=_note(metric),
            papers=[RankedPaper(paper=summary_from_row(r), score=r["score"]) for r in rows],
        )

    async def influential_authors(self, metric: AuthorMetric, limit: int) -> InfluentialResponse:
        rows = await self._graph.read(
            _INFLUENTIAL_AUTHORS[metric], {"limit": limit}, label=f"analytics.top_authors.{metric}"
        )
        return InfluentialResponse(
            entity="author",
            metric=metric,
            note=_note(metric),
            authors=[RankedAuthor.model_validate(r) for r in rows],
        )

    async def similar_papers(
        self, paper_id: str, method: Literal["coupling", "cocitation"], limit: int
    ) -> list[SimilarPaper]:
        await self._require_paper(paper_id)
        query = _COUPLING if method == "coupling" else _COCITATION
        rows = await self._graph.read(
            query, {"id": paper_id, "limit": limit}, label=f"analytics.similar.{method}"
        )
        results = []
        for r in rows:
            if method == "coupling":
                why = (
                    f"Shares {r['shared']} reference(s) with this paper (Jaccard {r['score']:.2f})."
                )
            else:
                why = (
                    f"Cited together with this paper by {r['shared']} paper(s) "
                    f"(Jaccard {r['score']:.2f})."
                )
            results.append(
                SimilarPaper(
                    paper=summary_from_row(r),
                    method=method,
                    score=r["score"],
                    shared=r["shared"],
                    explanation=why,
                )
            )
        return results

    async def paper_summaries(self, ids: list[str]) -> dict[str, PaperSummary]:
        rows = await self._graph.read(_SUMMARIES_BY_ID, {"ids": ids}, label="analytics.summaries")
        return {r["id"]: summary_from_row(r) for r in rows}

    async def shortest_path(
        self, source: str, target: str, relationships: list[str], max_hops: int
    ) -> PathResponse:
        if source == target:
            raise ValidationFailedError("source and target must differ")
        query = build_shortest_path_query(
            label_for_id(source), label_for_id(target), relationships, max_hops
        )
        rows = await self._graph.run_readonly_unchecked(
            query, {"source": source, "target": target}, label="analytics.shortest_path"
        )
        if not rows:
            return PathResponse(
                found=False,
                explanation=(
                    f"No path of at most {max_hops} hops over {', '.join(relationships)} "
                    "connects these nodes in the current graph (or a node does not exist)."
                ),
            )
        nodes = [PathNode.model_validate(n) for n in rows[0]["nodes"]]
        rels = [PathRelationship.model_validate(r) for r in rows[0]["relationships"]]
        return PathResponse(
            found=True,
            length=len(rels),
            nodes=nodes,
            relationships=rels,
            explanation=describe_path(nodes, rels),
        )

    async def communities(
        self, scope: Literal["papers", "authors"], skip: int, limit: int
    ) -> list[CommunitySummary]:
        rows = await self._graph.read(
            _COMMUNITIES, {"scope": scope, "skip": skip, "limit": limit}, label="communities.list"
        )
        return [CommunitySummary.model_validate(_clean(r["community"])) for r in rows]

    async def community(self, community_id: str, top_papers: int = 10) -> CommunityDetail:
        rows = await self._graph.read(_COMMUNITY, {"id": community_id}, label="communities.get")
        if not rows:
            raise NotFoundError(f"Community {community_id!r} not found")
        base = CommunitySummary.model_validate(_clean(rows[0]["community"]))
        params = {"id": community_id, "limit": top_papers}
        if base.scope == "papers":
            detail = (await self._graph.read(_PAPER_COMMUNITY_DETAIL, params))[0]
            papers = await self._graph.read(_PAPER_COMMUNITY_TOP, params)
            connections = _merge_links(detail["cites_out"], detail["cites_in"])
        else:
            detail = (await self._graph.read(_AUTHOR_COMMUNITY_DETAIL, params))[0]
            papers = await self._graph.read(_AUTHOR_COMMUNITY_TOP_PAPERS, params)
            connections = []
        return CommunityDetail(
            **base.model_dump(),
            top_papers=[summary_from_row(p) for p in papers],
            top_authors=[CountItem.model_validate(a) for a in detail["authors"]],
            institutions=[CountItem.model_validate(i) for i in detail["institutions"]],
            topics=[CountItem.model_validate(t) for t in detail["topics"]],
            papers_per_year={int(y): int(n) for y, n in detail["per_year"]},
            connections=connections,
        )

    async def _require_paper(self, paper_id: str) -> None:
        if not await self._graph.read(_PAPER_EXISTS, {"id": paper_id}, label="papers.exists"):
            raise NotFoundError(f"Paper {paper_id!r} not found")


def _note(metric: str) -> str:
    if metric == "pagerank":
        return PAGERANK_NOTE
    if metric == "betweenness":
        return BETWEENNESS_NOTE
    return "Raw counts within the ingested graph; they depend on what has been ingested."


def _merge_links(
    outgoing: list[dict[str, object]], incoming: list[dict[str, object]], limit: int = 10
) -> list[CommunityLink]:
    links: dict[str, CommunityLink] = {}
    for rows, attr in ((outgoing, "citations_out"), (incoming, "citations_in")):
        for row in rows:
            cid = str(row["community_id"])
            link = links.setdefault(
                cid,
                CommunityLink(
                    community_id=cid,
                    label=row["label"] if isinstance(row["label"], str) else None,
                    citations_out=0,
                    citations_in=0,
                ),
            )
            setattr(link, attr, int(str(row["n"])))
    ranked = sorted(
        links.values(),
        key=lambda link: (-(link.citations_out + link.citations_in), link.community_id),
    )
    return ranked[:limit]


def _clean(community: dict[str, object]) -> dict[str, object]:
    return {k: v for k, v in community.items() if v is not None}
