"""Natural-language question -> validated, read-only Cypher -> rows.

Safety layers, all of which must pass before any rows are read (ADR-009):
1. ``validate_cypher``: static allow-list (read clauses, known schema, bounded paths, LIMIT).
2. ``EXPLAIN``: Neo4j itself must classify the query as read-only ("r") and parse it.
3. Execution in a read transaction with a server-side timeout and a row cap.
Rejections are fed back to the model once so it can repair its own query.
"""

from __future__ import annotations

from typing import Any

from neo4j.exceptions import Neo4jError

from app.ai.llm import LLMProvider, Message, complete_structured
from app.ai.text2cypher import CypherDraft, build_messages
from app.core.errors import ResearchGraphError, ValidationFailedError
from app.core.logging import get_logger
from app.graph.client import GraphClient
from app.graph.cypher_guard import MAX_ROWS, CypherRejectedError, ValidatedQuery, validate_cypher
from app.schemas.nlquery import NLQueryResponse

log = get_logger(__name__)

QUERY_TIMEOUT_SECONDS = 10.0
MAX_ATTEMPTS = 2
MAX_CELL_CHARS = 300
MAX_LIST_ITEMS = 25
_HIDDEN_KEYS = frozenset({"embedding", "insight_json"})


def clean_value(value: Any, depth: int = 0) -> Any:
    """Make a Neo4j value JSON-safe and small: no vectors, bounded strings and lists."""
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return value if len(value) <= MAX_CELL_CHARS else value[: MAX_CELL_CHARS - 1] + "…"
    if depth >= 3:
        return None
    if isinstance(value, dict):
        return {k: clean_value(v, depth + 1) for k, v in value.items() if k not in _HIDDEN_KEYS}
    if isinstance(value, list | tuple):
        return [clean_value(v, depth + 1) for v in list(value)[:MAX_LIST_ITEMS]]
    return clean_value(str(value), depth)  # dates, durations, points


async def _check_with_neo4j(graph: GraphClient, cypher: str) -> None:
    try:
        kind = await graph.query_type(cypher)
    except Neo4jError as exc:
        detail = (exc.message or "invalid query").splitlines()[0][:200]
        raise CypherRejectedError(f"Neo4j could not parse the query: {detail}") from exc
    if kind != "r":
        raise CypherRejectedError("Neo4j classified the query as not read-only.")


async def _draft_and_validate(
    graph: GraphClient, llm: LLMProvider, question: str
) -> tuple[CypherDraft, ValidatedQuery | None, int, str]:
    messages = build_messages(question)
    model = llm.model
    last_error = "no attempt"
    draft = CypherDraft()
    for attempt in range(1, MAX_ATTEMPTS + 1):
        draft, completion = await complete_structured(llm, messages, CypherDraft, max_tokens=600)
        model = completion.model
        if not draft.can_answer:
            return draft, None, attempt, model
        try:
            checked = validate_cypher(draft.cypher)
            await _check_with_neo4j(graph, checked.cypher)
            return draft, checked, attempt, model
        except CypherRejectedError as exc:
            last_error = exc.message
            log.warning("nlquery.rejected", attempt=attempt, reason=last_error[:120])
            messages = [
                *messages,
                Message("assistant", draft.model_dump_json()),
                Message(
                    "user",
                    f"That query was rejected: {last_error} Write a corrected query and reply "
                    "with the same JSON shape.",
                ),
            ]
    raise ValidationFailedError(
        f"Could not produce a safe query for this question ({last_error}). "
        "Try rephrasing it more specifically."
    )


async def ask_graph(graph: GraphClient, llm: LLMProvider, question: str) -> NLQueryResponse:
    question = " ".join(question.split())
    draft, checked, attempts, model = await _draft_and_validate(graph, llm, question)
    if checked is None:
        return NLQueryResponse(
            question=question,
            answerable=False,
            message=draft.explanation or "This question cannot be answered from the graph.",
            attempts=attempts,
            model=model,
        )
    try:
        records = await graph.run_readonly_unchecked(
            checked.cypher, label="nlquery.run", tx_timeout=QUERY_TIMEOUT_SECONDS
        )
    except Neo4jError as exc:
        # Includes the server-side timeout. Details stay in the log, not the response.
        log.warning("nlquery.execution_failed", code=exc.code)
        raise ValidationFailedError(
            "The query failed or took too long to run. Try a narrower question."
        ) from exc
    except ResearchGraphError:
        raise
    rows = [{k: clean_value(v) for k, v in record.items()} for record in records[:MAX_ROWS]]
    columns = list(rows[0]) if rows else []
    return NLQueryResponse(
        question=question,
        cypher=checked.cypher,
        explanation=draft.explanation or None,
        columns=columns,
        rows=rows,
        row_count=len(rows),
        truncated=len(records) >= checked.limit,
        attempts=attempts,
        model=model,
    )
