"""Gold datasets for evaluation (JSON files under ``data/eval``)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.core.errors import ValidationFailedError


def default_dir() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "data" / "eval"
        if candidate.is_dir():
            return candidate
    raise ValidationFailedError("Could not find data/eval; pass --dataset.")


class RetrievalCase(BaseModel):
    q: str
    style: Literal["lexical", "paraphrase"] = "lexical"
    relevant: list[str] = Field(min_length=1)  # seed keys


class NLQueryCase(BaseModel):
    q: str
    gold: str


class RagCase(BaseModel):
    q: str
    expect_sources: list[str] = Field(default_factory=list)  # seed keys
    unanswerable: bool = False


def _load(path: Path, key: str) -> list[dict[str, object]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data[key]
    except (OSError, KeyError, json.JSONDecodeError) as exc:
        raise ValidationFailedError(f"Cannot read dataset {path}: {exc}") from exc
    if not isinstance(items, list):
        raise ValidationFailedError(f"Dataset {path} must contain a '{key}' list.")
    return items


def load_retrieval(path: Path | None = None) -> list[RetrievalCase]:
    rows = _load(path or default_dir() / "retrieval.json", "queries")
    return [RetrievalCase.model_validate(r) for r in rows]


def load_nlquery(path: Path | None = None) -> list[NLQueryCase]:
    rows = _load(path or default_dir() / "nlquery.json", "cases")
    return [NLQueryCase.model_validate(r) for r in rows]


def load_rag(path: Path | None = None) -> list[RagCase]:
    rows = _load(path or default_dir() / "rag.json", "cases")
    return [RagCase.model_validate(r) for r in rows]
