import pytest
from neo4j.exceptions import ConstraintError

from app.graph.client import GraphClient
from app.graph.schema import CONSTRAINTS, INDEXES, apply_schema

pytestmark = pytest.mark.integration


async def test_apply_schema_is_idempotent(neo4j_graph: GraphClient) -> None:
    assert await apply_schema(neo4j_graph) == len(CONSTRAINTS) + len(INDEXES)
    await apply_schema(neo4j_graph)  # second run must not fail
    rows = await neo4j_graph.read("SHOW CONSTRAINTS YIELD name RETURN collect(name) AS names")
    assert "paper_doi" in rows[0]["names"]


async def test_duplicate_doi_is_rejected(neo4j_graph: GraphClient) -> None:
    await apply_schema(neo4j_graph)
    await neo4j_graph.write("CREATE (:Paper {id: 'a', doi: '10.1/x'})")
    with pytest.raises(ConstraintError):
        await neo4j_graph.write("CREATE (:Paper {id: 'b', doi: '10.1/x'})")
