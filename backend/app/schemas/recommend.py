from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ResponseModel
from app.schemas.graph import PaperSummary


class RecommendRequest(BaseModel):
    # The reading list to recommend from: papers the user has read or cares about.
    paper_ids: list[str] = Field(min_length=1, max_length=20)
    limit: int = Field(default=10, ge=1, le=30)


class Reason(ResponseModel):
    kind: Literal["citation_proximity", "similar_meaning", "directly_linked"]
    text: str


class Recommendation(ResponseModel):
    paper: PaperSummary
    # Reciprocal-rank-fusion score across the signals; only meaningful for ordering.
    score: float
    reasons: list[Reason] = Field(default_factory=list)
    # Titles of the reading-list papers this one is directly linked to by citation.
    linked_to: list[str] = Field(default_factory=list)


class RecommendResponse(ResponseModel):
    seeds: list[PaperSummary]
    recommendations: list[Recommendation] = Field(default_factory=list)
    semantic_available: bool = True
    note: str | None = None
