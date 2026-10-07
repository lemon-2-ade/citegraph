from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.analytics.queries import build_shortest_path_query, describe_path, label_for_id
from app.api.deps import get_queue
from app.core.config import Settings
from app.core.errors import ValidationFailedError
from app.db.session import create_engine, create_sessionmaker, create_tables
from app.main import create_app
from app.schemas.analytics import PAGERANK_NOTE, PathNode, PathRelationship
from tests.fakes import ScriptedGraph

SUMMARY_ROW = {
    "id": "paper:1",
    "title": "T",
    "year": 2017,
    "doi": None,
    "arxiv_id": None,
    "citation_count": None,
    "pagerank": 0.3,
    "is_stub": False,
    "cited_by_in_graph": 4,
    "venue": None,
    "authors": ["A"],
}


def _client(graph: ScriptedGraph, **settings: Any) -> TestClient:
    app = create_app(Settings(log_json=False, **settings))
    app.state.graph = graph
    return TestClient(app)


def test_influential_papers_include_pagerank_caveat() -> None:
    graph = ScriptedGraph({"analytics.top_papers.pagerank": [{**SUMMARY_ROW, "score": 0.3}]})
    body = _client(graph).get("/api/analytics/influential").json()
    assert body["note"] == PAGERANK_NOTE
    assert "not a measure of research quality" in body["note"]
    assert body["papers"][0]["paper"]["id"] == "paper:1"


def test_influential_authors_metric_mapping() -> None:
    graph = ScriptedGraph(
        {
            "analytics.top_authors.paper_count": [
                {"id": "author:1", "name": "A", "score": 3.0, "paper_count": 3}
            ]
        }
    )
    body = (
        _client(graph)
        .get("/api/analytics/influential", params={"entity": "author", "metric": "in_degree"})
        .json()
    )
    assert body["metric"] == "paper_count"
    assert body["authors"][0]["paper_count"] == 3


def test_similar_papers_explain_shared_references() -> None:
    graph = ScriptedGraph(
        {
            "papers.exists": [{"id": "paper:0"}],
            "analytics.similar.coupling": [{**SUMMARY_ROW, "shared": 3, "score": 0.25}],
        }
    )
    body = _client(graph).get("/api/papers/paper:0/similar").json()
    assert body[0]["explanation"] == "Shares 3 reference(s) with this paper (Jaccard 0.25)."


def test_related_papers_uses_local_ppr() -> None:
    graph = ScriptedGraph(
        {
            "papers.exists": [{"id": "paper:0"}],
            "proj.neighbourhood": [{"id": "paper:1"}],
            "proj.edges_among": [{"source": "paper:0", "target": "paper:1"}],
            "analytics.summaries": [SUMMARY_ROW],
        }
    )
    body = _client(graph).get("/api/papers/paper:0/related").json()
    assert [r["paper"]["id"] for r in body] == ["paper:1"]
    assert body[0]["method"] == "ppr"


def test_shortest_path_found_and_explained() -> None:
    graph = ScriptedGraph(
        {
            "analytics.shortest_path": [
                {
                    "nodes": [
                        {"id": "paper:a", "label": "Paper", "name": "GAT", "year": 2017},
                        {"id": "paper:b", "label": "Paper", "name": "GCN", "year": 2016},
                    ],
                    "relationships": [{"type": "CITES", "source": "paper:a", "target": "paper:b"}],
                }
            ]
        }
    )
    body = (
        _client(graph)
        .get("/api/graph/shortest-path", params={"source": "paper:a", "target": "paper:b"})
        .json()
    )
    assert body["found"] is True
    assert body["length"] == 1
    assert body["explanation"] == "GAT cites GCN"


def test_shortest_path_not_found_is_explicit() -> None:
    body = (
        _client(ScriptedGraph())
        .get("/api/graph/shortest-path", params={"source": "paper:a", "target": "author:b"})
        .json()
    )
    assert body["found"] is False
    assert "No path" in body["explanation"]


def test_shortest_path_rejects_unknown_relationship_and_prefix() -> None:
    client = _client(ScriptedGraph())
    bad_rel = client.get(
        "/api/graph/shortest-path",
        params={"source": "paper:a", "target": "paper:b", "relationships": "DETACH DELETE"},
    )
    assert bad_rel.status_code == 422
    bad_id = client.get("/api/graph/shortest-path", params={"source": "x:a", "target": "paper:b"})
    assert bad_id.status_code == 422


