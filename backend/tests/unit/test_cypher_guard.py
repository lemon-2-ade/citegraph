import pytest

from app.graph.cypher_guard import CypherRejectedError, validate_cypher

GOOD = "MATCH (p:Paper)-[:CITES]->(q:Paper) WHERE p.year > 2018 RETURN p.title, q.title LIMIT 10"


def test_accepts_read_query_unchanged() -> None:
    v = validate_cypher(GOOD)
    assert v.cypher == GOOD and v.limit == 10
    assert v.labels == {"Paper"} and v.rel_types == {"CITES"}


def test_adds_a_limit_when_missing_and_drops_trailing_semicolon() -> None:
    v = validate_cypher("MATCH (a:Author) RETURN a.name ORDER BY a.name;")
    assert v.cypher.endswith("\nLIMIT 50") and v.limit == 50 and ";" not in v.cypher


@pytest.mark.parametrize(
    "query",
    [
        "CREATE (p:Paper {id: 'x'}) RETURN p",
        "MATCH (p:Paper) SET p.title = 'x' RETURN p",
        "MATCH (p:Paper) DETACH DELETE p RETURN 1",
        "MATCH (p:Paper) REMOVE p.title RETURN p",
        "MERGE (p:Paper {id:'x'}) RETURN p",
        "MATCH (p:Paper) FOREACH (x IN [1] | SET p.a = x) RETURN p",
        "LOAD CSV FROM 'http://x' AS r RETURN r",
        "CALL apoc.cypher.runMany('x', {}) YIELD row RETURN row",
        "CALL dbms.listConfig() YIELD name RETURN name",
        "CALL db.index.fulltext.queryNodes('secret_idx', 'x') YIELD node RETURN node",
        "SHOW DATABASES",
        "MATCH (p:Paper) RETURN p.title UNION MATCH (a:Author) RETURN a.name",
        "MATCH (p:Paper) RETURN p LIMIT 10; MATCH (n) DETACH DELETE n",
        "MATCH (p:Paper) WHERE p.id = $id RETURN p",
        "MATCH (p:Paper) RETURN p // hidden",
        "MATCH (p:`Paper`) RETURN p",
        "EXPLAIN MATCH (p:Paper) RETURN p",
    ],
)
def test_rejects_writes_procedures_and_other_unsafe_forms(query: str) -> None:
    with pytest.raises(CypherRejectedError):
        validate_cypher(query)


def test_keywords_inside_strings_and_property_names_are_not_false_positives() -> None:
    v = validate_cypher("MATCH (p:Paper) WHERE p.title CONTAINS 'create set delete' RETURN p.title")
    assert v.limit == 50
    validate_cypher("MATCH (c:Community) RETURN c.size ORDER BY c.size DESC LIMIT 5")


def test_allowed_fulltext_call() -> None:
    q = (
        "CALL db.index.fulltext.queryNodes('paper_text', 'graph') YIELD node, score "
        "RETURN node.title, score LIMIT 5"
    )
    assert validate_cypher(q).limit == 5


@pytest.mark.parametrize(
    "query, message",
    [
        ("MATCH (x:Person) RETURN x", "Unknown node label"),
        ("MATCH (:Paper)-[:LIKES]->(:Paper) RETURN 1", "Unknown relationship"),
        ("MATCH (p:Paper) RETURN p.embedding", "Unknown property 'embedding'"),
        ("MATCH (p:Paper) RETURN p.insight_json", "Unknown property"),
        ("MATCH (p:Paper)-[:CITES*]->(q) RETURN q.title", "bounded"),
        ("MATCH (p:Paper)-[:CITES*1..9]->(q) RETURN q.title", "at most 4"),
        ("MATCH (p:Paper) RETURN p.title LIMIT 5000", "at most 100"),
        ("MATCH (p:Paper) RETURN p.title LIMIT 5 SKIP 2", "end of the query"),
        ("MATCH (p:Paper) WHERE p.title = 'oops RETURN p", "Unterminated"),
        ("MATCH (p:Paper) " + "x" * 2000 + " RETURN p", "longer than"),
    ],
)
def test_rejects_with_actionable_message(query: str, message: str) -> None:
    with pytest.raises(CypherRejectedError, match=message):
        validate_cypher(query)


def test_bounded_variable_length_path_is_ok() -> None:
    validate_cypher("MATCH (p:Paper)-[:CITES*1..3]->(q:Paper) RETURN DISTINCT q.title LIMIT 10")
    validate_cypher("MATCH (p:Paper)-[:CITES*2]->(q:Paper) RETURN q.title LIMIT 10")


def test_function_namespaces_are_not_treated_as_properties() -> None:
    validate_cypher("RETURN date.truncate('year', date()) AS d LIMIT 1")
