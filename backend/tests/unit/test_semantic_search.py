from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.ai.embeddings import EmbedderCache, HashingEmbeddings
from app.core.config import Settings
from app.main import create_app
from app.repositories.embeddings import SemanticUnavailableError, index_ddl
from app.services.embedding import embed_papers
from app.services.paper_search import reciprocal_rank_fusion
from tests.fakes import ScriptedGraph


def _row(pid: str, score: float, title: str = "T") -> dict[str, Any]:
    return {
        "id": pid, "title": title, "year": 2020, "doi": None, "arxiv_id": None,
        "citation_count": None, "pagerank": None, "is_stub": False,
        "cited_by_in_graph": 0, "venue": None, "authors": [], "score": score,
    }  # fmt: skip


CONFIG = {"model": HashingEmbeddings.model, "dimensions": 256, "provider": "hashing"}


def _client(graph: ScriptedGraph) -> TestClient:
    settings = Settings(log_json=False)
    app = create_app(settings)
    app.state.graph = graph
    app.state.embedder = EmbedderCache(settings, HashingEmbeddings())
    return TestClient(app)


def test_rrf_rewards_agreement_between_rankings() -> None:
    fused = reciprocal_rank_fusion({"keyword": ["a", "b", "c"], "semantic": ["c", "a", "d"]})
    ids = [i for i, _ in fused]
    assert ids[:2] == ["a", "c"]  # in both lists beat items in only one
    assert ids[-1] == "d" or ids[-1] == "b"
    assert dict(fused)["a"] == pytest.approx(1 / 61 + 1 / 62)


def test_index_ddl_validates_dimensions() -> None:
    ddl = index_ddl(384)
    assert "`vector.dimensions`: 384" in ddl and "'cosine'" in ddl
    for bad in (0, -1, 100_000):
        with pytest.raises(ValueError, match="unsupported"):
            index_ddl(bad)


def test_hybrid_merges_both_rankings_and_labels_sources() -> None:
    graph = ScriptedGraph(
        {
            "embeddings.config": [CONFIG],
            "search.keyword_papers": [_row("p1", 5.0), _row("p2", 3.0)],
            "embeddings.search": [_row("p2", 0.9), _row("p3", 0.8)],
        }
    )
    body = _client(graph).get("/api/search/papers", params={"q": "attention"}).json()
    hits = {h["paper"]["id"]: h for h in body["hits"]}
    assert body["mode"] == "hybrid" and body["semantic_available"] is True
    assert body["hits"][0]["paper"]["id"] == "p2"  # found by both
    assert hits["p2"]["matched_by"] == ["keyword", "semantic"]
    assert hits["p1"]["matched_by"] == ["keyword"] and hits["p1"]["semantic_rank"] is None
    assert hits["p3"]["matched_by"] == ["semantic"] and hits["p3"]["keyword_rank"] is None


def test_semantic_mode_returns_cosine_scores_in_order() -> None:
    graph = ScriptedGraph(
        {"embeddings.config": [CONFIG], "embeddings.search": [_row("p1", 0.9), _row("p2", 0.4)]}
    )
    body = _client(graph).get("/api/search/papers", params={"q": "x y", "mode": "semantic"}).json()
    assert [h["score"] for h in body["hits"]] == [0.9, 0.4]
    assert all(h["matched_by"] == ["semantic"] for h in body["hits"])


def test_hybrid_degrades_to_keyword_when_embeddings_are_missing() -> None:
    graph = ScriptedGraph({"search.keyword_papers": [_row("p1", 5.0)]})  # no embeddings.config
    body = _client(graph).get("/api/search/papers", params={"q": "attention"}).json()
    assert body["semantic_available"] is False
    assert "researchgraph embed" in body["note"]
    assert [h["paper"]["id"] for h in body["hits"]] == ["p1"]


def test_semantic_mode_without_embeddings_is_a_clear_conflict() -> None:
    response = _client(ScriptedGraph()).get(
        "/api/search/papers", params={"q": "attention", "mode": "semantic"}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "semantic_unavailable"


def test_model_mismatch_is_reported_not_silently_mixed() -> None:
    graph = ScriptedGraph({"embeddings.config": [{**CONFIG, "model": "other-model"}]})
    response = _client(graph).get(
        "/api/search/papers", params={"q": "attention", "mode": "semantic"}
    )
    assert response.status_code == 409
    assert "--rebuild" in response.json()["error"]["message"]


def test_short_query_returns_nothing_and_touches_no_index() -> None:
    graph = ScriptedGraph()
    body = _client(graph).get("/api/search/papers", params={"q": "a"}).json()
    assert body["hits"] == [] and graph.calls == []


def test_semantic_similar_uses_stored_vector() -> None:
    graph = ScriptedGraph(
        {"embeddings.exists": [{"id": "p1"}], "embeddings.similar": [_row("p2", 0.83)]}
    )
    body = _client(graph).get("/api/papers/p1/semantic-similar").json()
    assert body[0]["method"] == "semantic"
    assert "0.83" in body[0]["explanation"]


def test_semantic_similar_unknown_paper_is_404() -> None:
    assert _client(ScriptedGraph()).get("/api/papers/nope/semantic-similar").status_code == 404


class _Sequenced(ScriptedGraph):
    """Returns each scripted candidate page once, then an empty page."""

    def __init__(self, pages: list[list[dict[str, Any]]], config: dict[str, Any] | None) -> None:
        super().__init__({"embeddings.config": [config] if config else []})
        self.pages = pages

    async def read(self, query: Any, params: Any = None, *, label: str = "") -> Any:
        if label == "embeddings.candidates":
            self.calls.append((label, query, dict(params or {})))
            return self.pages.pop(0) if self.pages else []
        return await super().read(query, params, label=label)


def _cand(
    pid: str, title: str, hash_: str | None = None, model: str | None = None
) -> dict[str, Any]:
    return {
        "id": pid, "title": title, "abstract": f"About {title}", "description": None,
        "hash": hash_, "model": model, "has_vector": hash_ is not None,
    }  # fmt: skip


async def test_embed_papers_stores_new_and_skips_unchanged() -> None:
    from app.ai.embeddings import paper_text, text_hash

    unchanged_hash = text_hash(paper_text("Same", "About Same", None))
    graph = _Sequenced(
        [[_cand("p1", "New"), _cand("p2", "Same", unchanged_hash, HashingEmbeddings.model)]], None
    )
    stats = await embed_papers(graph, HashingEmbeddings(), batch_size=10)
    assert (stats.scanned, stats.embedded, stats.unchanged) == (2, 1, 1)
    stored = next(c for c in graph.calls if c[0] == "embeddings.store")
    assert [r["id"] for r in stored[2]["rows"]] == ["p1"]
    assert len(stored[2]["rows"][0]["vector"]) == 256
    assert any(c[0] == "embeddings.ensure_index" for c in graph.calls)


async def test_embed_papers_refuses_a_model_change_without_rebuild() -> None:
    graph = _Sequenced([], {**CONFIG, "model": "old-model"})
    with pytest.raises(SemanticUnavailableError, match="--rebuild"):
        await embed_papers(graph, HashingEmbeddings())
    await embed_papers(graph, HashingEmbeddings(), rebuild=True)
    assert any(c[0] == "embeddings.drop_index" for c in graph.calls)
