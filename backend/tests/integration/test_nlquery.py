import json

import pytest
from neo4j.exceptions import ClientError, Neo4jError

from app.ai.text2cypher import EXAMPLES
from app.graph.client import GraphClient
from app.graph.cypher_guard import validate_cypher
from app.services.nlquery import ask_graph
from tests.fakes import ScriptedLLM

pytestmark = pytest.mark.integration


async def test_explain_classifies_read_and_write_queries(neo4j_graph: GraphClient) -> None:
    assert await neo4j_graph.query_type("MATCH (p:Paper) RETURN p.title LIMIT 1") == "r"
    assert await neo4j_graph.query_type("MATCH (p:Paper) SET p.x = 1 RETURN p") != "r"
    with pytest.raises(Neo4jError):
        await neo4j_graph.query_type("MATCH (p:Paper RETURN p")


async def test_explain_does_not_execute(neo4j_graph: GraphClient) -> None:
    await neo4j_graph.query_type("CREATE (:ShouldNotExist)")
    assert await neo4j_graph.read("MATCH (n:ShouldNotExist) RETURN count(n) AS n") == [{"n": 0}]


@pytest.mark.parametrize("question, cypher", EXAMPLES)
async def test_prompt_examples_run_on_a_real_database(
    neo4j_graph: GraphClient, question: str, cypher: str
) -> None:
    checked = validate_cypher(cypher)
    assert await neo4j_graph.query_type(checked.cypher) == "r"
    await neo4j_graph.run_readonly_unchecked(checked.cypher, tx_timeout=10)


async def test_end_to_end_with_scripted_model(neo4j_graph: GraphClient) -> None:
    await neo4j_graph.write(
        "CREATE (:Author {id: 'a1', name: 'Ada'})-[:WROTE]->(:Paper {id: 'p1', title: 'T'})"
    )
    cypher = (
        "MATCH (a:Author)-[:WROTE]->(p:Paper) RETURN a.name AS author, count(p) AS papers LIMIT 5"
    )
    reply = json.dumps({"can_answer": True, "cypher": cypher, "explanation": "Counts."})
    result = await ask_graph(neo4j_graph, ScriptedLLM([reply]), "who wrote what?")
    assert result.rows == [{"author": "Ada", "papers": 1}]


async def test_server_side_timeout_aborts_runaway_queries(neo4j_graph: GraphClient) -> None:
    slow = "UNWIND range(1, 100000000) AS i WITH sum(i * i) AS s RETURN s"
    with pytest.raises(ClientError):
        await neo4j_graph.run_readonly_unchecked(slow, tx_timeout=0.5)
