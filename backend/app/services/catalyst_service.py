from __future__ import annotations

from collections.abc import Collection
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models.predictions import MarketEvent
from backend.app.schemas.catalyst import (
    CatalystLifecycle,
    CatalystListResponse,
    CatalystResponse,
    ConfidenceLabel,
    ImpactLabel,
)


DEFAULT_CATALYST_WINDOW_DAYS = 14
MAX_CURATED_CATALYST_ROWS = 1000


class _LifecycleEvent(Protocol):
    event_date: datetime
    expected_window_days: int | None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _active_until(event: _LifecycleEvent) -> datetime:
    event_date = _as_utc(event.event_date)
    window_days = event.expected_window_days or DEFAULT_CATALYST_WINDOW_DAYS
    return event_date + timedelta(days=window_days)


def catalyst_lifecycle(
    event: _LifecycleEvent,
    *,
    as_of: datetime,
) -> CatalystLifecycle:
    event_date = _as_utc(event.event_date)
    normalized_as_of = _as_utc(as_of)
    if event_date > normalized_as_of:
        return "upcoming"
    if normalized_as_of <= _active_until(event):
        return "active"
    return "expired"


def _impact_label(score: int | None) -> ImpactLabel:
    if score is None:
        return "unscored"
    if score >= 80:
        return "high"
    if score >= 50:
        return "medium"
    return "low"


def _confidence_label(score: Decimal | None) -> ConfidenceLabel:
    if score is None:
        return "insufficient_data"
    if score >= 80:
        return "high"
    if score >= 50:
        return "medium"
    return "low"


def market_event_to_catalyst_response(
    event: MarketEvent,
    *,
    as_of: datetime,
) -> CatalystResponse:
    normalized_as_of = _as_utc(as_of)
    return CatalystResponse(
        id=event.id,
        event_date=_as_utc(event.event_date),
        active_until=_active_until(event),
        event_type=event.event_type,
        description=event.description,
        source_url=event.source_url,
        affected_games=list(event.affected_games or []),
        affected_asset_ids=list(event.affected_asset_ids or []),
        affected_set_ids=list(event.affected_set_ids or []),
        expected_window_days=event.expected_window_days,
        impact_score=event.impact_score,
        impact_label=_impact_label(event.impact_score),
        confidence_score=event.confidence_score,
        confidence_label=_confidence_label(event.confidence_score),
        status=catalyst_lifecycle(event, as_of=normalized_as_of),
        verified_at=_as_utc(event.verified_at),
    )


def _verified_event_filters():
    return (
        MarketEvent.verified_at.is_not(None),
        MarketEvent.source_url.is_not(None),
        func.trim(MarketEvent.source_url) != "",
    )


def _verified_curated_events(db: Session) -> list[MarketEvent]:
    query = (
        select(MarketEvent)
        .where(*_verified_event_filters())
        .order_by(MarketEvent.id)
        .limit(MAX_CURATED_CATALYST_ROWS)
    )
    return list(db.scalars(query).all())


def _sort_key(catalyst: CatalystResponse):
    impact_score = catalyst.impact_score or 0
    impact_key = (catalyst.impact_score is None, -impact_score)
    event_timestamp = catalyst.event_date.timestamp()
    catalyst_id = str(catalyst.id)

    if catalyst.status == "active":
        return (0, *impact_key, -event_timestamp, catalyst_id)
    if catalyst.status == "upcoming":
        return (1, event_timestamp, *impact_key, catalyst_id)
    return (2, -event_timestamp, *impact_key, catalyst_id)


def list_catalysts(
    db: Session,
    *,
    statuses: Collection[CatalystLifecycle] | None = None,
    game: str | None = None,
    event_type: str | None = None,
    limit: int = 20,
    offset: int = 0,
    as_of: datetime | None = None,
) -> CatalystListResponse:
    normalized_as_of = _as_utc(as_of or datetime.now(UTC))
    selected_statuses = set(statuses) if statuses is not None else None
    selected_game = game.strip().lower() if game is not None else None
    selected_event_type = event_type.strip().upper() if event_type is not None else None

    catalysts = []
    for event in _verified_curated_events(db):
        catalyst = market_event_to_catalyst_response(event, as_of=normalized_as_of)
        if selected_statuses is not None and catalyst.status not in selected_statuses:
            continue
        if selected_game is not None:
            affected_games = {
                affected_game.strip().lower()
                for affected_game in catalyst.affected_games
            }
            if selected_game not in affected_games and "global" not in affected_games:
                continue
        if (
            selected_event_type is not None
            and catalyst.event_type != selected_event_type
        ):
            continue
        catalysts.append(catalyst)

    catalysts.sort(key=_sort_key)
    total = len(catalysts)
    return CatalystListResponse(
        catalysts=catalysts[offset : offset + limit],
        total=total,
        limit=limit,
        offset=offset,
        as_of=normalized_as_of,
    )


def get_catalyst(
    db: Session,
    catalyst_id: UUID,
    *,
    as_of: datetime | None = None,
) -> CatalystResponse | None:
    query = (
        select(MarketEvent)
        .where(
            MarketEvent.id == catalyst_id,
            *_verified_event_filters(),
        )
        .limit(1)
    )
    event = db.scalar(query)
    if event is None:
        return None
    normalized_as_of = _as_utc(as_of or datetime.now(UTC))
    return market_event_to_catalyst_response(event, as_of=normalized_as_of)
