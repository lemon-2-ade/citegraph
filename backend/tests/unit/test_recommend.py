from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.recommend import centroid
from tests.fakes import ScriptedGraph

CONFIG = {"model": "m", "dimensions": 2, "provider": "x"}


def _row(pid: str, title: str, **extra: Any) -> dict[str, Any]:
    return {
        "id": pid, "title": title, "year": 2020, "doi": None, "arxiv_id": None,
        "citation_count": None, "pagerank": None, "is_stub": False,
        "cited_by_in_graph": 0, "venue": None, "authors": [], **extra,
    }  # fmt: skip


def _client(graph: ScriptedGraph) -> TestClient:
    app = create_app(Settings(log_json=False, _env_file=None))  # type: ignore[call-arg]
    app.state.graph = graph
    return TestClient(app)


def test_centroid_is_unit_length_and_between_inputs() -> None:
    c = centroid([[1.0, 0.0], [0.0, 2.0]])
    assert c == pytest.approx([2**-0.5, 2**-0.5])
    assert centroid([]) == []


def test_recommend_validates_input() -> None:
    client = _client(ScriptedGraph())
    assert client.post("/api/recommendations", json={"paper_ids": []}).status_code == 422
    assert client.post("/api/recommendations", json={"paper_ids": ["x"] * 21}).status_code == 422


def test_unknown_seed_is_404() -> None:
    res = _client(ScriptedGraph({"analytics.summaries": []})).post(
        "/api/recommendations", json={"paper_ids": ["nope"]}
    )
    assert res.status_code == 404


def test_semantic_unavailable_degrades_with_a_note(monkeypatch: pytest.MonkeyPatch) -> None:
    async def ppr(self: Any, sources: list[str], limit: int) -> dict[str, float]:
        return {"c1": 0.2, "c2": 0.1}

    monkeypatch.setattr("app.services.recommend.NetworkXBackend.personalized_pagerank", ppr)
    graph = ScriptedGraph({"analytics.summaries": [_row("s1", "Seed")], "embeddings.vectors": []})
    res = _client(graph).post("/api/recommendations", json={"paper_ids": ["s1"]})
    assert res.status_code == 200, res.text
    assert res.json()["semantic_available"] is False and "citation links only" in res.json()["note"]


def test_fusion_combines_signals_and_explains(monkeypatch: pytest.MonkeyPatch) -> None:
    async def ppr(self: Any, sources: list[str], limit: int) -> dict[str, float]:
        return {"c1": 0.2, "c2": 0.1}

    monkeypatch.setattr("app.services.recommend.NetworkXBackend.personalized_pagerank", ppr)

    class G(ScriptedGraph):
        async def read(self, query: str, params: Any = None, *, label: str = "") -> Any:
            if label == "analytics.summaries":
                ids = params["ids"]
                return [_row(i, f"T-{i}") for i in ids]
            return await super().read(query, params, label=label)

    graph = G(
        {
            "embeddings.vectors": [{"id": "s1", "vector": [1.0, 0.0]}],
            "embeddings.config": [CONFIG],
            "embeddings.search": [_row("c2", "x", score=0.9), _row("s1", "x", score=1.0)],
            "recommend.linked": [{"candidate": "c1", "seeds": ["s1"]}],
        }
    )
    body = (
        _client(graph).post("/api/recommendations", json={"paper_ids": ["s1"], "limit": 5}).json()
    )
    recs = {r["paper"]["id"]: r for r in body["recommendations"]}
    assert set(recs) == {"c1", "c2"}  # the seed itself is never recommended
    assert recs["c2"]["score"] > recs["c1"]["score"]  # in both rankings beats graph-only
    assert {r["kind"] for r in recs["c2"]["reasons"]} == {"citation_proximity", "similar_meaning"}
    assert recs["c1"]["linked_to"] == ["T-s1"]
    assert recs["c1"]["reasons"][0]["kind"] == "directly_linked"
