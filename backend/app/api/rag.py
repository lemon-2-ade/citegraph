from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import AdminDep, EmbedderDep, GraphDep, LLMDep
from app.rag.pipeline import answer_question
from app.schemas.rag import AskRequest, AskResponse

router = APIRouter(tags=["rag"])


@router.post(
    "/ask",
    summary="Answer a research question from the graph, with numbered citations",
    description=(
        "Retrieves papers by hybrid search, expands through citation links, and asks the "
        "configured LLM to answer using only those sources. Calls a paid LLM, so it sits "
        "behind the admin dependency."
    ),
    response_model=AskResponse,
    dependencies=[AdminDep],
)
async def ask(body: AskRequest, graph: GraphDep, embedder: EmbedderDep, llm: LLMDep) -> AskResponse:
    return await answer_question(graph, embedder, await llm.get(), body)
