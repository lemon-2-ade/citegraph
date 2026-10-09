"""Generate, cache and serve LLM paper insights."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass

from app.ai.insights import PaperInsight, extract_insight, insight_hash, insight_input
from app.ai.llm import LLMProvider
from app.core.errors import NotFoundError, ValidationFailedError
from app.core.logging import get_logger
from app.graph.client import GraphClient
from app.repositories.insights import InsightRepository
from app.schemas.insights import PaperInsightResult

log = get_logger(__name__)


def _result(row: dict, insight: PaperInsight, *, stale: bool, cached: bool) -> PaperInsightResult:  # type: ignore[type-arg]
    return PaperInsightResult(
        paper_id=row["id"],
        insight=insight,
        model=row["model"],
        generated_at=row["generated_at"],
        stale=stale,
        cached=cached,
    )


async def get_insight(graph: GraphClient, paper_id: str) -> PaperInsightResult:
    """Return the cached insight; 404 when none has been generated yet."""
    row = await InsightRepository(graph).get(paper_id)
    if not row.get("insight_json"):
        raise NotFoundError(f"No insight generated yet for {paper_id!r}")
    text = insight_input(row["title"], row["abstract"], row["description"])
    stale = row["hash"] != insight_hash(text)
    return _result(
        row, PaperInsight.model_validate_json(row["insight_json"]), stale=stale, cached=True
    )


async def generate_insight(
    graph: GraphClient, llm: LLMProvider, paper_id: str, *, force: bool = False
) -> PaperInsightResult:
    repo = InsightRepository(graph)
    row = await repo.get(paper_id)
    text = insight_input(row["title"], row["abstract"], row["description"])
    if not (row["abstract"] or row["description"]):
        raise ValidationFailedError("This paper has no abstract to analyse.")
    digest = insight_hash(text)
    if not force and row.get("insight_json") and row["hash"] == digest:
        return _result(row, PaperInsight.model_validate_json(row["insight_json"]),
                       stale=False, cached=True)  # fmt: skip
    insight, completion = await extract_insight(llm, row["title"], text)
    generated_at = await repo.store(
        paper_id, json=insight.model_dump_json(), hash=digest, model=completion.model
    )
    log.info("insight.generated", paper_id=paper_id, model=completion.model,
             prompt_tokens=completion.prompt_tokens)  # fmt: skip
    return PaperInsightResult(
        paper_id=paper_id, insight=insight, model=completion.model,
        generated_at=generated_at, stale=False, cached=False,
    )  # fmt: skip


@dataclass
class InsightStats:
    model: str
    scanned: int = 0
    generated: int = 0
    unchanged: int = 0
    without_text: int = 0
    failed: int = 0

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


async def generate_insights(
    graph: GraphClient,
    llm: LLMProvider,
    *,
    limit: int | None = None,
    force: bool = False,
    concurrency: int = 4,
    batch_size: int = 50,
) -> InsightStats:
    """Generate insights for papers that lack a current one. Resumable and idempotent.

    One paper failing (bad model output, a transient API error) is counted and skipped, so a
    long run is not lost to a single bad response.
    """
    repo = InsightRepository(graph)
    stats = InsightStats(model=llm.model)
    gate = asyncio.Semaphore(max(1, concurrency))

    async def one(paper_id: str) -> None:
        async with gate:
            try:
                await generate_insight(graph, llm, paper_id, force=force)
                stats.generated += 1
            except Exception as exc:
                stats.failed += 1
                log.warning("insight.failed", paper_id=paper_id, error=type(exc).__name__)

    after = ""
    while limit is None or stats.generated + stats.failed < limit:
        batch = await repo.candidates(after, batch_size)
        if not batch:
            break
        after = batch[-1]["id"]
        todo: list[str] = []
        for row in batch:
            stats.scanned += 1
            if not (row["abstract"] or row["description"]):
                stats.without_text += 1
                continue
            digest = insight_hash(insight_input(row["title"], row["abstract"], row["description"]))
            if not force and row["hash"] == digest:
                stats.unchanged += 1
                continue
            todo.append(row["id"])
        if limit is not None:
            todo = todo[: max(0, limit - stats.generated - stats.failed)]
        await asyncio.gather(*(one(pid) for pid in todo))
    return stats
