from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.app.core.permissions import get_pro_gate_config
from backend.app.core.response_types import CardDetailResponse, SignalsResponse
from backend.app.services.card_detail_service import build_card_detail
from backend.app.services.signals_feed_service import build_signals_feed


def _format_data_age(dt: datetime | None) -> str:
    if dt is None:
        return "Unknown"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - dt
    hours = int(delta.total_seconds() // 3600)
    if hours < 1:
        return "Updated less than 1 hour ago"
    if hours == 1:
        return "Updated 1 hour ago"
    if hours < 24:
        return f"Updated {hours} hours ago"
    days = hours // 24
    return f"Updated {days} day{'s' if days != 1 else ''} ago"


class DataService:
    @staticmethod
    def get_card_detail(
        db: Session,
        asset_id: uuid.UUID,
        *,
        access_tier: str,
        external_id: str = "",
    ) -> CardDetailResponse | None:
        vm = build_card_detail(db, asset_id, access_tier=access_tier)
        if vm is None:
            return None

        gate = (
            get_pro_gate_config("price_history", access_tier)
            if (access_tier or "").lower() != "pro"
            else None
        )

        return CardDetailResponse(
            card_name=vm.name,
            external_id=external_id,
            current_price=vm.latest_price,
            price_history=vm.price_history,
            sample_size=vm.sample_size,
            match_confidence_avg=vm.match_confidence_avg,
            data_age=_format_data_age(vm.data_age),
            source_breakdown=vm.source_breakdown,
            access_tier=access_tier,
            pro_gate_config=gate,
        )

    @staticmethod
    def get_signals(
        db: Session,
        *,
        access_tier: str,
        label_filter: str | None = None,
    ) -> SignalsResponse:
        result = build_signals_feed(db, access_tier, label_filter=label_filter)

        gate = (
            get_pro_gate_config("signals_full", access_tier)
            if (access_tier or "").lower() != "pro"
            else None
        )

        return SignalsResponse(
            signals=result.rows,
            total_eligible=len(result.rows) + result.hidden_count,
            access_tier=access_tier,
            pro_gate_config=gate,
        )
