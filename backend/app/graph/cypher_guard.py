"""Static validation of model-written Cypher before it can touch the database.

This is one of three independent layers (ADR-009): this validator, Neo4j's own ``EXPLAIN``
query type, and a read-only transaction with a timeout. The validator is deliberately
conservative: it accepts a small read-only subset and rejects everything else, with messages
written to be fed back to the model for a repair attempt (so they never echo model text that
could carry instructions beyond a short identifier).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.errors import ValidationFailedError

MAX_QUERY_CHARS = 1500
MAX_ROWS = 100
DEFAULT_ROWS = 50
MAX_HOPS = 4

NODE_LABELS = frozenset(
    {"Paper", "Author", "Institution", "Venue", "Topic", "Keyword", "Community"}
)
REL_TYPES = frozenset(
    {
        "CITES", "WROTE", "AFFILIATED_WITH", "PUBLISHED_IN", "HAS_TOPIC", "HAS_KEYWORD",
        "COLLABORATED_WITH", "RELATED_TO", "IN_COMMUNITY",
    }
)  # fmt: skip
# Properties the model may read. Embedding vectors and cached model output are excluded.
PROPERTIES = frozenset(
    {
        "id", "title", "title_key", "abstract", "description", "year", "publication_date", "doi",
        "openalex_id", "arxiv_id", "s2_id", "url", "language", "citation_count",
        "authors_complete", "is_stub", "sources", "pagerank", "betweenness", "in_degree",
        "out_degree", "community_id", "name", "orcid", "country", "ror", "type", "algorithm",
        "size", "computed_at", "position", "source", "confidence", "score", "weight",
    }
)  # fmt: skip
FULLTEXT_INDEXES = frozenset({"paper_text", "author_name", "topic_text"})

_FORBIDDEN = frozenset(
    {
        "CREATE", "MERGE", "DELETE", "DETACH", "SET", "REMOVE", "DROP", "LOAD", "FOREACH",
        "CSV", "SHOW", "TERMINATE", "GRANT", "DENY", "REVOKE", "ALTER", "RENAME", "START",
        "STOP", "USE", "PROFILE", "EXPLAIN", "USING", "INDEX", "CONSTRAINT", "DATABASE",
        "APOC", "DBMS", "UNION",
    }
)  # fmt: skip
_FIRST = frozenset({"MATCH", "OPTIONAL", "WITH", "UNWIND", "RETURN", "CALL"})
_NAMESPACES = frozenset(
    {"date", "datetime", "duration", "time", "localtime", "localdatetime", "point", "db"}
)


class CypherRejectedError(ValidationFailedError):
    code = "cypher_rejected"


@dataclass(frozen=True)
class ValidatedQuery:
    cypher: str
    limit: int
    labels: frozenset[str]
    rel_types: frozenset[str]


def _mask(text: str) -> str:
    """Blank out string literals, so keyword scans cannot be fooled by (or trip on) text."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch in "'\"":
            quote = ch
            out.append(quote)
            i += 1
            while i < n and text[i] != quote:
                i += 2 if text[i] == "\\" else 1
                out.append(" ")
            if i >= n:
                raise CypherRejectedError("Unterminated string literal.")
            out.append(quote)
            i += 1
            continue
        if text.startswith("//", i) or text.startswith("/*", i):
            raise CypherRejectedError("Comments are not allowed.")
        out.append(ch)
        i += 1
    return "".join(out)


