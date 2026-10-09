from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ResponseModel
from app.schemas.graph import PaperSummary


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    # How many papers to retrieve by hybrid search before graph expansion.
    k: int = Field(default=6, ge=1, le=12)
    # Extra papers pulled in through citation links to the retrieved ones (0 disables).
    expand: int = Field(default=3, ge=0, le=8)


class Source(ResponseModel):
    n: int  # the number the answer uses to cite this paper, as [n]
    paper: PaperSummary
    role: Literal["retrieved", "graph"]
    # Retrieval score for "retrieved" sources; None for graph-expanded ones.
    score: float | None = None
    # For "graph" sources: how many retrieved papers it is directly linked to by citations.
    links_to_retrieved: int = 0
    excerpt: str | None = None
    cited: bool = False


class Relation(ResponseModel):
    """``source`` cites ``target`` (numbers refer to ``Source.n``)."""

    source: int
    target: int


class Retrieval(ResponseModel):
    mode: str
    semantic_available: bool = True
    note: str | None = None
    retrieved: int = 0
    expanded: int = 0


class AskResponse(ResponseModel):
    question: str
    answer: str
    # False when the sources do not contain an answer (or nothing relevant was found).
    answerable: bool = True
    # True only when the answer cites at least one real source.
    grounded: bool = False
    sources: list[Source] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    retrieval: Retrieval
    model: str | None = None
