"""Batch graph analytics: compute metrics and write them back to the graph.

    researchgraph analyze     (CLI)      POST /api/analytics/runs     (API -> worker)

Steps
    1. Rebuild derived edges: COLLABORATED_WITH (co-authorship, weighted) and
       RELATED_TO (topic co-occurrence, weighted).
    2. Citation graph: in/out degree, PageRank, betweenness, communities -> Paper
       properties, Community nodes (scope "papers") and IN_COMMUNITY edges.
    3. Collaboration graph: PageRank, betweenness, collaborator count, communities ->
       Author properties and Community nodes (scope "authors").
    4. Community summaries: dominant topics per community.
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, LiteralString

from app.analytics.algorithms import CommunityAlgorithm
from app.analytics.backends import AnalyticsBackend
from app.core.logging import get_logger
from app.graph.client import GraphClient

log = get_logger(__name__)

WRITE_BATCH = 5000

_DROP_COLLAB = "MATCH ()-[r:COLLABORATED_WITH]->() DELETE r"
_BUILD_COLLAB = """
MATCH (a:Author)-[:WROTE]->(p:Paper)<-[:WROTE]-(b:Author)
WHERE a.id < b.id
WITH a, b, count(DISTINCT p) AS weight
CREATE (a)-[:COLLABORATED_WITH {weight: weight, source: 'derived'}]->(b)
RETURN count(*) AS n
"""
_DROP_RELATED = "MATCH (:Topic)-[r:RELATED_TO]->(:Topic) DELETE r"
_BUILD_RELATED = """
MATCH (t1:Topic)<-[:HAS_TOPIC]-(p:Paper)-[:HAS_TOPIC]->(t2:Topic)
WHERE t1.id < t2.id
WITH t1, t2, count(DISTINCT p) AS weight
WHERE weight >= $min_weight
CREATE (t1)-[:RELATED_TO {weight: weight, source: 'derived'}]->(t2)
RETURN count(*) AS n
"""

_PAPER_DEGREES = """
MATCH (p:Paper)
RETURN p.id AS id,
       COUNT { (:Paper)-[:CITES]->(p) } AS in_degree,
       COUNT { (p)-[:CITES]->(:Paper) } AS out_degree
"""
_WRITE_PAPER_METRICS = """
UNWIND $rows AS r
MATCH (p:Paper {id: r.id})
SET p.pagerank = r.pagerank,
    p.betweenness = r.betweenness,
    p.in_degree = r.in_degree,
    p.out_degree = r.out_degree,
    p.analytics_computed_at = datetime($computed_at)
"""
_AUTHOR_STATS = """
MATCH (a:Author)
RETURN a.id AS id,
       COUNT { (a)-[:WROTE]->(:Paper) } AS paper_count,
       COUNT { (a)-[:COLLABORATED_WITH]-(:Author) } AS collaborator_count
"""
_WRITE_AUTHOR_METRICS = """
UNWIND $rows AS r
MATCH (a:Author {id: r.id})
SET a.pagerank = r.pagerank,
    a.betweenness = r.betweenness,
    a.paper_count = r.paper_count,
    a.collaborator_count = r.collaborator_count,
    a.analytics_computed_at = datetime($computed_at)
"""

_CLEAR_COMMUNITIES = "MATCH (c:Community {scope: $scope}) DETACH DELETE c"
_CLEAR_PAPER_MEMBERSHIP = "MATCH (p:Paper) WHERE p.community_id IS NOT NULL REMOVE p.community_id"
_CLEAR_AUTHOR_MEMBERSHIP = "MATCH (a:Author) WHERE a.community_id IS NOT NULL REMOVE a.community_id"
_CREATE_COMMUNITIES = """
UNWIND $rows AS r
CREATE (:Community {id: r.id, scope: $scope, algorithm: $algorithm, rank: r.rank,
                    size: r.size, computed_at: datetime($computed_at)})
