from typing import Any

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.schemas.graph import PaperSummary
from app.services.reading_path import order_path
from app.services.trends import compute_trends, label_trend
from tests.fakes import ScriptedGraph


def _client(graph: ScriptedGraph) -> TestClient:
    app = create_app(Settings(log_json=False, _env_file=None))  # type: ignore[call-arg]
    app.state.graph = graph
    return TestClient(app)


def _p(pid: str, year: int, pagerank: float = 0.0) -> PaperSummary:
    return PaperSummary(id=pid, title=f"T-{pid}", year=year, pagerank=pagerank)


def test_labels() -> None:
    assert label_trend(3, 0, 5.0) == "emerging"
    assert label_trend(1, 0, 1.5) != "emerging"  # one paper is not a trend
    assert label_trend(6, 3, 1.9) == "rising"
    assert label_trend(1, 4, 0.3) == "declining"
    assert label_trend(3, 3, 1.0) == "steady"


def test_trends_use_share_not_counts() -> None:
    # Graph grows 4x, topic A grows 4x too (steady share); topic B grows 12x (rising).
    totals = {2018: 10, 2019: 10, 2020: 10, 2021: 40, 2022: 40, 2023: 40}
    rows = [
        {"topic_id": "a", "name": "A", "year": y, "papers": n}
        for y, n in [(2018, 2), (2019, 2), (2020, 2), (2021, 8), (2022, 8), (2023, 8)]
    ] + [{"topic_id": "b", "name": "B", "year": y, "papers": n} for y, n in [(2018, 1), (2021, 12)]]
    res = compute_trends(rows, totals, window=3, min_papers=2)
    by_id = {t.topic_id: t for t in res.topics}
    assert res.recent_years == [2021, 2022, 2023] and res.previous_years == [2018, 2019, 2020]
    assert by_id["a"].label == "steady" and by_id["a"].growth < 1.2
    assert by_id["b"].label == "rising" and by_id["b"].share_recent > by_id["b"].share_previous
    assert res.topics[0].topic_id == "b"  # rising sorts before steady


def test_trends_filter_small_topics_and_handle_empty() -> None:
    assert compute_trends([], {}, window=3, min_papers=1).topics == []
    res = compute_trends(
        [{"topic_id": "x", "name": "X", "year": 2020, "papers": 1}],
        {2020: 5},
        window=2,
        min_papers=2,
    )
    assert res.topics == []


def test_trends_endpoint() -> None:
    graph = ScriptedGraph(
        {
            "trends.topic_years": [{"topic_id": "t", "name": "T", "year": 2023, "papers": 3}],
            "trends.year_totals": [{"year": 2023, "papers": 6}],
        }
    )
    body = _client(graph).get("/api/trends/topics", params={"window": 1}).json()
    assert body["topics"][0]["label"] == "emerging" and body["last_year"] == 2023


def test_path_puts_cited_work_first_and_explains() -> None:
    papers = [_p("c", 2020), _p("b", 2018), _p("a", 2015), _p("lone", 2019)]
    edges = [("b", "a"), ("c", "b"), ("c", "a")]  # c cites b and a; b cites a
    ordered, cited_by, builds_on = order_path(papers, edges, length=4)
    ids = [p.id for p in ordered]
    assert ids.index("a") < ids.index("b") < ids.index("c")
    assert cited_by["a"] == 2 and builds_on["c"] == ["a", "b"]


def test_path_keeps_the_most_cited_when_truncating() -> None:
    papers = [_p("a", 2015), _p("b", 2018), _p("c", 2020), _p("x", 2019, pagerank=0.0)]
    ordered, _, _ = order_path(papers, [("b", "a"), ("c", "a"), ("c", "b")], length=3)
    assert {p.id for p in ordered} == {"a", "b", "c"}


def test_path_survives_citation_cycles() -> None:
    papers = [_p("a", 2010), _p("b", 2012)]
    ordered, _, _ = order_path(papers, [("a", "b"), ("b", "a")], length=2)
    assert [p.id for p in ordered] == ["a", "b"]  # earliest year breaks the cycle


def test_path_endpoint_requires_exactly_one_focus() -> None:
    client = _client(ScriptedGraph())
    assert client.get("/api/reading-path").status_code == 422
    assert (
        client.get("/api/reading-path", params={"topic_id": "t", "paper_id": "p"}).status_code
        == 422
    )


def test_path_endpoint_for_topic() -> None:
    def row(pid: str, year: int) -> dict[str, Any]:
        return {"id": pid, "title": pid, "year": year, "doi": None, "arxiv_id": None,
                "citation_count": None, "pagerank": None, "is_stub": False,
                "cited_by_in_graph": 0, "venue": None, "authors": []}  # fmt: skip

    graph = ScriptedGraph(
        {
            "paths.topic": [{"name": "Graphs"}],
            "paths.topic_candidates": [row("new", 2022), row("old", 2015)],
            "paths.edges": [{"source": "new", "target": "old"}],
        }
    )
    body = _client(graph).get("/api/reading-path", params={"topic_id": "topic:g"}).json()
    assert body["focus"] == "Topic: Graphs"
    assert [s["paper"]["id"] for s in body["steps"]] == ["old", "new"]
    assert body["steps"][1]["builds_on"] == ["old"] and body["steps"][0]["cited_by_on_path"] == 1
