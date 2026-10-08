"""Lexical search over the full-text indexes (papers, authors, topics).

Semantic search arrives with embeddings in a later phase; this is keyword search with
prefix matching on the last term so results appear while the user is still typing.
"""

from __future__ import annotations

import re
from typing import Any, Literal, LiteralString

from app.graph.client import GraphClient
from app.schemas.graph import SearchHit, SearchResults

# Lucene query syntax characters (and the word operators) that user text must not trigger.
_LUCENE_SPECIAL = re.compile(r'([+\-&|!(){}\[\]^"~*?:\\/])')
_OPERATORS = {"AND", "OR", "NOT"}
MIN_QUERY_LENGTH = 2
MAX_QUERY_LENGTH = 100


def to_lucene(text: str) -> str | None:
    """Turn free text into a safe Lucene query: all terms required, last term a prefix."""
    terms = [
        _LUCENE_SPECIAL.sub(r"\\\1", t)
        for t in text.strip()[:MAX_QUERY_LENGTH].split()
        if t.upper() not in _OPERATORS
    ]
    terms = [t for t in terms if t]
    if not terms or sum(len(t) for t in terms) < MIN_QUERY_LENGTH:
        return None
    terms[-1] += "*"
    return " AND ".join(terms)


_PAPERS: LiteralString = """
CALL db.index.fulltext.queryNodes('paper_text', $q, {limit: $fetch}) YIELD node AS p, score
WHERE coalesce(p.is_stub, false) = false
RETURN p.id AS id, coalesce(p.title, 'Untitled') AS title, score,
       toString(p.year) AS year,
       COLLECT {
           MATCH (a:Author)-[w:WROTE]->(p) RETURN a.name ORDER BY w.position LIMIT 3
       } AS authors
ORDER BY score DESC, id
LIMIT $limit
"""

_AUTHORS: LiteralString = """
CALL db.index.fulltext.queryNodes('author_name', $q, {limit: $fetch}) YIELD node AS a, score
RETURN a.id AS id, a.name AS title, score, COUNT { (a)-[:WROTE]->(:Paper) } AS papers
ORDER BY score DESC, papers DESC, id
LIMIT $limit
"""

_TOPICS: LiteralString = """
CALL db.index.fulltext.queryNodes('topic_text', $q, {limit: $fetch}) YIELD node AS t, score
RETURN t.id AS id, t.name AS title, score, COUNT { (:Paper)-[:HAS_TOPIC]->(t) } AS papers
ORDER BY score DESC, papers DESC, id
LIMIT $limit
"""


class SearchRepository:
    def __init__(self, graph: GraphClient) -> None:
        self._graph = graph

    async def search(self, text: str, limit: int) -> SearchResults:
        query = to_lucene(text)
        if query is None:
            return SearchResults(query=text.strip())
        params = {"q": query, "limit": limit, "fetch": limit * 3}
        papers = await self._graph.read(_PAPERS, params, label="search.papers")
        authors = await self._graph.read(_AUTHORS, params, label="search.authors")
        topics = await self._graph.read(_TOPICS, params, label="search.topics")
        return SearchResults(
            query=text.strip(),
            papers=[_paper_hit(r) for r in papers],
            authors=[_count_hit("author", r) for r in authors],
            topics=[_count_hit("topic", r) for r in topics],
        )


def _paper_hit(row: dict[str, Any]) -> SearchHit:
    parts = [", ".join(row["authors"]) or None, row["year"]]
    return SearchHit(
        kind="paper",
        id=row["id"],
        title=row["title"],
        subtitle=" · ".join(p for p in parts if p) or None,
        score=float(row["score"]),
    )


def _count_hit(kind: Literal["author", "topic"], row: dict[str, Any]) -> SearchHit:
    n = int(row["papers"])
    return SearchHit(
        kind=kind,
        id=row["id"],
        title=row["title"],
        subtitle=f"{n} paper{'s' if n != 1 else ''}",
        score=float(row["score"]),
    )
