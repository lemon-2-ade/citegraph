from __future__ import annotations

from typing import Literal

from app.schemas.analytics import YearCount
from app.schemas.common import ResponseModel

TrendLabel = Literal["emerging", "rising", "steady", "declining"]


class TopicTrend(ResponseModel):
    topic_id: str
    name: str
    total: int
    series: list[YearCount]
    recent: int  # papers in the recent window
    previous: int  # papers in the window before it
    share_recent: float  # fraction of all papers in the recent window that have this topic
    share_previous: float
    # Ratio of smoothed shares, recent / previous. 1.0 = unchanged.
    growth: float
    label: TrendLabel


class TrendsResponse(ResponseModel):
    first_year: int | None = None
    last_year: int | None = None
    window: int
    recent_years: list[int]
    previous_years: list[int]
    topics: list[TopicTrend]
    note: str
