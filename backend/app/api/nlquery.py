from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import AdminDep, GraphDep, LLMDep
from app.schemas.nlquery import NLQueryRequest, NLQueryResponse
from app.services.nlquery import ask_graph

router = APIRouter(tags=["nlquery"])


@router.post(
    "/query",
    summary="Ask a structural question in plain English; runs validated read-only Cypher",
    description=(
        "The configured LLM writes a Cypher query, which is validated against a read-only "
        "allow-list, checked by Neo4j's EXPLAIN, and run in a read transaction with a timeout "
        "and a row cap. The Cypher is returned so the answer can be audited. Calls a paid "
        "LLM, so it sits behind the admin dependency."
    ),
    response_model=NLQueryResponse,
    dependencies=[AdminDep],
)
async def query_graph(body: NLQueryRequest, graph: GraphDep, llm: LLMDep) -> NLQueryResponse:
    return await ask_graph(graph, await llm.get(), body.question)
