from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class LiquiditySummaryResponse(BaseModel):
    liquidity_score: int | None = None
    liquidity_label: str | None = None
    last_real_sale_at: datetime | None = None
    days_since_last_sale: int | None = None
    sales_count_7d: int | None = None
    sales_count_30d: int | None = None
    history_depth: int | None = None
    source_count: int | None = None


class AlertConfidenceResponse(BaseModel):
    alert_confidence: int | None = None
    alert_confidence_label: str | None = None


class AssetPriceResponse(LiquiditySummaryResponse, AlertConfidenceResponse):
    model_config = ConfigDict(from_attributes=True)

    asset_id: UUID
    asset_class: str
    category: str
    name: str
    set_name: str | None = None
    external_id: str | None = None
    card_number: str | None = None
    year: int | None = None
    variant: str | None = None
    grade_company: str | None = None
    grade_score: Decimal | None = None
    latest_price: Decimal
    currency: str
    source: str
    captured_at: datetime
    previous_price: Decimal | None = None
    absolute_change: Decimal | None = None
    percent_change: Decimal | None = None


class TopMoverResponse(LiquiditySummaryResponse, AlertConfidenceResponse):
    asset_id: UUID
    name: str
    category: str
    set_name: str | None = None
    external_id: str | None = None
    latest_price: Decimal
    previous_price: Decimal
    absolute_change: Decimal
    percent_change: Decimal


class TopValueResponse(BaseModel):
    asset_id: UUID
    name: str
    category: str
    set_name: str | None = None
    external_id: str | None = None
    latest_price: Decimal
    currency: str
    source: str
    captured_at: datetime


class PricePredictionResponse(BaseModel):
    asset_id: UUID
    name: str
    category: str
    set_name: str | None = None
    current_price: Decimal
    currency: str
    prediction: str
    up_probability: Decimal | None = None
    down_probability: Decimal | None = None
    flat_probability: Decimal | None = None
    reason: str
    points_used: int
    captured_at: datetime


class PriceHistoryPointResponse(BaseModel):
    timestamp: datetime
    captured_at: datetime
    price: Decimal
    currency: str
    source: str
    point_type: str | None = None
    event_type: str | None = None
    is_real_data: bool | None = None


class AssetHistoryResponse(LiquiditySummaryResponse, AlertConfidenceResponse):
    asset_id: UUID
    name: str
    category: str
    set_name: str | None = None
    current_price: Decimal
    currency: str
    points_returned: int
    history: list[PriceHistoryPointResponse]
