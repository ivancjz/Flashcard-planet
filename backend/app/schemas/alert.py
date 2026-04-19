from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class AlertCreateRequest(BaseModel):
    discord_user_id: str
    asset_name: str
    alert_type: str
    threshold_percent: Decimal | None = None
    target_price: Decimal | None = None
    direction: str | None = None


class AlertActionResponse(BaseModel):
    message: str


class AlertItemResponse(BaseModel):
    alert_id: UUID
    asset_id: UUID
    asset_name: str
    category: str | None = None
    game: str = "pokemon"
    alert_type: str
    direction: str | None = None
    threshold_percent: Decimal | None = None
    target_price: Decimal | None = None
    latest_price: Decimal | None = None
    currency: str | None = None
    is_active: bool
    is_armed: bool
    last_observed_signal: str | None = None
    current_prediction: str | None = None
    up_probability: Decimal | None = None
    down_probability: Decimal | None = None
    flat_probability: Decimal | None = None
    last_triggered_at: datetime | None = None
    created_at: datetime


class AlertHistoryItemResponse(BaseModel):
    history_id: UUID
    alert_id: UUID | None = None
    asset_id: UUID
    asset_name: str
    alert_type: str
    triggered_at: datetime
    price_at_trigger: Decimal | None = None
    reference_price: Decimal | None = None
    percent_change: Decimal | None = None
    currency: str | None = None
    delivery_status: str
    notification_content: str | None = None
