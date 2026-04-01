from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class WatchlistCreateRequest(BaseModel):
    discord_user_id: str
    asset_name: str
    threshold_up_percent: float | None = None
    threshold_down_percent: float | None = None
    target_price: float | None = None


class WatchlistItemResponse(BaseModel):
    watchlist_id: UUID
    asset_id: UUID
    name: str
    category: str
    added_at: datetime
    threshold_up_percent: Decimal | None = None
    threshold_down_percent: Decimal | None = None
    target_price: Decimal | None = None


class MessageResponse(BaseModel):
    message: str