@pytest.mark.parametrize(
    ("labels", "rels", "hops"),
    [
        (("Paper", "Paper"), ["CITES})-[:X"], 3),
        (("Paper) DETACH DELETE (n", "Paper"), ["CITES"], 3),
        (("Paper", "Paper"), ["CITES"], 99),
        (("Paper", "Paper"), [], 3),
    ],
)
def test_path_query_builder_only_accepts_whitelisted_parts(
    labels: tuple[str, str], rels: list[str], hops: int
) -> None:
    with pytest.raises(ValidationFailedError):
        build_shortest_path_query(labels[0], labels[1], rels, hops)


def test_path_query_builder_output() -> None:
    query = build_shortest_path_query("Paper", "Author", ["CITES", "WROTE", "CITES"], 4)
    assert "(a:Paper {id: $source})" in query
    assert "[:CITES|WROTE*..4]" in query
    assert label_for_id("topic:graph-neural-networks") == "Topic"


def test_describe_path() -> None:
    nodes = [
        PathNode(id="author:1", label="Author", name="Kipf"),
        PathNode(id="paper:1", label="Paper", name="GCN"),
    ]
    rels = [PathRelationship(type="WROTE", source="author:1", target="paper:1")]
    assert describe_path(nodes, rels) == "Kipf wrote GCN"


def test_community_detail_merges_links() -> None:
    graph = ScriptedGraph(
        {
            "communities.get": [
                {
                    "community": {
                        "id": "community:papers:0",
                        "scope": "papers",
                        "rank": 0,
                        "size": 30,
                        "label": "Graph Neural Networks",
                        "top_topics": ["Graph Neural Networks"],
                        "algorithm": "louvain",
                        "computed_at": None,
                    }
                }
            ],
        }
    )
    # Detail queries have no label; ScriptedGraph returns [] for them, so script a default.
    original = graph.read

    async def read(query: str, params: Any = None, *, label: str = "") -> list[dict[str, Any]]:
        if "AS cites_out" in query:
            return [
                {
                    "authors": [{"id": "author:1", "name": "A", "count": 2}],
                    "institutions": [],
                    "topics": [{"id": "topic:gnn", "name": "GNN", "count": 5}],
                    "per_year": [[2016, 2], [2017, 3]],
                    "cites_out": [{"community_id": "community:papers:1", "label": "LLMs", "n": 4}],
                    "cites_in": [
                        {"community_id": "community:papers:1", "label": "LLMs", "n": 1},
                        {"community_id": "community:papers:2", "label": "KGs", "n": 7},
                    ],
                }
            ]
        return await original(query, params, label=label)

    graph.read = read  # type: ignore[method-assign]
    body = _client(graph).get("/api/communities/community:papers:0").json()
    assert body["papers_per_year"] == {"2016": 2, "2017": 3}
    assert body["connections"] == [
        {
            "community_id": "community:papers:2",
            "label": "KGs",
            "citations_out": 0,
            "citations_in": 7,
        },
        {
            "community_id": "community:papers:1",
            "label": "LLMs",
            "citations_out": 4,
            "citations_in": 1,
        },
    ]


class FakeQueue:
    def __init__(self) -> None:
        self.enqueued: list[tuple[str, tuple[Any, ...]]] = []

    async def enqueue_job(self, name: str, *args: Any, **kwargs: Any) -> None:
        self.enqueued.append((name, args))


async def test_analytics_run_is_enqueued_once() -> None:
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    await create_tables(engine)
    queue = FakeQueue()
    app = create_app(Settings(log_json=False, app_env="development"))
    app.state.graph = ScriptedGraph()
    app.state.sessions = create_sessionmaker(engine)
    app.dependency_overrides[get_queue] = lambda: queue
    client = TestClient(app)

    first = client.post("/api/analytics/runs", json={"community_algorithm": "leiden"})
    assert first.status_code == 202
    assert queue.enqueued[0][0] == "run_analytics"
    # A second run while one is queued is refused.
    assert client.post("/api/analytics/runs", json={}).status_code == 422
    assert client.get("/api/analytics/runs").json()[0]["options"]["community_algorithm"] == "leiden"
    await engine.dispose()


def test_papers_per_year() -> None:
    graph = ScriptedGraph(
        {"analytics.papers_per_year": [{"year": 2016, "papers": 4}, {"year": 2017, "papers": 9}]}
    )
    resp = _client(graph).get("/api/analytics/years")
    assert resp.status_code == 200
    assert resp.json() == [{"year": 2016, "papers": 4}, {"year": 2017, "papers": 9}]
