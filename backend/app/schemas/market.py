from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class MarketIndexResponse(BaseModel):
    game: str
    label: str
    change_pct: Decimal
    direction: str
    observed_assets: int
    current_assets: int
    confidence_label: str


class MarketTopMoverResponse(BaseModel):
    asset_id: UUID
    name: str
    game: str
    set_name: str | None = None
    latest_price: Decimal
    previous_price: Decimal
    percent_change: Decimal
    absolute_change: Decimal
    direction: str


class MarketSignalSummaryResponse(BaseModel):
    label: str
    count: int
    average_confidence: Decimal | None = None


class MarketOverviewResponse(BaseModel):
    generated_at: datetime
    market_sentiment: str
    confidence_label: str
    indexes: list[MarketIndexResponse]
    top_movers: list[MarketTopMoverResponse]
    signal_summary: list[MarketSignalSummaryResponse]
    commentary: str
    evidence: list[str]
