"""Collect every Cypher query the backend can issue and print them as JSON.

Two sources:
* module-level string constants that look like Cypher, and
* queries actually issued by repositories/loader when driven by a recording fake
  (this catches queries assembled at runtime, e.g. per-sort ORDER BY variants).

Usage (from backend/):  uv run python scripts/dump_cypher.py | node ../scripts/cypher-lint/lint.mjs
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import json
import pkgutil
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app

_CYPHER_START = re.compile(
    r"^\s*(MATCH|OPTIONAL MATCH|MERGE|CREATE|UNWIND|CALL|WITH|RETURN|SHOW)\b", re.IGNORECASE
)


class RecordingGraph:
    def __init__(self) -> None:
        self.queries: dict[str, str] = {}

    async def _record(
        self, query: str, params: Mapping[str, Any] | None = None, *, label: str = ""
    ) -> list[dict[str, Any]]:
        key = label or f"anon{len(self.queries)}"
        suffix = 1
        while key in self.queries and self.queries[key] != query:
            suffix += 1
            key = f"{label}#{suffix}"
        self.queries[key] = query
        if "AS total" in query:
            return [{"total": 0}]
        return []

    read = write = run_readonly_unchecked = _record


def static_queries() -> dict[str, str]:
    found: dict[str, str] = {}
    for module_info in pkgutil.walk_packages(app.__path__, "app."):
        if module_info.name in {"app.main", "app.cli"}:
            continue
        module = importlib.import_module(module_info.name)
        for name, value in vars(module).items():
            if name.endswith("_FRAGMENT"):
                continue  # partial queries; covered by runtime capture
            if isinstance(value, str) and _CYPHER_START.match(value):
                found[f"{module_info.name}.{name}"] = value
            elif isinstance(value, tuple | list) and all(isinstance(v, str) for v in value):
                for i, v in enumerate(value):
                    if _CYPHER_START.match(v):
                        found[f"{module_info.name}.{name}[{i}]"] = v
            elif isinstance(value, dict) and all(isinstance(v, str) for v in value.values()):
                for key, v in value.items():
                    if _CYPHER_START.match(v):  # ORDER BY fragments are skipped here
                        found[f"{module_info.name}.{name}[{key}]"] = v
    return found


async def runtime_queries() -> dict[str, str]:
    from app.core.errors import NotFoundError
    from app.ingestion.loader import GraphLoader
    from app.models.domain import AuthorRecord, ExternalIds, PaperRecord, TopicRecord, VenueRecord
    from app.repositories.authors import AuthorRepository
    from app.repositories.papers import PaperRepository
    from app.repositories.topics import TopicRepository
    from app.schemas.common import PageParams

    graph = RecordingGraph()
    papers = PaperRepository(graph)  # type: ignore[arg-type]
    for sort in ("year", "pagerank", "cited_by"):
        await papers.list(PageParams(), sort=sort)  # type: ignore[arg-type]
    for call in (
        papers.get("x"),
        papers.citations("x", PageParams()),
        papers.references("x", PageParams()),
        AuthorRepository(graph).get("x"),  # type: ignore[arg-type]
        TopicRepository(graph).get("x"),  # type: ignore[arg-type]
    ):
        with contextlib.suppress(NotFoundError):
            await call
    await TopicRepository(graph).list(PageParams())  # type: ignore[arg-type]

    record = PaperRecord(
        source="lint",
        ids=ExternalIds(doi="10.1000/x"),
        title="T",
        authors=[AuthorRecord(name="A B")],
        venue=VenueRecord(name="V"),
        topics=[TopicRecord(name="Topic")],
        keywords=["k"],
        references=[ExternalIds(openalex="W1")],
    )
    await GraphLoader(graph).load([record])  # type: ignore[arg-type]
    for extra in _extra_runtime_hooks():
        await extra(graph)
    return {f"runtime:{k}": v for k, v in graph.queries.items()}


def _extra_runtime_hooks() -> list[Any]:
    """Producers of dynamically built queries."""

    async def shortest_paths(graph: RecordingGraph) -> None:
        from app.analytics.queries import build_shortest_path_query

        graph.queries["runtime:shortest_path.cites"] = build_shortest_path_query(
            "Paper", "Paper", ["CITES"], 6
        )
        graph.queries["runtime:shortest_path.mixed"] = build_shortest_path_query(
            "Author", "Topic", ["WROTE", "HAS_TOPIC", "COLLABORATED_WITH"], 8
        )

    return [shortest_paths]


def main() -> None:
    import structlog

    structlog.configure(logger_factory=structlog.PrintLoggerFactory(file=sys.stderr))
    queries = static_queries()
    queries.update(asyncio.run(runtime_queries()))
    json.dump(queries, sys.stdout, indent=1)


if __name__ == "__main__":
    main()
