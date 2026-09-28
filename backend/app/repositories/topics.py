"""Read access to topics."""

from __future__ import annotations

from app.core.errors import NotFoundError
from app.graph.client import GraphClient
from app.repositories.papers import SUMMARY, summary_from_row
from app.schemas.common import Page, PageParams
from app.schemas.graph import AuthorActivity, RelatedTopic, TopicDetail, TopicListItem

_TOPIC = """
MATCH (t:Topic {id: $id})
RETURN t {.id, .name, .description} AS topic,
COUNT { (:Paper)-[:HAS_TOPIC]->(t) } AS paper_count,
COLLECT {
    MATCH (t)<-[:HAS_TOPIC]-(:Paper)-[:HAS_TOPIC]->(o:Topic)
    WHERE o <> t
    WITH o, count(*) AS shared
    RETURN {id: o.id, name: o.name, shared_papers: shared}
    ORDER BY shared DESC, o.name LIMIT 20
} AS related,
COLLECT {
    MATCH (t)<-[:HAS_TOPIC]-(:Paper)<-[:WROTE]-(a:Author)
    WITH a, count(*) AS n
    RETURN {id: a.id, name: a.name, paper_count: n}
    ORDER BY n DESC, a.name LIMIT 20
} AS authors,
COLLECT {
    MATCH (t)<-[:HAS_TOPIC]-(p:Paper) WHERE p.year IS NOT NULL
    WITH p.year AS year, count(*) AS n
    RETURN [year, n] ORDER BY year
} AS per_year
"""

_TOP_PAPERS = (
    """
MATCH (:Topic {id: $id})<-[:HAS_TOPIC]-(p:Paper)
WITH p ORDER BY coalesce(p.pagerank, 0.0) DESC, COUNT { (:Paper)-[:CITES]->(p) } DESC
LIMIT $limit
RETURN """
    + SUMMARY
)


class TopicRepository:
    def __init__(self, graph: GraphClient) -> None:
        self._graph = graph

    async def get(self, topic_id: str, *, paper_limit: int = 20) -> TopicDetail:
        rows = await self._graph.read(_TOPIC, {"id": topic_id}, label="topics.get")
        if not rows:
            raise NotFoundError(f"Topic {topic_id!r} not found")
        row = rows[0]
        papers = await self._graph.read(
            _TOP_PAPERS, {"id": topic_id, "limit": paper_limit}, label="topics.papers"
        )
        return TopicDetail(
            id=row["topic"]["id"],
            name=row["topic"]["name"],
            description=row["topic"].get("description"),
            paper_count=row["paper_count"],
            related_topics=[RelatedTopic.model_validate(r) for r in row["related"]],
            top_authors=[AuthorActivity.model_validate(a) for a in row["authors"]],
            papers_per_year={int(y): int(n) for y, n in row["per_year"]},
            top_papers=[summary_from_row(p) for p in papers],
        )

    async def list(self, page: PageParams) -> Page[TopicListItem]:
        rows = await self._graph.read(
            """
            MATCH (t:Topic)
            WITH t, COUNT { (:Paper)-[:HAS_TOPIC]->(t) } AS n
            ORDER BY n DESC, t.name SKIP $skip LIMIT $limit
            RETURN t.id AS id, t.name AS name, n AS paper_count
            """,
            {"skip": page.skip, "limit": page.page_size},
            label="topics.list",
        )
        total = await self._graph.read("MATCH (t:Topic) RETURN count(t) AS total")
        return Page(
            items=[TopicListItem.model_validate(r) for r in rows],
            total=total[0]["total"],
            page=page.page,
            page_size=page.page_size,
        )