def validate_cypher(raw: str) -> ValidatedQuery:
    text = raw.strip().rstrip(";").strip()
    if not text:
        raise CypherRejectedError("The query is empty.")
    if len(text) > MAX_QUERY_CHARS:
        raise CypherRejectedError(f"The query is longer than {MAX_QUERY_CHARS} characters.")
    if "`" in text:
        raise CypherRejectedError("Backtick-quoted identifiers are not allowed.")
    masked = _mask(text)
    if ";" in masked:
        raise CypherRejectedError("Only a single statement is allowed.")
    if "$" in masked:
        raise CypherRejectedError("Query parameters are not allowed; write literal values.")

    upper = masked.upper()
    words = re.findall(r"(?<![.\w])[A-Z_][A-Z0-9_]*", upper)
    if not words or words[0] not in _FIRST:
        raise CypherRejectedError(
            "The query must start with MATCH, OPTIONAL MATCH, WITH or UNWIND."
        )
    bad = sorted(set(words) & _FORBIDDEN)
    if bad:
        raise CypherRejectedError(f"Not allowed in read-only queries: {', '.join(bad)}.")
    if "RETURN" not in words:
        raise CypherRejectedError("The query must end with a RETURN clause.")

    for call in re.finditer(r"\bCALL\b\s*(\{|[\w.]+)", masked, flags=re.IGNORECASE):
        if call.group(1) == "{":
            continue
        name = re.sub(r"\s+", "", call.group(1)).lower()
        index = re.search(r"queryNodes\(\s*['\"](\w+)['\"]", text)
        if (
            name != "db.index.fulltext.querynodes"
            or not index
            or (index.group(1) not in FULLTEXT_INDEXES)
        ):
            raise CypherRejectedError(
                "Only CALL db.index.fulltext.queryNodes on paper_text, author_name or "
                "topic_text is allowed."
            )

    labels = _labels(masked)
    rel_types = _rel_types(masked)
    unknown_labels = sorted(labels - NODE_LABELS)
    if unknown_labels:
        raise CypherRejectedError(
            f"Unknown node label(s): {', '.join(unknown_labels)}. "
            f"Use only: {', '.join(sorted(NODE_LABELS))}."
        )
    unknown_rels = sorted(rel_types - REL_TYPES)
    if unknown_rels:
        raise CypherRejectedError(
            f"Unknown relationship type(s): {', '.join(unknown_rels)}. "
            f"Use only: {', '.join(sorted(REL_TYPES))}."
        )

    for match in re.finditer(r"(?<![\w.])([A-Za-z_]\w*)\s*\.\s*([A-Za-z_]\w*)", masked):
        owner, prop = match.group(1), match.group(2)
        if owner.lower() in _NAMESPACES:
            continue
        if prop not in PROPERTIES:
            raise CypherRejectedError(f"Unknown property '{prop}'.")

    _check_hops(masked)
    return _bound_rows(text, masked, labels, rel_types)


def _labels(masked: str) -> frozenset[str]:
    found: set[str] = set()
    for m in re.finditer(r"\(\s*[A-Za-z_]\w*?\s*((?::\s*\w+\s*)+)", masked):
        found.update(re.findall(r":\s*(\w+)", m.group(1)))
    for m in re.finditer(r"\(\s*((?::\s*\w+\s*)+)", masked):
        found.update(re.findall(r":\s*(\w+)", m.group(1)))
    return frozenset(found)


def _rel_types(masked: str) -> frozenset[str]:
    found: set[str] = set()
    for m in re.finditer(r"\[\s*\w*\s*:\s*([\w|:\s]+)", masked):
        found.update(t for t in re.split(r"[|:\s]+", m.group(1)) if t)
    return frozenset(found)


def _check_hops(masked: str) -> None:
    for m in re.finditer(r"\[\s*\w*\s*(?::[\w|:\s]+)?\s*\*([^\]]*)\]", masked):
        spec = m.group(1).replace(" ", "")
        bounds = re.fullmatch(r"(\d*)(\.\.)?(\d*)", spec.split("{", 1)[0])
        if not bounds:
            raise CypherRejectedError("Variable-length paths must look like *1..3.")
        low, dots, high = bounds.groups()
        upper = high if dots else low
        if not upper or int(upper) > MAX_HOPS:
            raise CypherRejectedError(
                f"Variable-length paths must be bounded to at most {MAX_HOPS} hops."
            )


def _bound_rows(
    text: str, masked: str, labels: frozenset[str], rel_types: frozenset[str]
) -> ValidatedQuery:
    limits = [int(x) for x in re.findall(r"\bLIMIT\s+(\d+)\b", masked, flags=re.IGNORECASE)]
    if any(v > MAX_ROWS for v in limits):
        raise CypherRejectedError(f"LIMIT must be at most {MAX_ROWS}.")
    if re.search(r"\bLIMIT\s+\d+\s*$", masked, flags=re.IGNORECASE):
        return ValidatedQuery(text, limits[-1], labels, rel_types)
    if re.search(r"\bLIMIT\b", masked, flags=re.IGNORECASE):
        raise CypherRejectedError("LIMIT must be a plain number at the end of the query.")
    return ValidatedQuery(f"{text}\nLIMIT {DEFAULT_ROWS}", DEFAULT_ROWS, labels, rel_types)
