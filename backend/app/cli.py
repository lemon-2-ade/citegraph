"""``researchgraph`` command-line interface.

researchgraph init                       create Neo4j constraints/indexes and SQL tables
researchgraph seed                       load the curated seed dataset
researchgraph ingest --query "..."       ingest from OpenAlex (inline, or --enqueue)
researchgraph ingest --resume <job-id>   resume a failed/interrupted job
researchgraph jobs                       list recent ingestion jobs
researchgraph embed [--rebuild]          embed papers and build the vector index
researchgraph insights [--limit N]       generate AI summaries/extractions with the LLM
researchgraph eval retrieval|nlquery|rag measure search, NL->Cypher and RAG quality
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from app.ai.embeddings import EmbedderCache, build_provider
from app.ai.llm import build_llm
from app.core.config import get_settings
from app.core.errors import ResearchGraphError
from app.core.logging import configure_logging
from app.core.resources import Resources
from app.db.session import create_tables
from app.evaluation import datasets as eval_data
from app.evaluation import runner as eval_runner
from app.graph.schema import apply_schema
from app.ingestion.pipeline import IngestionParams
from app.ingestion.seed import DEFAULT_SEED_PATH, seed_graph
from app.repositories.analytics_runs import AnalyticsRunRepository
from app.repositories.jobs import JobRepository
from app.services.analytics import execute_run
from app.services.embedding import embed_papers
from app.services.ingestion import SOURCES, create_job, run_job
from app.services.insights import generate_insights

app = typer.Typer(help="ResearchGraph: research intelligence over a citation knowledge graph.")


def _run[T](work: Callable[[Resources], Awaitable[T]]) -> T:
    settings = get_settings()
    configure_logging(settings.log_level, json=False, stream="stderr")

    async def main() -> T:
        resources = Resources.create(settings)
        try:
            return await work(resources)
        finally:
            await resources.close()

    return asyncio.run(main())


@app.command()
def init() -> None:
    """Create Neo4j constraints/indexes and PostgreSQL tables (idempotent)."""

    async def work(r: Resources) -> int:
        await r.graph.verify()
        count = await apply_schema(r.graph)
        await create_tables(r.engine)
        return count

    count = _run(work)
    typer.echo(f"Neo4j schema: {count} constraints/indexes ensured. PostgreSQL tables ensured.")


@app.command()
def seed(
    path: Annotated[Path | None, typer.Option(help="Seed JSON file")] = None,
    batch_size: Annotated[int, typer.Option(min=1, max=1000)] = 50,
) -> None:
    """Load the curated seed dataset into Neo4j (safe to re-run)."""
    settings = get_settings()
    seed_path = path or (Path(settings.seed_path) if settings.seed_path else DEFAULT_SEED_PATH)

    async def work(r: Resources) -> dict[str, int]:
        await apply_schema(r.graph)
        stats = await seed_graph(r.graph, seed_path, batch_size=batch_size)
        return stats.as_dict()

    typer.echo(json.dumps(_run(work), indent=2))


@app.command()
def ingest(
    query: Annotated[str | None, typer.Option(help="Search query sent to the source")] = None,
    source: Annotated[str, typer.Option(help=f"One of: {', '.join(SOURCES)}")] = "openalex",
    max_results: Annotated[int, typer.Option(min=1)] = 200,
    per_page: Annotated[int, typer.Option(min=1, max=200)] = 50,
    year_from: Annotated[int | None, typer.Option()] = None,
    year_to: Annotated[int | None, typer.Option()] = None,
    hydrate: Annotated[
        int, typer.Option(min=0, help="Also fetch metadata for N most-cited referenced papers")
    ] = 0,
    resume: Annotated[str | None, typer.Option(help="Resume an existing job by ID")] = None,
    enqueue: Annotated[
        bool, typer.Option(help="Hand the job to the background worker instead of running here")
    ] = False,
) -> None:
    """Run (or enqueue) an ingestion job. Progress is checkpointed; failed jobs can resume."""
    if resume is None and query is None:
        raise typer.BadParameter("either --query or --resume is required")
    params: IngestionParams | None = None
    if resume is None:
        try:
            params = IngestionParams(
                query=query or "",
                max_results=max_results,
                per_page=per_page,
                year_from=year_from,
                year_to=year_to,
                hydrate_references=hydrate,
            )
        except ValidationError as exc:
            raise typer.BadParameter(str(exc)) from exc

    async def work(r: Resources) -> dict[str, object]:
        await apply_schema(r.graph)
        await create_tables(r.engine)
        if resume is not None:
            job_id = uuid.UUID(resume)
        else:
            assert params is not None
            job_id = (await create_job(r, source, params)).id
        typer.echo(f"job {job_id}")
        if enqueue:
            from arq import create_pool
            from arq.connections import RedisSettings

            from app.workers.tasks import INGESTION_TASK

            pool = await create_pool(RedisSettings.from_dsn(r.settings.redis_url))
            await pool.enqueue_job(INGESTION_TASK, str(job_id), _job_id=f"ingest-{job_id}-cli")
            await pool.aclose()
            return {"job_id": str(job_id), "status": "enqueued"}
        job = await run_job(r, job_id)
        return {"job_id": str(job.id), "status": job.status.value, "stats": job.stats}

    try:
        result = _run(work)
    except Exception as exc:
        typer.echo(f"ingestion failed: {type(exc).__name__}: {exc}", err=True)
        typer.echo("progress was checkpointed; re-run with --resume <job-id>", err=True)
        raise typer.Exit(1) from exc
    typer.echo(json.dumps(result, indent=2, default=str))


@app.command()
def jobs(limit: Annotated[int, typer.Option(min=1, max=200)] = 20) -> None:
    """List recent ingestion jobs."""

    async def work(r: Resources) -> list[str]:
        await create_tables(r.engine)
        rows = await JobRepository(r.sessions).list(limit)
        return [
            f"{j.id}  {j.status.value:<9}  {j.source:<8}  attempts={j.attempts}  "
            f"fetched={j.stats.get('fetched', 0)}  query={j.params.get('query')!r}"
            for j in rows
        ]

    lines = _run(work)
    typer.echo("\n".join(lines) if lines else "no jobs yet")


@app.command()
def analyze(
    backend: Annotated[
        str, typer.Option(help="auto (GDS if installed, else NetworkX), gds or networkx")
    ] = "auto",
    algorithm: Annotated[str, typer.Option(help="louvain or leiden")] = "louvain",
    min_community_size: Annotated[int, typer.Option(min=1)] = 3,
) -> None:
    """Compute PageRank, degree, betweenness and communities and write them to the graph."""
    if backend not in {"auto", "gds", "networkx"}:
        raise typer.BadParameter("backend must be auto, gds or networkx")
    if algorithm not in {"louvain", "leiden"}:
        raise typer.BadParameter("algorithm must be louvain or leiden")

    async def work(r: Resources) -> dict[str, object]:
        await create_tables(r.engine)
        runs = AnalyticsRunRepository(r.sessions)
        run = await runs.create(
            {
                "backend": backend,
                "community_algorithm": algorithm,
                "min_community_size": min_community_size,
            }
        )
        finished = await execute_run(r, run.id)
        return {"run_id": str(finished.id), "status": finished.status.value, **finished.report}

    typer.echo(json.dumps(_run(work), indent=2, default=str))


@app.command()
def embed(
    rebuild: Annotated[
        bool, typer.Option(help="Drop vectors and the index first (required after changing model)")
    ] = False,
    batch_size: Annotated[int | None, typer.Option(min=1, max=512)] = None,
) -> None:
    """Embed papers and build the vector index (incremental; safe to re-run)."""
    settings = get_settings()

    async def work(r: Resources) -> dict[str, object]:
        # Loading a local model is slow and blocking, so build the provider off-loop.
        provider = await asyncio.to_thread(build_provider, settings)
        stats = await embed_papers(
            r.graph,
            provider,
            rebuild=rebuild,
            batch_size=batch_size or settings.embedding_batch_size,
        )
        return stats.as_dict()

    try:
        typer.echo(json.dumps(_run(work), indent=2))
    except ResearchGraphError as exc:
        typer.secho(exc.message, err=True, fg=typer.colors.RED)
        raise typer.Exit(1) from exc


@app.command()
def insights(
    limit: Annotated[int | None, typer.Option(min=1, help="Stop after this many papers")] = None,
    force: Annotated[bool, typer.Option(help="Regenerate even when up to date")] = False,
) -> None:
    """Generate AI summaries and structured extractions (skips papers already done)."""
    settings = get_settings()

    async def work(r: Resources) -> dict[str, object]:
        stats = await generate_insights(
            r.graph, build_llm(settings), limit=limit, force=force,
            concurrency=settings.llm_concurrency,
        )  # fmt: skip
        return stats.as_dict()

    try:
        typer.echo(json.dumps(_run(work), indent=2))
    except ResearchGraphError as exc:
        typer.secho(exc.message, err=True, fg=typer.colors.RED)
        raise typer.Exit(1) from exc


@app.command("eval")
def evaluate(
    suite: Annotated[str, typer.Argument(help="retrieval | nlquery | rag")],
    dataset: Annotated[
        Path | None, typer.Option(help="Gold dataset JSON (default: data/eval)")
    ] = None,
    out: Annotated[Path | None, typer.Option(help="Also write a Markdown report here")] = None,
    judge: Annotated[
        bool, typer.Option(help="rag: LLM-judge faithfulness (extra LLM calls)")
    ] = False,
) -> None:
    """Measure retrieval, NL->Cypher or RAG quality on the gold sets in data/eval."""
    if suite not in {"retrieval", "nlquery", "rag"}:
        typer.secho("suite must be retrieval, nlquery or rag", err=True, fg=typer.colors.RED)
        raise typer.Exit(2)
    settings = get_settings()

    async def work(r: Resources) -> dict[str, object]:
        embedder = EmbedderCache(settings)
        if suite == "retrieval":
            return await eval_runner.eval_retrieval(
                r.graph, embedder, eval_data.load_retrieval(dataset)
            )
        llm = build_llm(settings)
        if suite == "nlquery":
            return await eval_runner.eval_nlquery(r.graph, llm, eval_data.load_nlquery(dataset))
        return await eval_runner.eval_rag(
            r.graph, embedder, llm, eval_data.load_rag(dataset), judge=judge
        )

    try:
        report = _run(work)
    except ResearchGraphError as exc:
        typer.secho(exc.message, err=True, fg=typer.colors.RED)
        raise typer.Exit(1) from exc
    typer.echo(json.dumps(report, indent=2, default=str))
    if out is not None:
        out.write_text(eval_runner.format_markdown(suite, report), encoding="utf-8")
        typer.secho(f"wrote {out}", err=True)


if __name__ == "__main__":  # pragma: no cover
    app()
