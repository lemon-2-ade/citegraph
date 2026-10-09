"""Guards against accidental quadratic behaviour in pure-Python hot paths.

Bounds are 10-50x what a laptop needs, so they catch complexity regressions, not noise. Real
latency against Neo4j is measured with scripts/loadtest.py on your own stack.
"""

import random
import time

from app.graph.cypher_guard import validate_cypher
from app.schemas.graph import PaperSummary
from app.services.paper_search import reciprocal_rank_fusion
from app.services.reading_path import order_path
from app.services.trends import compute_trends


def _timed(fn):  # type: ignore[no-untyped-def]
    start = time.perf_counter()
    result = fn()
    return result, time.perf_counter() - start


def test_reading_path_scales_to_thousands_of_candidates() -> None:
    rng = random.Random(1)
    papers = [PaperSummary(id=f"p{i}", title=f"T{i}", year=1990 + i % 35) for i in range(4000)]
    edges = [(f"p{rng.randrange(4000)}", f"p{rng.randrange(4000)}") for _ in range(20000)]
    (ordered, _, _), elapsed = _timed(lambda: order_path(papers, edges, 500))
    assert len(ordered) == 500 and elapsed < 2.0


def test_trends_scale_to_many_topics_and_years() -> None:
    rows = [
        {"topic_id": f"t{t}", "name": f"Topic {t}", "year": 1995 + y, "papers": 1 + (t * y) % 7}
        for t in range(600)
        for y in range(30)
    ]
    totals = {1995 + y: 5000 for y in range(30)}
    result, elapsed = _timed(lambda: compute_trends(rows, totals, window=3, min_papers=2))
    assert len(result.topics) == 600 and elapsed < 1.5


def test_validator_handles_a_burst_of_queries() -> None:
    query = (
        "MATCH (a:Author)-[:WROTE]->(p:Paper)-[:HAS_TOPIC]->(t:Topic) "
        "WHERE toLower(t.name) CONTAINS 'graph' AND p.year > 2015 "
        "RETURN a.name AS author, count(DISTINCT p) AS papers ORDER BY papers DESC LIMIT 20"
    )
    _, elapsed = _timed(lambda: [validate_cypher(query) for _ in range(2000)])
    assert elapsed < 3.0


def test_rank_fusion_over_large_lists() -> None:
    a = [f"p{i}" for i in range(50000)]
    b = list(reversed(a))
    fused, elapsed = _timed(lambda: reciprocal_rank_fusion({"x": a, "y": b}))
    assert len(fused) == 50000 and elapsed < 1.5
