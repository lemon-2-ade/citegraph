"""Topic trends: which topics are gaining or losing share of the papers in the graph.

Growth is measured on *share* (a topic's papers over all papers in the window), not on raw
counts, because the number of ingested papers per year mostly reflects what was collected.
Shares are smoothed with a pseudo-count so a topic going from 0 to 1 paper is not an infinite
rise. Labels use deliberately simple thresholds, documented in ``label_trend``.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import LiteralString

from app.graph.client import GraphClient
from app.schemas.analytics import YearCount
from app.schemas.trends import TopicTrend, TrendLabel, TrendsResponse

SMOOTHING = 0.5  # pseudo-papers added to each window's count
RISING = 1.5
DECLINING = 0.67
MIN_RECENT_FOR_EMERGING = 2

_TOPIC_YEARS: LiteralString = """
MATCH (p:Paper)-[:HAS_TOPIC]->(t:Topic)
WHERE p.year IS NOT NULL AND coalesce(p.is_stub, false) = false
RETURN t.id AS topic_id, t.name AS name, p.year AS year, count(DISTINCT p) AS papers
"""

_YEAR_TOTALS: LiteralString = """
MATCH (p:Paper)
WHERE p.year IS NOT NULL AND coalesce(p.is_stub, false) = false
RETURN p.year AS year, count(p) AS papers
"""


def label_trend(recent: int, previous: int, growth: float) -> TrendLabel:
    """emerging: absent before, at least 2 papers now; rising/declining: share moved by
    1.5x / 0.67x or more; otherwise steady."""
    if previous == 0 and recent >= MIN_RECENT_FOR_EMERGING:
        return "emerging"
    if growth >= RISING and recent > previous:
        return "rising"
    if growth <= DECLINING and recent < previous:
        return "declining"
    return "steady"


def compute_trends(
    topic_years: Iterable[Mapping[str, object]],
    year_totals: Mapping[int, int],
    *,
    window: int,
    min_papers: int,
) -> TrendsResponse:
    years = sorted(year_totals)
    note = (
        "Trends describe the papers in this graph, which is a collected sample and not the whole "
        "field. A topic's share can move because of what was ingested."
    )
    if not years:
        return TrendsResponse(
            window=window, recent_years=[], previous_years=[], topics=[], note=note
        )
    last = years[-1]
    recent_years = list(range(last - window + 1, last + 1))
    previous_years = list(range(last - 2 * window + 1, last - window + 1))
    total_recent = sum(year_totals.get(y, 0) for y in recent_years)
    total_previous = sum(year_totals.get(y, 0) for y in previous_years)

    names: dict[str, str] = {}
    per_topic: dict[str, dict[int, int]] = defaultdict(dict)
    for row in topic_years:
        tid = str(row["topic_id"])
        names[tid] = str(row["name"])
        per_topic[tid][int(row["year"])] = int(row["papers"])  # type: ignore[call-overload]

    trends: list[TopicTrend] = []
    for tid, by_year in per_topic.items():
        total = sum(by_year.values())
        if total < min_papers:
            continue
        recent = sum(by_year.get(y, 0) for y in recent_years)
        previous = sum(by_year.get(y, 0) for y in previous_years)
        share_recent = recent / total_recent if total_recent else 0.0
        share_previous = previous / total_previous if total_previous else 0.0
        smooth_recent = (recent + SMOOTHING) / (total_recent + 2 * SMOOTHING)
        smooth_previous = (previous + SMOOTHING) / (total_previous + 2 * SMOOTHING)
        growth = smooth_recent / smooth_previous
        trends.append(
            TopicTrend(
                topic_id=tid,
                name=names[tid],
                total=total,
                series=[YearCount(year=y, papers=n) for y, n in sorted(by_year.items())],
                recent=recent,
                previous=previous,
                share_recent=share_recent,
                share_previous=share_previous,
                growth=growth,
                label=label_trend(recent, previous, growth),
            )
        )
    order = {"emerging": 0, "rising": 1, "steady": 2, "declining": 3}
    trends.sort(key=lambda t: (order[t.label], -t.growth, -t.total, t.name))
    return TrendsResponse(
        first_year=years[0],
        last_year=last,
        window=window,
        recent_years=recent_years,
        previous_years=previous_years,
        topics=trends,
        note=note,
    )


async def topic_trends(
    graph: GraphClient, *, window: int = 3, min_papers: int = 2, limit: int = 30
) -> TrendsResponse:
    rows = await graph.read(_TOPIC_YEARS, label="trends.topic_years")
    totals = await graph.read(_YEAR_TOTALS, label="trends.year_totals")
    result = compute_trends(
        rows, {int(r["year"]): int(r["papers"]) for r in totals}, window=window,
        min_papers=min_papers,
    )  # fmt: skip
    result.topics = result.topics[:limit]
    return result
