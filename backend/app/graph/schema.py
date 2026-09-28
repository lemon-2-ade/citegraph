"""Neo4j schema: uniqueness constraints and indexes.

All statements are idempotent (``IF NOT EXISTS``) so ``apply_schema`` can run on every
deployment. See docs/graph-schema.md for the model these statements enforce.
"""

from __future__ import annotations

from typing import LiteralString

from app.core.logging import get_logger
from app.graph.client import GraphClient

log = get_logger(__name__)

# Node labels
PAPER = "Paper"
AUTHOR = "Author"
INSTITUTION = "Institution"
VENUE = "Venue"
TOPIC = "Topic"
KEYWORD = "Keyword"
COMMUNITY = "Community"

CONSTRAINTS: tuple[LiteralString, ...] = (
    # Internal identifiers
    "CREATE CONSTRAINT paper_id IF NOT EXISTS FOR (n:Paper) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT author_id IF NOT EXISTS FOR (n:Author) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT institution_id IF NOT EXISTS FOR (n:Institution) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT venue_id IF NOT EXISTS FOR (n:Venue) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT topic_id IF NOT EXISTS FOR (n:Topic) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT keyword_id IF NOT EXISTS FOR (n:Keyword) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT community_id IF NOT EXISTS FOR (n:Community) REQUIRE n.id IS UNIQUE",
    # External identifiers: the database itself refuses duplicate papers/authors for the
    # same DOI / OpenAlex ID / arXiv ID / ORCID, backing up application-level resolution.
    "CREATE CONSTRAINT paper_doi IF NOT EXISTS FOR (n:Paper) REQUIRE n.doi IS UNIQUE",
    "CREATE CONSTRAINT paper_openalex IF NOT EXISTS FOR (n:Paper) REQUIRE n.openalex_id IS UNIQUE",
    "CREATE CONSTRAINT paper_arxiv IF NOT EXISTS FOR (n:Paper) REQUIRE n.arxiv_id IS UNIQUE",
    "CREATE CONSTRAINT paper_s2 IF NOT EXISTS FOR (n:Paper) REQUIRE n.s2_id IS UNIQUE",
    "CREATE CONSTRAINT paper_seed IF NOT EXISTS FOR (n:Paper) REQUIRE n.seed_key IS UNIQUE",
    "CREATE CONSTRAINT author_orcid IF NOT EXISTS FOR (n:Author) REQUIRE n.orcid IS UNIQUE",
    "CREATE CONSTRAINT author_openalex IF NOT EXISTS "
    "FOR (n:Author) REQUIRE n.openalex_id IS UNIQUE",
)

INDEXES: tuple[LiteralString, ...] = (
    "CREATE INDEX paper_year IF NOT EXISTS FOR (n:Paper) ON (n.year)",
    "CREATE INDEX paper_title_key IF NOT EXISTS FOR (n:Paper) ON (n.title_key)",
    "CREATE INDEX paper_is_stub IF NOT EXISTS FOR (n:Paper) ON (n.is_stub)",
    "CREATE INDEX paper_pagerank IF NOT EXISTS FOR (n:Paper) ON (n.pagerank)",
    "CREATE INDEX author_name_key IF NOT EXISTS FOR (n:Author) ON (n.name_key)",
    "CREATE INDEX topic_name IF NOT EXISTS FOR (n:Topic) ON (n.name)",
    "CREATE INDEX paper_community IF NOT EXISTS FOR (n:Paper) ON (n.community_id)",
    # Full-text (Lucene) indexes for lexical search and name lookup.
    "CREATE FULLTEXT INDEX paper_text IF NOT EXISTS "
    "FOR (n:Paper) ON EACH [n.title, n.abstract, n.description]",
    "CREATE FULLTEXT INDEX author_name IF NOT EXISTS FOR (n:Author) ON EACH [n.name]",
    "CREATE FULLTEXT INDEX topic_text IF NOT EXISTS FOR (n:Topic) ON EACH [n.name, n.description]",
)


async def apply_schema(graph: GraphClient) -> int:
    """Create all constraints and indexes. Returns the number of statements applied."""
    statements = (*CONSTRAINTS, *INDEXES)
    for statement in statements:
        await graph.write(statement, label="schema.apply")
    log.info("neo4j.schema_applied", statements=len(statements))
    return len(statements)
