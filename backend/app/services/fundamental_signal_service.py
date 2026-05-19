"""fundamental_signal_service.py — Public Calls Phase 3.

Computes the "ex-event" (fundamental) signal for a card by stripping price
history points that fall inside known market-event contamination windows, then
re-running the same delta calculation used by the main signal engine.

The gap between actual_signal and fundamental_signal is the "hype premium" —
the price move attributable to events rather than underlying fundamentals.

Public entry point:
  compute_fundamental_signal(db, asset_id) -> SignalEstimate

Algorithm:
  1. Fetch all market_events that touch this asset (by asset_id or set_name).
  2. Build contamination windows: [event_date - PRE_EVENT_BUFFER_DAYS,
     event_date + expected_window_days + POST_EVENT_BUFFER_DAYS].
  3. Fetch all price_history for this asset.
  4. Filter out rows inside contamination windows → "clean" price history.
  5. Compute baseline from clean rows ≥ BASELINE_MIN_AGE_DAYS old.
  6. Compute current from clean rows ≤ CURRENT_MAX_AGE_HOURS hours old.
  7. Return SignalEstimate with both actual and fundamental signals.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.asset import Asset
from backend.app.models.asset_signal import AssetSignal
from backend.app.models.predictions import MarketEvent
from backend.app.models.price_history import PriceHistory

# Days before an event to start excluding price data (pre-event anticipation
# buying can contaminate the baseline just as much as the event itself).
PRE_EVENT_BUFFER_DAYS = 3

# Days after an event's stated window to continue excluding price data.
POST_EVENT_BUFFER_DAYS = 2

# Minimum age (days) of a price point for it to count as "baseline".
BASELINE_MIN_AGE_DAYS = 7

# Maximum age (hours) of a price point for it to count as "current".
CURRENT_MAX_AGE_HOURS = 48

# Minimum number of price points needed in each window to compute a signal.
MIN_BASELINE_POINTS = 3
MIN_CURRENT_POINTS = 1

# Source exclusion — CardMarket and eBay data must not mix with TCG API price
# windows for delta comparison (different currency / segment semantics).
_CM_ALL_SOURCES = frozenset({
    "cardmarket_avg1", "cardmarket_avg7",
    "cardmarket_avg30", "cardmarket_trend",
})
_EXCLUDE_SOURCES = frozenset({"ebay_sold", "ebay_web_sold"}) | _CM_ALL_SOURCES


@dataclass
class SignalEstimate:
    asset_id: uuid.UUID
    # Actual signal from asset_signals table
    actual_label: str | None
    actual_delta_pct: Decimal | None
    # Fundamental signal computed ex-event
    fundamental_delta_pct: Decimal | None
    fundamental_baseline_price: Decimal | None
    fundamental_current_price: Decimal | None
    # How much of the actual move is attributable to events
    hype_premium_pct: Decimal | None
    # Diagnostics
    total_price_points: int
    clean_price_points: int
    events_excluded: int
    contamination_windows: list[tuple[datetime, datetime]]
    insufficient_data: bool
    reason: str | None


def _contamination_windows(events: list[MarketEvent]) -> list[tuple[datetime, datetime]]:
    """Build exclusion intervals from market events."""
    windows: list[tuple[datetime, datetime]] = []
    for ev in events:
        window_days = ev.expected_window_days or 14
        start = ev.event_date - timedelta(days=PRE_EVENT_BUFFER_DAYS)
        end = ev.event_date + timedelta(days=window_days + POST_EVENT_BUFFER_DAYS)
        windows.append((start, end))
    # Merge overlapping windows
    if not windows:
        return []
    windows.sort(key=lambda w: w[0])
    merged: list[tuple[datetime, datetime]] = [windows[0]]
    for start, end in windows[1:]:
        if start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _is_contaminated(ts: datetime, windows: list[tuple[datetime, datetime]]) -> bool:
    for start, end in windows:
        if start <= ts <= end:
            return True
    return False


def _matching_events(
    db: Session,
    *,
    asset_id: uuid.UUID,
    set_name: str | None,
) -> list[MarketEvent]:
    """All market_events touching this asset (by UUID or set_name)."""
    all_events = db.scalars(select(MarketEvent)).all()
    matched: list[MarketEvent] = []
    asset_id_str = str(asset_id)
    for ev in all_events:
        asset_ids = ev.affected_asset_ids or []
        set_ids = ev.affected_set_ids or []
        touches_asset = asset_id_str in [str(a) for a in asset_ids]
        touches_set = set_name is not None and set_name in set_ids
        if touches_asset or touches_set:
            matched.append(ev)
    return matched


def compute_fundamental_signal(
    db: Session,
    *,
    asset_id: uuid.UUID,
) -> SignalEstimate:
    """
    Compute the ex-event fundamental signal for a card.

    Strips price history inside market-event contamination windows, then
    recomputes baseline → current delta.  Returns both the actual and
    fundamental signals for hype-premium analysis.
    """
    now = datetime.now(UTC)
    baseline_cutoff = now - timedelta(days=BASELINE_MIN_AGE_DAYS)
    current_cutoff = now - timedelta(hours=CURRENT_MAX_AGE_HOURS)

    asset = db.get(Asset, asset_id)
    if asset is None:
        return SignalEstimate(
            asset_id=asset_id,
            actual_label=None,
            actual_delta_pct=None,
            fundamental_delta_pct=None,
            fundamental_baseline_price=None,
            fundamental_current_price=None,
            hype_premium_pct=None,
            total_price_points=0,
            clean_price_points=0,
            events_excluded=0,
            contamination_windows=[],
            insufficient_data=True,
            reason=f"Asset {asset_id} not found",
        )

    set_name = asset.set_name

    # Actual signal from asset_signals table
    actual_signal = db.scalars(
        select(AssetSignal).where(AssetSignal.asset_id == asset_id)
    ).first()
    actual_label = actual_signal.label if actual_signal else None
    actual_delta_pct = (
        Decimal(str(actual_signal.price_delta_pct))
        if actual_signal and actual_signal.price_delta_pct is not None
        else None
    )

    # Market events touching this asset
    events = _matching_events(db, asset_id=asset_id, set_name=set_name)
    windows = _contamination_windows(events)

    # All price history for this asset (excluding source-mixed rows)
    price_rows = db.scalars(
        select(PriceHistory).where(
            PriceHistory.asset_id == asset_id,
            PriceHistory.source.not_in(_EXCLUDE_SOURCES),
        ).order_by(PriceHistory.captured_at)
    ).all()

    total = len(price_rows)

    # Partition into clean / contaminated
    clean_rows = [r for r in price_rows if not _is_contaminated(r.captured_at, windows)]
    clean_total = len(clean_rows)
    excluded = total - clean_total

    # Separate into baseline (≥7d old) and current (≤48h old)
    baseline_points = [
        Decimal(str(r.price)) for r in clean_rows
        if r.captured_at <= baseline_cutoff
    ]
    current_points = [
        Decimal(str(r.price)) for r in clean_rows
        if r.captured_at >= current_cutoff
    ]

    if len(baseline_points) < MIN_BASELINE_POINTS:
        return SignalEstimate(
            asset_id=asset_id,
            actual_label=actual_label,
            actual_delta_pct=actual_delta_pct,
            fundamental_delta_pct=None,
            fundamental_baseline_price=None,
            fundamental_current_price=None,
            hype_premium_pct=None,
            total_price_points=total,
            clean_price_points=clean_total,
            events_excluded=excluded,
            contamination_windows=windows,
            insufficient_data=True,
            reason=(
                f"Insufficient clean baseline points: "
                f"{len(baseline_points)} < {MIN_BASELINE_POINTS} required"
            ),
        )

    if len(current_points) < MIN_CURRENT_POINTS:
        return SignalEstimate(
            asset_id=asset_id,
            actual_label=actual_label,
            actual_delta_pct=actual_delta_pct,
            fundamental_delta_pct=None,
            fundamental_baseline_price=None,
            fundamental_current_price=None,
            hype_premium_pct=None,
            total_price_points=total,
            clean_price_points=clean_total,
            events_excluded=excluded,
            contamination_windows=windows,
            insufficient_data=True,
            reason=(
                f"Insufficient clean current points: "
                f"{len(current_points)} < {MIN_CURRENT_POINTS} required"
            ),
        )

    baseline_price = Decimal(str(median(float(p) for p in baseline_points)))
    current_price = Decimal(str(median(float(p) for p in current_points)))

    if baseline_price == 0:
        return SignalEstimate(
            asset_id=asset_id,
            actual_label=actual_label,
            actual_delta_pct=actual_delta_pct,
            fundamental_delta_pct=None,
            fundamental_baseline_price=baseline_price,
            fundamental_current_price=current_price,
            hype_premium_pct=None,
            total_price_points=total,
            clean_price_points=clean_total,
            events_excluded=excluded,
            contamination_windows=windows,
            insufficient_data=True,
            reason="Baseline price is zero — cannot compute delta",
        )

    fundamental_delta = (
        (current_price - baseline_price) / baseline_price * Decimal("100")
    ).quantize(Decimal("0.01"))

    # Hype premium = actual move - fundamental move (positive = event-driven excess)
    hype_premium: Decimal | None = None
    if actual_delta_pct is not None:
        hype_premium = (actual_delta_pct - fundamental_delta).quantize(Decimal("0.01"))

    return SignalEstimate(
        asset_id=asset_id,
        actual_label=actual_label,
        actual_delta_pct=actual_delta_pct,
        fundamental_delta_pct=fundamental_delta,
        fundamental_baseline_price=baseline_price.quantize(Decimal("0.01")),
        fundamental_current_price=current_price.quantize(Decimal("0.01")),
        hype_premium_pct=hype_premium,
        total_price_points=total,
        clean_price_points=clean_total,
        events_excluded=excluded,
        contamination_windows=windows,
        insufficient_data=False,
        reason=None,
    )
