"""Reading paths: an ordered list that builds up from foundational to recent work.

1. Candidates come from a topic's papers, or from the 2-hop citation neighbourhood of a paper.
2. The most important ``length`` candidates are kept. Importance is the number of citations a
   paper receives *from other candidates* (what the path itself builds on), then PageRank.
3. The kept papers are ordered so every paper comes after the papers it cites that are also on
   the path (a topological order of the citation edges, earliest year first among ties).
   Citation cycles, which should not occur but do in real data, are broken by year.
"""

from __future__ import annotations

import heapq
from collections import defaultdict
from collections.abc import Iterable, Sequence

from app.core.errors import ValidationFailedError
from app.graph.client import GraphClient
from app.repositories.paths import PathRepository
from app.schemas.graph import PaperSummary
from app.schemas.paths import PathStep, ReadingPath

CANDIDATE_LIMIT = 80


def order_path(
    papers: Sequence[PaperSummary], edges: Iterable[tuple[str, str]], length: int
) -> tuple[list[PaperSummary], dict[str, int], dict[str, list[str]]]:
    """Select and order papers. Edges are (citing, cited). Returns the ordered papers,
    in-path citation counts and, per paper, the ids of earlier path papers it builds on."""
    by_id = {p.id: p for p in papers}
    valid = [(a, b) for a, b in set(edges) if a in by_id and b in by_id and a != b]
    cited_by: dict[str, int] = defaultdict(int)
    for _, cited in valid:
        cited_by[cited] += 1

    def importance(p: PaperSummary) -> tuple[int, float, str]:
        return (-cited_by[p.id], -(p.pagerank or 0.0), p.id)

    chosen = sorted(papers, key=importance)[:length]
    chosen_ids = {p.id for p in chosen}
    sub = [(a, b) for a, b in valid if a in chosen_ids and b in chosen_ids]
    in_path_cited_by: dict[str, int] = defaultdict(int)
    prerequisites: dict[str, list[str]] = defaultdict(list)  # citing -> cited
    dependents: dict[str, list[str]] = defaultdict(list)  # cited -> citing
    for citing, cited in sub:
        in_path_cited_by[cited] += 1
        prerequisites[citing].append(cited)
        dependents[cited].append(citing)

    def key(pid: str) -> tuple[int, str]:
        return (by_id[pid].year or 9999, pid)

    # Kahn's algorithm with a heap: a paper is ready when everything it cites on the path is
    # already placed. Ties go to the earliest year.
    remaining = {pid: len(prerequisites[pid]) for pid in chosen_ids}
    ready = [(key(pid), pid) for pid, n in remaining.items() if n == 0]
    heapq.heapify(ready)
    order: list[str] = []
    placed: set[str] = set()
    while len(order) < len(chosen_ids):
        if not ready:
            # A cycle: release the earliest unplaced paper to make progress.
            pid = min((p for p in chosen_ids if p not in placed), key=key)
            heapq.heappush(ready, (key(pid), pid))
        _, pid = heapq.heappop(ready)
        if pid in placed:
            continue
        placed.add(pid)
        order.append(pid)
        for dep in dependents[pid]:
            remaining[dep] -= 1
            if remaining[dep] == 0 and dep not in placed:
                heapq.heappush(ready, (key(dep), dep))
    position = {pid: i for i, pid in enumerate(order)}
    builds_on = {
        pid: sorted(
            (c for c in prerequisites[pid] if position[c] < position[pid]),
            key=lambda c: position[c],
        )
        for pid in order
    }
    return [by_id[pid] for pid in order], dict(in_path_cited_by), builds_on


def _reason(cited_by: int, builds_on: list[str], first: bool) -> str:
    parts = []
    if cited_by:
        parts.append(
            f"Cited by {cited_by} other paper(s) on this path, so it is foundational here."
        )
    if builds_on:
        parts.append(f"Builds on {len(builds_on)} earlier paper(s) on the path.")
    if not parts:
        parts.append(
            "A good starting point: it does not depend on other papers on this path."
            if first
            else "Related to the topic and independent of the other papers on this path."
        )
    return " ".join(parts)


async def build_reading_path(
    graph: GraphClient, *, topic_id: str | None, paper_id: str | None, length: int
) -> ReadingPath:
    if (topic_id is None) == (paper_id is None):
        raise ValidationFailedError("Provide exactly one of topic_id or paper_id.")
    repo = PathRepository(graph)
    if topic_id is not None:
        focus = f"Topic: {await repo.topic_name(topic_id)}"
        rows = await repo.candidates_for_topic(topic_id, CANDIDATE_LIMIT)
    else:
        assert paper_id is not None
        focus = f"Around: {await repo.paper_title(paper_id)}"
        rows = await repo.candidates_near_paper(paper_id, CANDIDATE_LIMIT)
    papers = [PaperSummary.model_validate(r) for r in rows]
    edges = await repo.edges([p.id for p in papers])
    ordered, cited_by, builds_on = order_path(papers, edges, length)
    titles = {p.id: p.title or p.id for p in papers}
    steps = [
        PathStep(
            position=i,
            paper=p,
            cited_by_on_path=cited_by.get(p.id, 0),
            builds_on=[titles[c] for c in builds_on[p.id]],
            reason=_reason(cited_by.get(p.id, 0), builds_on[p.id], i == 1),
        )
        for i, p in enumerate(ordered, start=1)
    ]
    return ReadingPath(
        focus=focus,
        steps=steps,
        candidates=len(papers),
        note=(
            "Order follows citations within this graph (cited work first). It is a suggested "
            "route, not a curriculum: it only knows about papers that were ingested."
        ),
    )