"""
_ASSIGN: dict[str, LiteralString] = {
    "papers": """
        UNWIND $rows AS r
        MATCH (n:Paper {id: r.node}), (c:Community {id: r.community})
        SET n.community_id = r.community
        CREATE (n)-[:IN_COMMUNITY]->(c)""",
    "authors": """
        UNWIND $rows AS r
        MATCH (n:Author {id: r.node}), (c:Community {id: r.community})
        SET n.community_id = r.community
        CREATE (n)-[:IN_COMMUNITY]->(c)""",
}
_SUMMARISE: dict[str, LiteralString] = {
    "papers": """
        MATCH (c:Community {scope: 'papers'})
        WITH c, COLLECT {
            MATCH (c)<-[:IN_COMMUNITY]-(:Paper)-[:HAS_TOPIC]->(t:Topic)
            WITH t, count(*) AS n ORDER BY n DESC, t.name LIMIT 5
            RETURN t.name
        } AS topics
        SET c.top_topics = topics, c.label = CASE WHEN size(topics) > 0 THEN topics[0] END""",
    "authors": """
        MATCH (c:Community {scope: 'authors'})
        WITH c, COLLECT {
            MATCH (c)<-[:IN_COMMUNITY]-(:Author)-[:WROTE]->(:Paper)-[:HAS_TOPIC]->(t:Topic)
            WITH t, count(*) AS n ORDER BY n DESC, t.name LIMIT 5
            RETURN t.name
        } AS topics
        SET c.top_topics = topics, c.label = CASE WHEN size(topics) > 0 THEN topics[0] END""",
}


@dataclass(frozen=True)
class AnalyticsOptions:
    community_algorithm: CommunityAlgorithm = "louvain"
    # Communities smaller than this are not materialised (members get no community_id).
    min_community_size: int = 3
    # Exact betweenness up to this many nodes; sampled estimate above it.
    exact_betweenness_max_nodes: int = 5000
    betweenness_sample_size: int = 500
    related_topics_min_weight: int = 1


@dataclass
class AnalyticsReport:
    backend: str
    computed_at: str
    options: dict[str, Any]
    papers: int = 0
    authors: int = 0
    collaboration_edges: int = 0
    related_topic_edges: int = 0
    paper_communities: int = 0
    author_communities: int = 0
    largest_paper_communities: list[int] = field(default_factory=list)
    betweenness_sampled: dict[str, bool] = field(default_factory=dict)
    durations_ms: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class AnalyticsService:
    def __init__(
        self,
        graph: GraphClient,
        backend: AnalyticsBackend,
        options: AnalyticsOptions | None = None,
    ) -> None:
        self._graph = graph
        self._backend = backend
        self._options = options or AnalyticsOptions()

    async def run(self) -> AnalyticsReport:
        computed_at = datetime.now(UTC).isoformat()
        report = AnalyticsReport(
            backend=self._backend.name, computed_at=computed_at, options=asdict(self._options)
        )
        try:
            await self._timed(report, "derived_edges", self._derived_edges(report))
            await self._timed(report, "papers", self._papers(report, computed_at))
            await self._timed(report, "authors", self._authors(report, computed_at))
            await self._timed(report, "community_summaries", self._summaries())
        finally:
            await self._backend.close()
        log.info(
            "analytics.completed", **{k: v for k, v in report.as_dict().items() if k != "options"}
        )
        return report

    async def _timed(self, report: AnalyticsReport, step: str, work: Any) -> None:
        start = time.perf_counter()
        await work
        report.durations_ms[step] = round((time.perf_counter() - start) * 1000, 1)
        log.info("analytics.step_done", step=step, ms=report.durations_ms[step])

    async def _derived_edges(self, report: AnalyticsReport) -> None:
        await self._graph.write(_DROP_COLLAB, label="analytics.drop_collab")
        rows = await self._graph.write(_BUILD_COLLAB, label="analytics.build_collab")
        report.collaboration_edges = int(rows[0]["n"]) if rows else 0
        await self._graph.write(_DROP_RELATED, label="analytics.drop_related")
        rows = await self._graph.write(
            _BUILD_RELATED,
            {"min_weight": self._options.related_topics_min_weight},
            label="analytics.build_related",
        )
        report.related_topic_edges = int(rows[0]["n"]) if rows else 0

    def _sample_size(self, nodes: int) -> int | None:
        if nodes <= self._options.exact_betweenness_max_nodes:
            return None
        return self._options.betweenness_sample_size

    async def _papers(self, report: AnalyticsReport, computed_at: str) -> None:
        degrees = await self._graph.read(_PAPER_DEGREES, label="analytics.paper_degrees")
        report.papers = len(degrees)
        if not degrees:
            return
        sample = self._sample_size(len(degrees))
        report.betweenness_sampled["papers"] = sample is not None
        pagerank = await self._backend.pagerank("citations")
        betweenness = await self._backend.betweenness("citations", sample)
        rows = [
            {
                "id": d["id"],
                "in_degree": d["in_degree"],
                "out_degree": d["out_degree"],
                "pagerank": pagerank.get(d["id"]),
                "betweenness": betweenness.get(d["id"]),
            }
            for d in degrees
        ]
        await self._write_batches(
            _WRITE_PAPER_METRICS, rows, computed_at, "analytics.paper_metrics"
        )
        assignment = await self._backend.communities("citations", self._options.community_algorithm)
        sizes = await self._write_communities("papers", assignment, computed_at)
        report.paper_communities = len(sizes)
        report.largest_paper_communities = sizes[:10]

    async def _authors(self, report: AnalyticsReport, computed_at: str) -> None:
        stats = await self._graph.read(_AUTHOR_STATS, label="analytics.author_stats")
        report.authors = len(stats)
        if not stats:
            return
        sample = self._sample_size(len(stats))
        report.betweenness_sampled["authors"] = sample is not None
        pagerank = await self._backend.pagerank("collaboration")
        betweenness = await self._backend.betweenness("collaboration", sample)
        rows = [
            {
                **s,
                "pagerank": pagerank.get(s["id"]),
                "betweenness": betweenness.get(s["id"]),
            }
            for s in stats
        ]
        await self._write_batches(
            _WRITE_AUTHOR_METRICS, rows, computed_at, "analytics.author_metrics"
        )
        assignment = await self._backend.communities(
            "collaboration", self._options.community_algorithm
        )
        report.author_communities = len(
            await self._write_communities("authors", assignment, computed_at)
        )

    async def _write_communities(
        self, scope: Literal["papers", "authors"], assignment: dict[str, int], computed_at: str
    ) -> list[int]:
        """Materialise communities of at least ``min_community_size``; returns their sizes."""
        await self._graph.write(_CLEAR_COMMUNITIES, {"scope": scope}, label="analytics.clear")
        clear = _CLEAR_PAPER_MEMBERSHIP if scope == "papers" else _CLEAR_AUTHOR_MEMBERSHIP
        await self._graph.write(clear, label="analytics.clear_membership")

        sizes = Counter(assignment.values())
        kept = sorted(
            (c for c, n in sizes.items() if n >= self._options.min_community_size),
            key=lambda c: (-sizes[c], c),
        )
        ids = {c: f"community:{scope}:{rank}" for rank, c in enumerate(kept)}
        await self._graph.write(
            _CREATE_COMMUNITIES,
            {
                "rows": [
                    {"id": ids[c], "rank": rank, "size": sizes[c]} for rank, c in enumerate(kept)
                ],
                "scope": scope,
                "algorithm": self._options.community_algorithm,
                "computed_at": computed_at,
            },
            label="analytics.create_communities",
        )
        members = [
            {"node": node, "community": ids[c]} for node, c in assignment.items() if c in ids
        ]
        for start in range(0, len(members), WRITE_BATCH):
            await self._graph.write(
                _ASSIGN[scope],
                {"rows": members[start : start + WRITE_BATCH]},
                label="analytics.assign",
            )
        return [sizes[c] for c in kept]

    async def _summaries(self) -> None:
        for scope in ("papers", "authors"):
            await self._graph.write(_SUMMARISE[scope], label=f"analytics.summarise.{scope}")

    async def _write_batches(
        self, query: LiteralString, rows: list[dict[str, Any]], computed_at: str, label: str
    ) -> None:
        for start in range(0, len(rows), WRITE_BATCH):
            await self._graph.write(
                query,
                {"rows": rows[start : start + WRITE_BATCH], "computed_at": computed_at},
                label=label,
            )
