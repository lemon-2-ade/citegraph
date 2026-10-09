import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from neo4j.exceptions import ClientError

from app.ai.llm import LLMCache
from app.ai.text2cypher import EXAMPLES, build_messages
from app.core.config import Settings
from app.graph.cypher_guard import validate_cypher
from app.main import create_app
from app.services.nlquery import clean_value
from tests.fakes import ScriptedGraph, ScriptedLLM

GOOD = "MATCH (a:Author)-[:WROTE]->(p:Paper) RETURN a.name AS author, count(p) AS n ORDER BY n DESC LIMIT 5"  # noqa: E501


def _reply(cypher: str, can_answer: bool = True, explanation: str = "Counts papers.") -> str:
    return json.dumps({"can_answer": can_answer, "cypher": cypher, "explanation": explanation})


def _client(graph: ScriptedGraph, llm: ScriptedLLM) -> TestClient:
    settings = Settings(log_json=False, _env_file=None)  # type: ignore[call-arg]
    app = create_app(settings)
    app.state.graph = graph
    app.state.llm = LLMCache(settings, llm)
    return TestClient(app)


@pytest.mark.parametrize("question, cypher", EXAMPLES)
def test_prompt_examples_pass_the_validator(question: str, cypher: str) -> None:
    validate_cypher(cypher)


def test_prompt_states_schema_and_rules() -> None:
    system = build_messages("q")[0].content
    assert "(:Paper)-[:CITES]->(:Paper)" in system and "No CREATE" in system
    assert "embedding" not in system


def test_happy_path_returns_rows_and_the_cypher() -> None:
    graph = ScriptedGraph({"nlquery.run": [{"author": "A", "n": 3}, {"author": "B", "n": 1}]})
    llm = ScriptedLLM([_reply(GOOD)])
    res = _client(graph, llm).post("/api/query", json={"question": "top authors?"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["cypher"] == GOOD and body["columns"] == ["author", "n"]
    assert body["row_count"] == 2 and body["truncated"] is False and body["attempts"] == 1
    assert ("query_type", GOOD, {}) in graph.calls


def test_rejected_query_is_repaired_once_with_feedback() -> None:
    graph = ScriptedGraph({"nlquery.run": [{"author": "A", "n": 3}]})
    llm = ScriptedLLM([_reply("MATCH (p:Paper) DETACH DELETE p RETURN 1"), _reply(GOOD)])
    body = _client(graph, llm).post("/api/query", json={"question": "top authors?"}).json()
    assert body["attempts"] == 2 and body["cypher"] == GOOD
    feedback = llm.requests[1][-1].content
    assert "rejected" in feedback and "DETACH" in feedback
    assert not [c for c in graph.calls if c[0] == "nlquery.run" and "DELETE" in c[1]]


def test_two_rejections_give_422_and_nothing_runs() -> None:
    bad = _reply("MATCH (p:Paper) SET p.title = 'x' RETURN p")
    graph = ScriptedGraph()
    res = _client(graph, ScriptedLLM([bad, bad])).post("/api/query", json={"question": "hack it"})
    assert res.status_code == 422 and "SET" in res.json()["error"]["message"]
    assert not [c for c in graph.calls if c[0] == "nlquery.run"]


def test_neo4j_classifying_query_as_write_blocks_it() -> None:
    graph = ScriptedGraph()
    graph.query_types = ["rw", "rw"]
    res = _client(graph, ScriptedLLM([_reply(GOOD), _reply(GOOD)])).post(
        "/api/query", json={"question": "anything"}
    )
    assert res.status_code == 422
    assert not [c for c in graph.calls if c[0] == "nlquery.run"]


def test_unanswerable_question_returns_the_models_reason() -> None:
    llm = ScriptedLLM([_reply("", False, "The graph does not store citations by country.")])
    body = _client(ScriptedGraph(), llm).post("/api/query", json={"question": "by country?"}).json()
    assert body["answerable"] is False and "country" in body["message"] and body["cypher"] is None


def test_execution_failure_hides_server_details() -> None:
    class Failing(ScriptedGraph):
        async def run_readonly_unchecked(self, *a: Any, **k: Any) -> Any:
            raise ClientError("Neo.ClientError.Transaction.TransactionTimedOut secret-detail")

    res = _client(Failing(), ScriptedLLM([_reply(GOOD)])).post(
        "/api/query", json={"question": "slow one"}
    )
    assert res.status_code == 422 and "secret-detail" not in res.text


def test_hitting_the_limit_marks_truncated() -> None:
    graph = ScriptedGraph({"nlquery.run": [{"n": i} for i in range(5)]})
    body = (
        _client(graph, ScriptedLLM([_reply(GOOD)]))
        .post("/api/query", json={"question": "top authors?"})
        .json()
    )
    assert body["truncated"] is True


def test_clean_value_strips_vectors_and_bounds_size() -> None:
    cleaned = clean_value({"title": "x" * 1000, "embedding": [0.1] * 384, "ids": list(range(100))})
    assert "embedding" not in cleaned and len(cleaned["title"]) == 300 and len(cleaned["ids"]) == 25
    assert clean_value(object()).startswith("<object")
