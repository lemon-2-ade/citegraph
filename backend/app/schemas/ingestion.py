from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.db.models import JobStatus
from app.ingestion.pipeline import IngestionParams


class IngestionJobCreate(BaseModel):
    source: str = "openalex"
    params: IngestionParams


class IngestionJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source: str
    status: JobStatus
    params: dict[str, Any]
    checkpoint: dict[str, Any]
    stats: dict[str, Any]
    error: str | None
    attempts: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
