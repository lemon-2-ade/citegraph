from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import ResponseModel


class NLQueryRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class NLQueryResponse(ResponseModel):
    question: str
    # False when the schema cannot answer the question; ``message`` says why.
    answerable: bool = True
    message: str | None = None
    cypher: str | None = None
    explanation: str | None = None
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    # True when the row cap was reached, so more rows may exist.
    truncated: bool = False
    # Generation attempts used (2 means the first draft was rejected and repaired).
    attempts: int = 1
    model: str | None = None
