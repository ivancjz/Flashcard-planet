from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from backend.app.schemas.catalyst import CatalystResponse
from backend.app.schemas.daily_report_intelligence import (
    DailyReportIntelligenceResponse,
)
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
    catalysts: list[CatalystResponse]
    intelligence: DailyReportIntelligenceResponse = Field(
        default_factory=DailyReportIntelligenceResponse
    )


class DailyMarketReportListResponse(BaseModel):
    reports: list[DailyMarketReportResponse]
    total: int
    limit: int
    offset: int
