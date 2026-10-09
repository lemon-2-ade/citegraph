from __future__ import annotations

from pydantic import Field

from app.schemas.common import ResponseModel
from app.schemas.graph import PaperSummary


class PathStep(ResponseModel):
    position: int  # 1 = read first
    paper: PaperSummary
    # How many other papers on this path cite this one: high = foundational to the path.
    cited_by_on_path: int = 0
    # Titles of earlier papers on the path that this one cites ("read these first").
    builds_on: list[str] = Field(default_factory=list)
    reason: str


class ReadingPath(ResponseModel):
    focus: str  # human-readable description of the starting point
    steps: list[PathStep]
    candidates: int  # how many papers were considered
    note: str
