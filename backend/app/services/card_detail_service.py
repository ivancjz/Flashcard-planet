from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.core.permissions import Feature, can
from backend.app.core.price_sources import SAMPLE_PRICE_SOURCE, get_active_price_source_filter
from backend.app.models.asset import Asset
from backend.app.models.asset_signal import AssetSignal
from backend.app.models.observation_match_log import ObservationMatchLog
from backend.app.models.price_history import PriceHistory

MATCH_CONFIDENCE_WINDOW_DAYS = 30
CONFIDENCE_HIGH_THRESHOLD = Decimal("0.75")
CONFIDENCE_MEDIUM_THRESHOLD = Decimal("0.50")
CONFIDENCE_MIN_SAMPLE_SIZE = 5

FREE_HISTORY_DAYS = 7
PRO_HISTORY_DAYS = 180


@dataclass
class PricePoint:
    price: Decimal
    captured_at: datetime
    source: str
    is_real: bool


@dataclass
class CardDetailViewModel:
    asset_id: uuid.UUID
    name: str
    set_name: str | None
    card_number: str | None
    variant: str | None
    image_url: str | None
    # Current price
    latest_price: Decimal | None
    previous_price: Decimal | None
    percent_change: Decimal | None
    currency: str
    data_age: datetime | None
    # History
    price_history: list[PricePoint]
    history_truncated: bool
    # Signal layer
    signal_label: str | None
    signal_confidence: int | None
    signal_explanation: str | None
    liquidity_score: int | None
    # Data quality (computed)
    sample_size: int
    match_confidence_avg: Decimal | None
    confidence_label: str
    source_breakdown: dict[str, int]


def _confidence_label(avg: Decimal | None, sample_size: int) -> str:
    """Convert match confidence avg and sample size to a user-facing label."""
    if sample_size < CONFIDENCE_MIN_SAMPLE_SIZE or avg is None:
        return "Insufficient data"
    if avg >= CONFIDENCE_HIGH_THRESHOLD:
        return "High"
    if avg >= CONFIDENCE_MEDIUM_THRESHOLD:
        return "Medium"
    return "Low"


def _get_sample_and_confidence(
    db: Session, asset_id: uuid.UUID
) -> tuple[int, Decimal | None]:
    """Return (count, avg_confidence) for matched observations in last 30d."""
    cutoff = datetime.now(UTC) - timedelta(days=MATCH_CONFIDENCE_WINDOW_DAYS)
    row = db.execute(
        select(
            func.count(ObservationMatchLog.id),
            func.avg(ObservationMatchLog.confidence),
        ).where(
            ObservationMatchLog.matched_asset_id == asset_id,
            ObservationMatchLog.created_at >= cutoff,
        )
    ).one()
    count = int(row[0] or 0)
    avg = Decimal(str(row[1])).quantize(Decimal("0.01")) if row[1] is not None else None
    return count, avg


def build_card_detail(
    db: Session,
    asset_id: uuid.UUID,
    *,
    access_tier: str,
) -> CardDetailViewModel | None:
    """Build a CardDetailViewModel for the given asset_id and access tier."""
    asset = db.get(Asset, asset_id)
    if asset is None:
        return None

    has_full_history = can(access_tier, Feature.PRICE_HISTORY_FULL)
    history_days = PRO_HISTORY_DAYS if has_full_history else FREE_HISTORY_DAYS
    history_truncated = not has_full_history

    source_filter = get_active_price_source_filter(db)
    cutoff = datetime.now(UTC) - timedelta(days=history_days)

    history_rows = db.execute(
        select(PriceHistory.price, PriceHistory.captured_at, PriceHistory.source)
        .where(
            PriceHistory.asset_id == asset_id,
            source_filter,
            PriceHistory.captured_at >= cutoff,
        )
        .order_by(PriceHistory.captured_at.desc())
    ).all()

    price_history = [
        PricePoint(
            price=Decimal(str(row.price)),
            captured_at=row.captured_at,
            source=row.source,
            is_real=(row.source != SAMPLE_PRICE_SOURCE),
        )
        for row in history_rows
    ]

    latest_price = price_history[0].price if price_history else None
    previous_price = price_history[1].price if len(price_history) > 1 else None
    percent_change: Decimal | None = None
    if latest_price is not None and previous_price is not None and previous_price != 0:
        percent_change = (
            (latest_price - previous_price) / previous_price * Decimal("100")
        ).quantize(Decimal("0.01"))

    source_breakdown: dict[str, int] = {}
    for p in price_history:
        source_breakdown[p.source] = source_breakdown.get(p.source, 0) + 1

    # AssetSignal has a unique constraint on asset_id — at most one row per asset.
    signal = db.scalars(
        select(AssetSignal).where(AssetSignal.asset_id == asset_id)
    ).first()

    sample_size, match_confidence_avg = _get_sample_and_confidence(db, asset_id)

    return CardDetailViewModel(
        asset_id=asset.id,
        name=asset.name,
        set_name=asset.set_name,
        card_number=asset.card_number,
        variant=asset.variant,
        image_url=(asset.metadata_json or {}).get("images", {}).get("small"),
        latest_price=latest_price,
        previous_price=previous_price,
        percent_change=percent_change,
        currency="USD",
        data_age=price_history[0].captured_at if price_history else None,
        price_history=price_history,
        history_truncated=history_truncated,
        signal_label=signal.label if signal else None,
        signal_confidence=signal.confidence if signal else None,
        signal_explanation=signal.explanation if signal else None,
        liquidity_score=signal.liquidity_score if signal else None,
        sample_size=sample_size,
        match_confidence_avg=match_confidence_avg,
        confidence_label=_confidence_label(match_confidence_avg, sample_size),
        source_breakdown=source_breakdown,
    )
