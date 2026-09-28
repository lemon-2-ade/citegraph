"""Read access to authors, their papers and collaboration neighbourhood."""

from __future__ import annotations

from app.core.errors import NotFoundError
from app.graph.client import GraphClient
from app.repositories.papers import SUMMARY, summary_from_row
from app.schemas.graph import (
    AuthorDetail,
    CollaboratorRef,
    GraphMetrics,
    InstitutionRef,
    TopicRef,
)

_AUTHOR = """
MATCH (a:Author {id: $id})
RETURN a {.id, .name, .orcid, .openalex_id, .pagerank, .betweenness, .community_id} AS author,
COLLECT {
    MATCH (a)-[:AFFILIATED_WITH]->(i:Institution) RETURN i {.id, .name, .country}
} AS institutions,
COLLECT {
    MATCH (a)-[:WROTE]->(:Paper)<-[:WROTE]-(c:Author)
    WHERE c <> a
    WITH c, count(*) AS shared
    RETURN {id: c.id, name: c.name, shared_papers: shared}
    ORDER BY shared DESC, c.name LIMIT $collaborator_limit
} AS collaborators,
COLLECT {
    MATCH (a)-[:WROTE]->(:Paper)-[:HAS_TOPIC]->(t:Topic)
    WITH t, count(*) AS n
    RETURN {id: t.id, name: t.name, score: toFloat(n)}
    ORDER BY n DESC, t.name LIMIT 15
} AS topics
"""

_AUTHOR_PAPERS = (
    """
MATCH (:Author {id: $id})-[:WROTE]->(p:Paper)
WITH p ORDER BY p.year DESC, p.title LIMIT $paper_limit
RETURN """
    + SUMMARY
)


class AuthorRepository:
    def __init__(self, graph: GraphClient) -> None:
        self._graph = graph

    async def get(
        self, author_id: str, *, paper_limit: int = 100, collaborator_limit: int = 25
    ) -> AuthorDetail:
        rows = await self._graph.read(
            _AUTHOR,
            {"id": author_id, "collaborator_limit": collaborator_limit},
            label="authors.get",
        )
        if not rows:
            raise NotFoundError(f"Author {author_id!r} not found")
        row = rows[0]
        author = row["author"]
        papers = await self._graph.read(
            _AUTHOR_PAPERS, {"id": author_id, "paper_limit": paper_limit}, label="authors.papers"
        )
        return AuthorDetail(
            id=author["id"],
            name=author["name"],
            orcid=author.get("orcid"),
            openalex_id=author.get("openalex_id"),
            institutions=[InstitutionRef.model_validate(i) for i in row["institutions"]],
            collaborators=[CollaboratorRef.model_validate(c) for c in row["collaborators"]],
            # ``score`` here is the number of the author's papers tagged with the topic.
            topics=[TopicRef.model_validate(t) for t in row["topics"]],
            papers=[summary_from_row(p) for p in papers],
            metrics=GraphMetrics(
                pagerank=author.get("pagerank"),
                betweenness=author.get("betweenness"),
                community_id=author.get("community_id"),
            ),
        )
