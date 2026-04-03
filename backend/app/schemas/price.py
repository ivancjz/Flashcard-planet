from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AssetPriceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    asset_id: UUID
    asset_class: str
    category: str
    name: str
    set_name: str | None = None
    card_number: str | None = None
    year: int | None = None
    variant: str | None = None
    grade_company: str | None = None
    grade_score: Decimal | None = None
    latest_price: Decimal
    currency: str
    source: str
    captured_at: datetime


class TopMoverResponse(BaseModel):
    asset_id: UUID
    name: str
    category: str
    latest_price: Decimal
    previous_price: Decimal
    absolute_change: Decimal
    percent_change: Decimal


class TopValueResponse(BaseModel):
    asset_id: UUID
    name: str
    category: str
    set_name: str | None = None
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
    captured_at: datetime
    price: Decimal
    currency: str
    source: str


class AssetHistoryResponse(BaseModel):
    asset_id: UUID
    name: str
    category: str
    set_name: str | None = None
    current_price: Decimal
    currency: str
    points_returned: int
    history: list[PriceHistoryPointResponse]
