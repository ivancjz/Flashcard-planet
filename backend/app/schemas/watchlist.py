from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class WatchlistCreateRequest(BaseModel):
    discord_user_id: str
    asset_name: str
    threshold_up_percent: float | None = None
    threshold_down_percent: float | None = None
    target_price: float | None = None
    predict_signal_change: bool | None = None
    predict_up_probability_above: float | None = None
    predict_down_probability_above: float | None = None


class WatchlistItemResponse(BaseModel):
    watchlist_id: UUID
    asset_id: UUID
    name: str
    category: str | None = None
    game: str = "pokemon"
    added_at: datetime
    threshold_up_percent: Decimal | None = None
    threshold_down_percent: Decimal | None = None
    target_price: Decimal | None = None


class MessageResponse(BaseModel):
    message: str
    created_watchlist: bool | None = None
    added_rule_labels: list[str] = Field(default_factory=list)
