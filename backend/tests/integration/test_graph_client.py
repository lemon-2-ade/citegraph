import pytest
from neo4j.exceptions import ClientError

from app.graph.client import GraphClient

pytestmark = pytest.mark.integration


async def test_read_write_roundtrip(neo4j_graph: GraphClient) -> None:
    await neo4j_graph.write("CREATE (:Probe {v: $v})", {"v": 42})
    rows = await neo4j_graph.read("MATCH (p:Probe) RETURN p.v AS v")
    assert rows == [{"v": 42}]


async def test_read_transaction_rejects_writes(neo4j_graph: GraphClient) -> None:
    with pytest.raises(ClientError):
        await neo4j_graph.run_readonly_unchecked("CREATE (:ShouldNotExist)")
