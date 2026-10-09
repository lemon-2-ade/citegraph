import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.ai.embeddings import EmbedderCache, HashingEmbeddings
from app.ai.llm import LLMCache
from app.core.config import Settings
from app.main import create_app
from app.rag.pipeline import build_prompt, verify_citations
from app.schemas.rag import Relation, Source
from tests.fakes import ScriptedGraph, ScriptedLLM

CONFIG = {"model": HashingEmbeddings.model, "dimensions": 256, "provider": "hashing"}


def _row(pid: str, title: str, **extra: Any) -> dict[str, Any]:
    return {
        "id": pid, "title": title, "year": 2020, "doi": None, "arxiv_id": None,
        "citation_count": None, "pagerank": None, "is_stub": False,
        "cited_by_in_graph": 0, "venue": None, "authors": ["A. Author"], **extra,
    }  # fmt: skip


def _graph(**overrides: list[dict[str, Any]]) -> ScriptedGraph:
    responses = {
        "embeddings.config": [CONFIG],
        "search.keyword_papers": [_row("p1", "Attention", score=5.0)],
        "embeddings.search": [_row("p2", "Transformers", score=0.9)],
        "rag.passages": [
            _row("p1", "Attention", abstract="Attention is about weighting."),
            _row("p2", "Transformers", abstract="Transformers use attention."),
        ],
        "rag.expand": [_row("p3", "Seq2Seq", abstract="Earlier models.", links=2)],
        "rag.relations": [{"source": "p2", "target": "p1"}, {"source": "p2", "target": "p3"}],
    }
    responses.update(overrides)
    return ScriptedGraph(responses)


def _client(graph: ScriptedGraph, llm: ScriptedLLM) -> TestClient:
    settings = Settings(log_json=False, _env_file=None)  # type: ignore[call-arg]
    app = create_app(settings)
    app.state.graph = graph
    app.state.embedder = EmbedderCache(settings, HashingEmbeddings())
    app.state.llm = LLMCache(settings, llm)
    return TestClient(app)


def _reply(answer: str, answerable: bool = True) -> str:
    return json.dumps({"answer": answer, "answerable": answerable})


def test_verify_citations_drops_unknown_markers_and_collects_valid() -> None:
    text, cited = verify_citations("A [1] and B [2, 9] and C [7][3].", 3)
    assert text == "A [1] and B [2] and C [3]." and cited == {1, 2, 3}


def test_prompt_numbers_sources_lists_links_and_marks_text_untrusted() -> None:
    src = [
        Source(n=1, paper=_to_summary(_row("p1", "Attention")), role="retrieved", excerpt="x"),
        Source(n=2, paper=_to_summary(_row("p2", "Other")), role="graph"),
    ]
    system, user = build_prompt("What?", src, [Relation(source=2, target=1)])
    assert "untrusted" in system.content
    assert "[1] Attention" in user.content and "[2] cites [1]" in user.content
    assert "(no abstract available)" in user.content


def _to_summary(row: dict[str, Any]):  # type: ignore[no-untyped-def]
    from app.schemas.graph import PaperSummary

    return PaperSummary.model_validate(row)


def test_ask_returns_grounded_answer_with_sources_and_relations() -> None:
    llm = ScriptedLLM([_reply("Attention weights inputs [1]. Transformers build on it [2][9].")])
    graph = _graph()
    res = _client(graph, llm).post("/api/ask", json={"question": "What is attention?"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["grounded"] is True and "[9]" not in body["answer"]
    by_n = {s["n"]: s for s in body["sources"]}
    assert by_n[3]["role"] == "graph" and by_n[3]["links_to_retrieved"] == 2
    assert [by_n[n]["cited"] for n in (1, 2, 3)] == [True, True, False]
    assert {(r["source"], r["target"]) for r in body["relations"]} == {(2, 1), (2, 3)}
    assert body["retrieval"] == {
        "mode": "hybrid", "semantic_available": True, "note": None, "retrieved": 2, "expanded": 1,
    }  # fmt: skip
    user_prompt = llm.requests[0][1].content
    assert "Attention is about weighting." in user_prompt and "[2] cites [1]" in user_prompt
    expand_call = next(c for c in graph.calls if c[0] == "rag.expand")
    assert set(expand_call[2]["seeds"]) == {"p1", "p2"}


def test_uncited_answer_is_not_grounded() -> None:
    res = _client(_graph(), ScriptedLLM([_reply("Plausible but unsupported.")])).post(
        "/api/ask", json={"question": "What is attention?"}
    )
    assert res.json()["grounded"] is False


def test_unanswerable_is_reported() -> None:
    res = _client(_graph(), ScriptedLLM([_reply("The sources do not say.", False)])).post(
        "/api/ask", json={"question": "Who won the 1998 World Cup?"}
    )
    body = res.json()
    assert body["answerable"] is False and body["grounded"] is False


def test_no_relevant_papers_skips_the_llm() -> None:
    graph = _graph(**{"search.keyword_papers": [], "embeddings.search": []})
    llm = ScriptedLLM([])
    body = _client(graph, llm).post("/api/ask", json={"question": "zzzz qqqq"}).json()
    assert body["answerable"] is False and body["sources"] == [] and llm.requests == []


def test_sources_without_text_skip_the_llm() -> None:
    graph = _graph(**{"rag.passages": [_row("p1", "A"), _row("p2", "B")], "rag.expand": []})
    llm = ScriptedLLM([])
    body = _client(graph, llm).post("/api/ask", json={"question": "attention?"}).json()
    assert body["answerable"] is False and len(body["sources"]) == 2 and llm.requests == []


def test_semantic_outage_degrades_to_keyword_and_says_so() -> None:
    graph = _graph(**{"embeddings.config": []})
    # No config row means "not embedded yet"; the ScriptedGraph returns [] -> config() is None.
    llm = ScriptedLLM([_reply("Only keyword hits [1].")])
    body = _client(graph, llm).post("/api/ask", json={"question": "attention"}).json()
    assert body["retrieval"]["semantic_available"] is False
    assert "keyword" in body["retrieval"]["note"]


@pytest.mark.parametrize(
    "payload", [{"question": "x"}, {"question": "ok?" * 400}, {"question": "fine", "k": 99}]
)
def test_ask_validates_input(payload: dict[str, Any]) -> None:
    assert _client(_graph(), ScriptedLLM([])).post("/api/ask", json=payload).status_code == 422
