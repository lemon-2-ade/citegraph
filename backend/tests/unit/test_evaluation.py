import json
from pathlib import Path
from typing import Any

import pytest

from app.evaluation import runner
from app.evaluation.datasets import (
    NLQueryCase,
    RagCase,
    RetrievalCase,
    default_dir,
    load_nlquery,
    load_rag,
    load_retrieval,
)
from app.evaluation.metrics import (
    hit_at_k,
    ndcg_at_k,
    recall_at_k,
    reciprocal_rank,
    rows_as_multiset,
    same_result,
)
from app.graph.cypher_guard import validate_cypher
from app.schemas.graph import PaperHit, PaperSearchResults, PaperSummary
from tests.fakes import ScriptedGraph, ScriptedLLM


def test_ranking_metrics_on_known_lists() -> None:
    ranked = ["x", "a", "y", "b"]
    rel = {"a", "b", "c"}
    assert recall_at_k(ranked, rel, 2) == pytest.approx(1 / 3)
    assert recall_at_k(ranked, rel, 4) == pytest.approx(2 / 3)
    assert hit_at_k(ranked, rel, 1) == 0.0 and hit_at_k(ranked, rel, 2) == 1.0
    assert reciprocal_rank(ranked, rel) == 0.5 and reciprocal_rank(["z"], rel) == 0.0
    # DCG = 1/log2(3) + 1/log2(5); ideal = 1 + 1/log2(3) + 1/log2(4)
    assert ndcg_at_k(ranked, rel, 4) == pytest.approx(
        (1 / 1.5849625 + 1 / 2.3219281) / (1 + 1 / 1.5849625 + 0.5), rel=1e-4
    )
    assert ndcg_at_k(["a"], {"a"}, 10) == 1.0


def test_result_comparison_ignores_names_and_order_but_not_duplicates() -> None:
    gold = [{"n": 3, "t": "x"}, {"n": 1, "t": "y"}]
    assert same_result(gold, [{"b": "y", "a": 1}, {"b": "x", "a": 3}])
    assert not same_result(gold, [{"n": 3, "t": "x"}])
    assert rows_as_multiset([{"v": 1}, {"v": 1}])[("1",)] == 2
    assert same_result([{"v": 0.1 + 0.2}], [{"v": 0.3}])


def test_gold_datasets_load_and_are_consistent() -> None:
    retrieval, nlquery, rag = load_retrieval(), load_nlquery(), load_rag()
    assert len(retrieval) >= 20 and len(nlquery) >= 8 and len(rag) >= 8
    seed = json.loads((default_dir().parent / "seed" / "papers.json").read_text())
    keys = {p["key"] for p in seed["papers"]}
    for case in retrieval:
        assert set(case.relevant) <= keys, case.q
    for rcase in rag:
        assert set(rcase.expect_sources) <= keys, rcase.q
    assert any(c.unanswerable for c in rag)


def test_gold_cypher_stays_inside_the_allowed_language() -> None:
    for case in load_nlquery():
        validate_cypher(case.gold)


def test_bad_dataset_gives_a_clear_error(tmp_path: Path) -> None:
    path = tmp_path / "x.json"
    path.write_text("{}")
    with pytest.raises(Exception, match="Cannot read dataset"):
        load_retrieval(path)


def _hit(pid: str) -> PaperHit:
    return PaperHit(paper=PaperSummary(id=pid, title=pid), score=1.0)


