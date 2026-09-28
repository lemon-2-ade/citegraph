from typing import Any

import pytest

from app.analytics.backends import NetworkXBackend, _normalise_communities, select_backend
from app.analytics.service import AnalyticsOptions, AnalyticsService
from tests.fakes import ScriptedGraph

PAPERS = [{"id": f"p{i}"} for i in range(7)]
# Two triangles (p0-p2, p3-p5) joined through p6.
CITES = [
    ("p1", "p0"),
    ("p2", "p0"),
    ("p2", "p1"),
    ("p4", "p3"),
    ("p5", "p3"),
    ("p5", "p4"),
    ("p6", "p0"),
    ("p6", "p3"),
]


def _graph() -> ScriptedGraph:
    indeg = {p["id"]: 0 for p in PAPERS}
    outdeg = dict(indeg)
    for s, t in CITES:
        outdeg[s] += 1
        indeg[t] += 1
    return ScriptedGraph(
        {
            "proj.papers": PAPERS,
            "proj.cites": [{"source": s, "target": t} for s, t in CITES],
            "proj.authors": [{"id": "a1"}, {"id": "a2"}, {"id": "a3"}],
            "proj.collab": [
                {"source": "a1", "target": "a2", "weight": 3},
                {"source": "a2", "target": "a3", "weight": 1},
            ],
            "analytics.paper_degrees": [
                {"id": p, "in_degree": indeg[p], "out_degree": outdeg[p]} for p in indeg
            ],
            "analytics.author_stats": [
                {"id": a, "paper_count": 1, "collaborator_count": 1} for a in ("a1", "a2", "a3")
            ],
            "analytics.build_collab": [{"n": 2}],
            "analytics.build_related": [{"n": 0}],
        }
    )


def _params(graph: ScriptedGraph, label: str) -> list[dict[str, Any]]:
    return [params for lbl, _, params in graph.calls if lbl == label]


async def test_networkx_backend_pagerank_from_projection() -> None:
    backend = NetworkXBackend(_graph())  # type: ignore[arg-type]
    scores = await backend.pagerank("citations")
    assert set(scores) == {p["id"] for p in PAPERS}
    assert scores["p0"] > scores["p6"]  # p0 is cited, p6 only cites
    assert sum(scores.values()) == pytest.approx(1.0)


async def test_run_writes_metrics_and_communities() -> None:
    graph = _graph()
    backend = NetworkXBackend(graph)  # type: ignore[arg-type]
    report = await AnalyticsService(graph, backend, AnalyticsOptions(min_community_size=3)).run()  # type: ignore[arg-type]

    assert report.backend == "networkx"
    assert report.papers == 7
    assert report.authors == 3
    assert report.collaboration_edges == 2
    assert report.betweenness_sampled == {"papers": False, "authors": False}

    rows = _params(graph, "analytics.paper_metrics")[0]["rows"]
    by_id = {r["id"]: r for r in rows}
    assert by_id["p0"]["in_degree"] == 3
    assert by_id["p6"]["out_degree"] == 2
    # p6 bridges the two triangles.
    assert max(rows, key=lambda r: r["betweenness"])["id"] == "p6"

    created = _params(graph, "analytics.create_communities")
    paper_communities = created[0]["rows"]
    assert all(c["size"] >= 3 for c in paper_communities)
    assert paper_communities[0]["id"] == "community:papers:0"
    assert report.paper_communities == len(paper_communities) >= 2


async def test_small_communities_are_not_materialised() -> None:
    graph = _graph()
    backend = NetworkXBackend(graph)  # type: ignore[arg-type]
    report = await AnalyticsService(graph, backend, AnalyticsOptions(min_community_size=4)).run()  # type: ignore[arg-type]
    # Two communities of 3-4 papers: at most one reaches size 4.
    assert report.paper_communities <= 1
    assigned = [r for p in _params(graph, "analytics.assign") for r in p["rows"]]
    assert all(r["community"].startswith("community:") for r in assigned)


async def test_betweenness_is_sampled_on_large_graphs() -> None:
    graph = _graph()
    backend = NetworkXBackend(graph)  # type: ignore[arg-type]
    options = AnalyticsOptions(exact_betweenness_max_nodes=5, betweenness_sample_size=3)
    report = await AnalyticsService(graph, backend, options).run()  # type: ignore[arg-type]
    assert report.betweenness_sampled == {"papers": True, "authors": False}


def test_gds_community_ids_are_renumbered_by_size() -> None:
    assert _normalise_communities({"a": 99, "b": 99, "c": 7}) == {"a": 0, "b": 0, "c": 1}


async def test_backend_selection() -> None:
    graph = ScriptedGraph()
    assert (await select_backend(graph, "networkx")).name == "networkx"  # type: ignore[arg-type]
    assert (await select_backend(graph, "gds")).name == "gds"  # type: ignore[arg-type]
