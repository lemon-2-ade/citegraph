from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.repositories.search import to_lucene
from tests.fakes import ScriptedGraph


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("graph neural", "graph AND neural*"),
        ("  attention  ", "attention*"),
        ("C++ (fast)", "C\\+\\+ AND \\(fast\\)*"),
        ("title:secret OR admin", "title\\:secret AND admin*"),
        ("a", None),
        ("   ", None),
        ("AND", None),
    ],
)
def test_to_lucene_escapes_syntax_and_prefixes_last_term(text: str, expected: str | None) -> None:
    assert to_lucene(text) == expected


def _client(graph: ScriptedGraph) -> TestClient:
    app = create_app(Settings(log_json=False))
    app.state.graph = graph
    return TestClient(app)


def test_search_groups_hits_by_kind() -> None:
    graph = ScriptedGraph(
        {
            "search.papers": [
                {
                    "id": "p1",
                    "title": "Attention",
                    "score": 2.0,
                    "year": "2017",
                    "authors": ["A", "B"],
                }
            ],
            "search.authors": [{"id": "a1", "title": "Ann", "score": 1.0, "papers": 1}],
            "search.topics": [
                {"id": "t1", "title": "Attention Mechanisms", "score": 1.5, "papers": 4}
            ],
        }
    )
    body: dict[str, Any] = _client(graph).get("/api/search", params={"q": "atten"}).json()
    assert body["papers"][0]["subtitle"] == "A, B · 2017"
    assert body["authors"][0]["subtitle"] == "1 paper"
    assert body["topics"][0]["subtitle"] == "4 papers"
    assert graph.calls[0][2]["q"] == "atten*"


def test_too_short_query_returns_empty_without_querying() -> None:
    graph = ScriptedGraph()
    body = _client(graph).get("/api/search", params={"q": "a"}).json()
    assert body["papers"] == [] and body["authors"] == [] and body["topics"] == []
    assert graph.calls == []


def test_query_parameter_is_required_and_length_limited() -> None:
    client = _client(ScriptedGraph())
    assert client.get("/api/search").status_code == 422
    assert client.get("/api/search", params={"q": "x" * 101}).status_code == 422
