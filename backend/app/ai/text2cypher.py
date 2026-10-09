"""Prompt and examples for translating a question into read-only Cypher.

The example queries are module-level constants so the Cypher linter checks them against
Neo4j's grammar, and a unit test checks that each passes the validator.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field

from app.ai.llm import Message
from app.graph.cypher_guard import MAX_HOPS, MAX_ROWS

EXAMPLE_CITING = """
MATCH (c:Paper)-[:CITES]->(p:Paper)
WHERE toLower(p.title) CONTAINS 'attention is all you need'
RETURN c.title AS citing_paper, c.year AS year
ORDER BY c.year DESC
LIMIT 25
"""

EXAMPLE_AUTHORS = """
MATCH (a:Author)-[:WROTE]->(p:Paper)
WHERE coalesce(p.is_stub, false) = false
WITH a, count(p) AS papers, sum(coalesce(p.pagerank, 0.0)) AS influence
RETURN a.name AS author, papers, round(influence * 1000) / 1000 AS influence
ORDER BY influence DESC
LIMIT 10
"""

EXAMPLE_TREND = """
MATCH (p:Paper)-[:HAS_TOPIC]->(t:Topic)
WHERE toLower(t.name) CONTAINS 'graph' AND p.year IS NOT NULL
RETURN p.year AS year, count(DISTINCT p) AS papers
ORDER BY year
LIMIT 50
"""

EXAMPLE_COLLAB = """
MATCH (a:Author)-[c:COLLABORATED_WITH]-(b:Author)
WHERE toLower(a.name) CONTAINS 'hinton'
RETURN b.name AS collaborator, c.weight AS joint_papers
ORDER BY joint_papers DESC
LIMIT 20
"""

EXAMPLES: list[tuple[str, str]] = [
    ("Which papers cite 'Attention Is All You Need'?", EXAMPLE_CITING),
    ("Who are the most influential authors?", EXAMPLE_AUTHORS),
    ("How many papers per year are about graphs?", EXAMPLE_TREND),
    ("Who has collaborated with Hinton the most?", EXAMPLE_COLLAB),
]

SCHEMA = """Node labels and properties:
- Paper: id, title, abstract, description, year, doi, arxiv_id, url, language, citation_count, \
is_stub, pagerank, betweenness, in_degree, out_degree, community_id
- Author: id, name, orcid
- Institution: id, name, country, ror
- Venue: id, name, type
- Topic: id, name, description
- Keyword: id, name
- Community: id, algorithm, size, computed_at

Relationships:
- (:Paper)-[:CITES]->(:Paper)            the first paper cites the second
- (:Author)-[:WROTE {position}]->(:Paper)
- (:Author)-[:AFFILIATED_WITH]->(:Institution)
- (:Paper)-[:PUBLISHED_IN]->(:Venue)
- (:Paper)-[:HAS_TOPIC {score}]->(:Topic)
- (:Paper)-[:HAS_KEYWORD]->(:Keyword)
- (:Author)-[:COLLABORATED_WITH {weight}]-(:Author)   weight = number of joint papers
- (:Topic)-[:RELATED_TO {weight}]-(:Topic)
- (:Paper)-[:IN_COMMUNITY]->(:Community)"""

RULES = f"""Rules:
- Write ONE read-only Cypher query. Only MATCH, OPTIONAL MATCH, WITH, UNWIND, WHERE, RETURN, \
ORDER BY, SKIP and LIMIT. No CREATE/MERGE/SET/DELETE, no CALL, no UNION, no comments.
- Use only the labels, relationship types and properties listed above.
- No query parameters: write values as literals. Match names and titles case-insensitively \
with toLower(x) CONTAINS 'text'.
- Variable-length paths must be bounded, like [:CITES*1..{MAX_HOPS}].
- End with LIMIT (at most {MAX_ROWS}). Return readable columns with AS aliases, not whole nodes.
- Papers with is_stub = true have no metadata; exclude them unless asked.
- pagerank and the other graph metrics only exist after analytics has run, so wrap them in \
coalesce(..., 0.0) when sorting.
- If the question cannot be answered from this schema (for example it asks about something \
that is not stored), set "can_answer" to false and explain why in "explanation"."""


def _text(value: object) -> object:
    return " ".join(value.split()) if isinstance(value, str) else value


class CypherDraft(BaseModel):
    can_answer: bool = True
    cypher: Annotated[str, BeforeValidator(lambda v: v.strip() if isinstance(v, str) else v)] = ""
    explanation: Annotated[str, BeforeValidator(_text), Field(max_length=600)] = ""


def build_messages(question: str) -> list[Message]:
    shots = "\n\n".join(f"Question: {q}\n{c.strip()}" for q, c in EXAMPLES)
    system = (
        "You translate questions about a research-paper knowledge graph into Cypher for "
        "Neo4j 5.\n\n"
        f"{SCHEMA}\n\n{RULES}\n\nExamples of valid queries:\n\n{shots}\n\n"
        'Reply with one JSON object: {"can_answer": boolean, "cypher": string, '
        '"explanation": string (one or two plain sentences saying what the query returns)}.'
    )
    return [Message("system", system), Message("user", f"Question: {question}")]
