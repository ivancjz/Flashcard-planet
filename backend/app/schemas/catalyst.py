from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from backend.app.models.enums import CatalystEventType


CatalystLifecycle = Literal["upcoming", "active", "expired"]
ImpactLabel = Literal["high", "medium", "low", "unscored"]
ConfidenceLabel = Literal["high", "medium", "low", "insufficient_data"]


class CatalystResponse(BaseModel):
    id: UUID
    event_date: datetime
    active_until: datetime
    event_type: CatalystEventType
    description: str
    source_url: str
    affected_games: list[str]
    affected_asset_ids: list[str]
    affected_set_ids: list[str]
    expected_window_days: int | None
    impact_score: int | None
    impact_label: ImpactLabel
    confidence_score: Decimal | None
    confidence_label: ConfidenceLabel
    status: CatalystLifecycle
    verified_at: datetime


class CatalystListResponse(BaseModel):
    catalysts: list[CatalystResponse]
    total: int
    limit: int
    offset: int
    as_of: datetime
