from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel

from backend.app.schemas.market import MarketOverviewResponse


class DailyMarketReportResponse(BaseModel):
    id: UUID
    report_date: date
    generated_at: datetime
    status: str
    title: str
    market_sentiment: str
    confidence_label: str
    summary: str
    overview: MarketOverviewResponse
    evidence: list[str]
