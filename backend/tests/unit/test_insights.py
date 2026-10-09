import json
from typing import Any

from fastapi.testclient import TestClient

from app.ai.insights import insight_hash, insight_input
from app.ai.llm import LLMCache
from app.core.config import Settings
from app.main import create_app
from app.services.insights import generate_insights
from tests.fakes import ScriptedGraph, ScriptedLLM

REPLY = json.dumps({"summary": "S.", "kind": "survey", "keywords": ["rag"]})
TEXT = insight_input("Title", "An abstract.", None)
ROW: dict[str, Any] = {
    "id": "p1", "title": "Title", "abstract": "An abstract.", "description": None,
    "insight_json": None, "hash": None, "model": None, "generated_at": None,
}  # fmt: skip


def _client(graph: ScriptedGraph, llm: ScriptedLLM) -> TestClient:
    settings = Settings(log_json=False, _env_file=None)  # type: ignore[call-arg]
    app = create_app(settings)
    app.state.graph = graph
    app.state.llm = LLMCache(settings, llm)
    return TestClient(app)


def test_get_without_insight_is_404() -> None:
    res = _client(ScriptedGraph({"insights.get": [ROW]}), ScriptedLLM()).get(
        "/api/papers/p1/insight"
    )
    assert res.status_code == 404


def test_get_missing_paper_is_404() -> None:
    assert _client(ScriptedGraph(), ScriptedLLM()).get("/api/papers/x/insight").status_code == 404


def test_post_generates_stores_and_returns() -> None:
    graph = ScriptedGraph({"insights.get": [ROW], "insights.store": [{"generated_at": "t0"}]})
    llm = ScriptedLLM([REPLY])
    res = _client(graph, llm).post("/api/papers/p1/insight")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["cached"] is False and body["insight"]["kind"] == "survey"
    assert body["model"] == "scripted-1"
    stored = next(c for c in graph.calls if c[0] == "insights.store")[2]
    assert stored["hash"] == insight_hash(TEXT) and "survey" in stored["json"]


def test_post_reuses_current_insight_without_calling_llm() -> None:
    row = {**ROW, "insight_json": REPLY, "hash": insight_hash(TEXT), "model": "m",
           "generated_at": "t"}  # fmt: skip
    llm = ScriptedLLM([])
    res = _client(ScriptedGraph({"insights.get": [row]}), llm).post("/api/papers/p1/insight")
    assert res.json()["cached"] is True and llm.requests == []


def test_stale_insight_is_flagged_on_get() -> None:
    row = {**ROW, "insight_json": REPLY, "hash": "old", "model": "m", "generated_at": "t"}
    body = _client(ScriptedGraph({"insights.get": [row]}), ScriptedLLM()).get(
        "/api/papers/p1/insight").json()  # fmt: skip
    assert body["stale"] is True


def test_post_rejects_paper_without_abstract() -> None:
    row = {**ROW, "abstract": None}
    res = _client(ScriptedGraph({"insights.get": [row]}), ScriptedLLM()).post(
        "/api/papers/p1/insight"
    )
    assert res.status_code == 422


async def test_batch_skips_done_and_isolates_failures() -> None:
    done = {"id": "p1", "title": "Title", "abstract": "An abstract.", "description": None,
            "hash": insight_hash(TEXT)}  # fmt: skip
    todo = {**done, "id": "p2", "hash": None}
    nothing = {**done, "id": "p3", "abstract": None, "hash": None}
    broken = {**done, "id": "p4", "hash": None}
    graph = ScriptedGraph({"insights.candidates": [done, todo, nothing, broken]})

    class FlakyLLM(ScriptedLLM):
        async def complete(self, messages: Any, **kw: Any) -> Any:
            if len(self.requests) >= 1 and not self.replies:
                raise RuntimeError("boom")
            return await super().complete(messages, **kw)

    # Single page of candidates: the second fetch returns the same rows, so cap with a
    # graph that empties after the first call.
    calls = {"n": 0}
    original = graph.read

    async def once(query: str, params: Any = None, *, label: str = "") -> Any:
        if label == "insights.candidates":
            calls["n"] += 1
            if calls["n"] > 1:
                return []
        return await original(query, params, label=label)

    graph.read = once  # type: ignore[method-assign]
    graph.write = once  # type: ignore[method-assign]
    graph.responses["insights.get"] = [{**ROW, "id": "p2"}]
    graph.responses["insights.store"] = [{"generated_at": "t"}]
    stats = await generate_insights(graph, FlakyLLM([REPLY]), concurrency=1)  # type: ignore[arg-type]
    assert (stats.scanned, stats.unchanged, stats.without_text) == (4, 1, 1)
    assert stats.generated == 1 and stats.failed == 1
