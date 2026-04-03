from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class AlertItemResponse(BaseModel):
    alert_id: UUID
    asset_id: UUID
    asset_name: str
    category: str
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
