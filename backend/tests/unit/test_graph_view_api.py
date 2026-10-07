from collections.abc import Mapping
from typing import Any

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from tests.fakes import ScriptedGraph


def _node(i: int, **extra: Any) -> dict[str, Any]:
    return {
        "id": f"paper:{i}",
        "title": f"Paper {i}",
        "year": 2015 + i,
        "pagerank": 1.0 / i,
        "cited_by_in_graph": i,
        "community_id": "community:paper:1",
        "community_label": "Transformers",
        "is_stub": False,
        "authors": ["Ann Author"],
        **extra,
    }


class SequencedGraph(ScriptedGraph):
    """ScriptedGraph whose responses for a label can differ per call."""

    def __init__(self, sequences: Mapping[str, list[list[dict[str, Any]]]], **kw: Any) -> None:
        super().__init__(**kw)
        self.sequences = {k: list(v) for k, v in sequences.items()}

    async def read(
        self, query: str, params: Mapping[str, Any] | None = None, *, label: str = ""
    ) -> list[dict[str, Any]]:
        if self.sequences.get(label):
            self.calls.append((label, query, dict(params or {})))
            return self.sequences[label].pop(0)
        return await super().read(query, params, label=label)


def _client(graph: ScriptedGraph) -> TestClient:
    app = create_app(Settings(app_env="test", log_json=False))
    app.state.graph = graph
    return TestClient(app)


def test_overview_returns_nodes_edges_and_truncation_flag() -> None:
    graph = ScriptedGraph(
        {
            "graph.overview.count": [{"total": 105}],
            "graph.overview.ids": [{"id": "paper:1"}, {"id": "paper:2"}, {"id": "paper:3"}],
            "graph.nodes": [_node(3), _node(1), _node(2)],  # DB order is arbitrary
            "graph.edges": [
                {"source": "paper:2", "target": "paper:1"},
                {"source": "paper:3", "target": "paper:9"},  # endpoint not shown: dropped
            ],
        }
    )
    body = _client(graph).get("/api/graph/overview?limit=5").json()
    assert [n["id"] for n in body["nodes"]] == ["paper:1", "paper:2", "paper:3"]  # ranking order
    assert body["edges"] == [{"source": "paper:2", "target": "paper:1", "type": "CITES"}]
    assert body["truncated"] is True
    assert body["total_papers"] == 105
    assert "not a measure of research quality" in body["note"]
    ids_call = next(c for c in graph.calls if c[0] == "graph.overview.ids")
    assert ids_call[2] == {"limit": 5}


def test_overview_limit_is_bounded() -> None:
    graph = ScriptedGraph()
    assert _client(graph).get("/api/graph/overview?limit=100000").status_code == 422
    assert _client(graph).get("/api/graph/overview?limit=1").status_code == 422


def test_overview_of_empty_graph() -> None:
    body = (
        _client(ScriptedGraph({"graph.overview.count": [{"total": 0}]}))
        .get("/api/graph/overview")
        .json()
    )
    assert body["nodes"] == [] and body["edges"] == [] and body["truncated"] is False


def test_neighbourhood_puts_the_focus_first_and_reports_truncation() -> None:
    graph = SequencedGraph(
        {"graph.nb.neighbours": [[{"id": "paper:2"}, {"id": "paper:3"}, {"id": "paper:4"}]]},
        responses={
            "graph.nb.exists": [{"id": "paper:1"}],
            "graph.nodes": [_node(2), _node(1), _node(3)],
            "graph.edges": [{"source": "paper:2", "target": "paper:1"}],
        },
    )
    # limit=5 -> room for 4 neighbours; three came back, so not truncated
    body = _client(graph).get("/api/graph/neighborhood/paper:1?limit=5").json()
    assert body["focus"] == "paper:1"
    assert body["nodes"][0]["id"] == "paper:1"
    assert body["truncated"] is False

    graph = SequencedGraph(
        {"graph.nb.neighbours": [[{"id": f"paper:{i}"} for i in range(2, 8)]]},
        responses={"graph.nb.exists": [{"id": "paper:1"}], "graph.nodes": [_node(1)]},
    )
    body = _client(graph).get("/api/graph/neighborhood/paper:1?limit=5").json()
    assert body["truncated"] is True  # 6 neighbours fetched for 4 slots
    nodes_call = next(c for c in graph.calls if c[0] == "graph.nodes")
    assert len(nodes_call[2]["ids"]) == 5  # focus + 4


def test_depth_two_expands_from_first_hop_neighbours_only() -> None:
    graph = SequencedGraph(
        {"graph.nb.neighbours": [[{"id": "paper:2"}], [{"id": "paper:3"}]]},
        responses={"graph.nb.exists": [{"id": "paper:1"}], "graph.nodes": [_node(1)]},
    )
    _client(graph).get("/api/graph/neighborhood/paper:1?depth=2&limit=10")
    calls = [c for c in graph.calls if c[0] == "graph.nb.neighbours"]
    assert calls[0][2]["seeds"] == ["paper:1"]
    assert calls[1][2]["seeds"] == ["paper:2"]
    assert set(calls[1][2]["exclude"]) == {"paper:1", "paper:2"}
    nodes_call = next(c for c in graph.calls if c[0] == "graph.nodes")
    assert nodes_call[2]["ids"] == ["paper:1", "paper:2", "paper:3"]


def test_unknown_paper_is_404_and_depth_is_validated() -> None:
    client = _client(ScriptedGraph())
    resp = client.get("/api/graph/neighborhood/nope")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"
    assert client.get("/api/graph/neighborhood/x?depth=3").status_code == 422