async def test_retrieval_eval_aggregates_per_mode_and_style(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_search(graph: Any, embedder: Any, q: str, mode: str, limit: int) -> Any:
        order = ["id-b", "id-a"] if mode == "keyword" else ["id-a", "id-b"]
        return PaperSearchResults(query=q, mode=mode, hits=[_hit(i) for i in order])  # type: ignore[arg-type]

    monkeypatch.setattr(runner, "search_papers", fake_search)
    graph = ScriptedGraph(
        {
            "eval.present": [{"key": "a"}],
            "eval.seed_keys": [{"id": "id-a", "key": "a"}, {"id": "id-b", "key": "b"}],
        }
    )
    cases = [
        RetrievalCase(q="q1", style="lexical", relevant=["a"]),
        RetrievalCase(q="q2", style="paraphrase", relevant=["a", "gone"]),
    ]
    report = await runner.eval_retrieval(graph, None, cases, modes=["keyword", "hybrid"])  # type: ignore[arg-type]
    assert report["missing_seed_keys"] == ["gone"]
    assert report["modes"]["keyword"]["mrr"] == 0.5 and report["modes"]["hybrid"]["mrr"] == 1.0
    assert report["modes"]["hybrid"]["by_style"]["paraphrase"]["n"] == 1
    assert "| hybrid | 2 |" in runner.format_markdown("retrieval", report)


async def test_retrieval_eval_reports_unavailable_semantic(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.repositories.embeddings import SemanticUnavailableError

    async def failing(*a: Any, **k: Any) -> Any:
        raise SemanticUnavailableError("run embed first")

    monkeypatch.setattr(runner, "search_papers", failing)
    graph = ScriptedGraph({"eval.present": [{"key": "a"}]})
    report = await runner.eval_retrieval(
        graph,
        None,
        [RetrievalCase(q="q", relevant=["a"])],
        modes=["semantic"],  # type: ignore[arg-type]
    )
    assert report["modes"]["semantic"] == {"unavailable": "run embed first"}


async def test_nlquery_eval_counts_correct_and_failed() -> None:
    good = json.dumps({"can_answer": True, "explanation": "n",
                       "cypher": "MATCH (p:Paper) RETURN count(p) AS total LIMIT 5"})  # fmt: skip
    graph = ScriptedGraph({"eval.gold": [{"n": 7}], "nlquery.run": [{"total": 7}]})
    cases = [NLQueryCase(q="how many", gold="MATCH (p:Paper) RETURN count(p) AS n")]
    report = await runner.eval_nlquery(graph, ScriptedLLM([good]), cases)  # type: ignore[arg-type]
    assert report["execution_accuracy"] == 1.0 and report["first_attempt_rate"] == 1.0

    graph.responses["nlquery.run"] = [{"total": 8}]
    wrong = await runner.eval_nlquery(graph, ScriptedLLM([good]), cases)  # type: ignore[arg-type]
    assert wrong["execution_accuracy"] == 0.0 and len(wrong["failures"]) == 1

    bad = json.dumps({"can_answer": True, "explanation": "", "cypher": "MATCH (n) DELETE n"})
    failed = await runner.eval_nlquery(graph, ScriptedLLM([bad, bad]), cases)  # type: ignore[arg-type]
    assert (
        failed["query_produced_rate"] == 0.0
        and failed["failures"][0]["error"] == "validation_failed"
    )


async def test_rag_eval_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.schemas.rag import AskResponse, Retrieval, Source

    def response(q: str, *, answerable: bool, grounded: bool) -> AskResponse:
        src = Source(
            n=1, paper=PaperSummary(id="id-a", title="A"), role="retrieved", cited=grounded
        )
        return AskResponse(question=q, answer="x [1]", answerable=answerable, grounded=grounded,
                           sources=[src], retrieval=Retrieval(mode="hybrid"))  # fmt: skip

    async def fake_answer(graph: Any, embedder: Any, llm: Any, request: Any) -> AskResponse:
        if "football" in request.question:
            return response(request.question, answerable=False, grounded=False)
        return response(request.question, answerable=True, grounded=True)

    monkeypatch.setattr(runner, "answer_question", fake_answer)
    graph = ScriptedGraph({"eval.seed_keys": [{"id": "id-a", "key": "a"}]})
    llm = ScriptedLLM([json.dumps({"supported": True, "unsupported_claims": []})])
    cases = [
        RagCase(q="what is a", expect_sources=["a", "b"]),
        RagCase(q="football?", unanswerable=True),
    ]
    report = await runner.eval_rag(graph, None, llm, cases, judge=True)  # type: ignore[arg-type]
    assert report["grounded_rate"] == 1.0 and report["source_recall"] == 0.5
    assert report["abstention_rate_on_unanswerable"] == 1.0
    assert report["faithfulness"] == 1.0 and report["judged"] == 1
