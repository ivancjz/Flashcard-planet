"""driver_attribution_service.py — Public Calls Phase 3.

Rule engine v1: attributes a price signal to its primary driver.

Priority order:
  1. EVENT_DRIVEN  — INFLUENCER or TOURNAMENT event within the signal window
  2. MACRO         — >60% of same-set cards show same signal direction
  3. SUPPLY_SHOCK  — SUPPLY-type event within signal window + 14d extension
  4. EVENT_DRIVEN  — RELEASE event that names this specific card in affected_asset_ids
                     (set-wide RELEASE without card-level specificity doesn't trigger this;
                      card-level release hype is distinct from set-wide MACRO movement)
  5. UNKNOWN       — no attribution found

Driver taxonomy:
  MACRO               overall market / set-level trend
  META_SHIFT          competitive meta change (YGO/MTG-centric)
  SUPPLY_SHOCK        reprint, pop-report, supply disruption
  EVENT_DRIVEN        influencer / tournament / content within event window
  INFLUENCER_PROVENANCE  celebrity-owned card premium
  UNKNOWN             abnormal move, cause unclear

Public entry point: attribute_signal(db, asset_id, signal_move_pct, signal_window_days)
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from backend.app.models.asset import Asset
from backend.app.models.asset_signal import AssetSignal
from backend.app.models.predictions import MarketEvent

# Event type → driver mapping
_EVENT_TYPE_TO_DRIVER: dict[str, str] = {
    "INFLUENCER": "EVENT_DRIVEN",
    "TOURNAMENT": "EVENT_DRIVEN",
    "RELEASE": "MACRO",
    "SUPPLY": "SUPPLY_SHOCK",
}

# Per-driver confidence multiplier (based on how reliably each event type
# signals a card-level move vs set-level noise).
_EVENT_TYPE_CONFIDENCE_WEIGHT: dict[str, float] = {
    "INFLUENCER": 0.90,
    "TOURNAMENT": 0.70,
    "SUPPLY": 0.85,
    # RELEASE=0.75: predictable, scheduled, well-documented (Pokemon.com source of truth),
    # high market impact. Higher than SUPPLY (0.68 effective) because releases are
    # announced months in advance and the investor community tracks them closely.
    # Decision 2026-05-19: bumped from 0.55 → 0.75.
    "RELEASE": 0.75,
}

# Fraction of same-set assets with the same signal direction that triggers MACRO.
MACRO_SET_BREADTH_THRESHOLD = 0.60

# Additional look-back window (days) for SUPPLY events beyond the primary
# signal_window_days. Supply events often precede the visible price move.
SUPPLY_LOOKBACK_EXTENSION_DAYS = 14

# Confidence assigned to UNKNOWN attribution.
UNKNOWN_CONFIDENCE = 0.10


@dataclass
class DriverAttribution:
    driver: str
    confidence: float
    reason: str
    event_id: uuid.UUID | None = None
    event_description: str | None = None
    event_type: str | None = None


def _recency_score(
    event_date: datetime,
    now: datetime,
    expected_window_days: int | None,
) -> float:
    """0.0–1.0: 1.0 = event just happened; decays linearly to 0 at window end."""
    window = expected_window_days or 14
    days_elapsed = max((now - event_date).total_seconds() / 86400, 0)
    return max(0.0, 1.0 - days_elapsed / window)


def _best_event(
    events: list,
    now: datetime,
    *,
    extra_multiplier: float = 1.0,
):
    """Pick the event that produces the highest confidence score.

    confidence = recency × event_type_weight × extra_multiplier

    Confidence already incorporates recency via the decay function, so using
    confidence as the tiebreaker avoids double-counting recency (the original
    'most recent wins' approach did this). When two events produce identical
    confidence, fall back to most recent (event_date DESC) for determinism.
    """
    def _key(ev):
        recency = _recency_score(ev.event_date, now, ev.expected_window_days)
        weight = _EVENT_TYPE_CONFIDENCE_WEIGHT.get(ev.event_type, 0.6)
        confidence = recency * weight * extra_multiplier
        return (confidence, ev.event_date)

    return max(events, key=_key)


def _matching_events(
    db: Session,
    *,
    asset_id: uuid.UUID,
    set_name: str | None,
    window_start: datetime,
    window_end: datetime,
    now: datetime,
    event_types: list[str] | None = None,
) -> list[MarketEvent]:
    """Return market_events that overlap the given time window and touch this asset."""
    q = select(MarketEvent).where(
        # Event started before the window ended
        MarketEvent.event_date <= window_end,
        # Event's activity window started before now
        # (event is not entirely in the future)
        MarketEvent.event_date <= now,
    )
    if event_types:
        q = q.where(MarketEvent.event_type.in_(event_types))

    events = db.scalars(q).all()

    matched: list[MarketEvent] = []
    for ev in events:
        # Check temporal overlap: event active window [event_date, event_date + window]
        # must overlap with [window_start, window_end]
        effective_window = ev.expected_window_days or 14
        ev_end = ev.event_date + timedelta(days=effective_window)
        if ev_end < window_start:
            continue  # event fully expired before our window

        # Check asset-level match: by UUID or by set_name
        asset_ids = ev.affected_asset_ids or []
        set_ids = ev.affected_set_ids or []

        asset_id_str = str(asset_id)
        touches_asset = asset_id_str in [str(a) for a in asset_ids]
        touches_set = set_name is not None and set_name in set_ids

        # RELEASE events with no specific asset/set listed apply broadly
        touches_broad = (ev.event_type == "RELEASE" and not asset_ids and not set_ids)

        if touches_asset or touches_set or touches_broad:
            matched.append(ev)

    return matched


def _check_macro_breadth(
    db: Session,
    *,
    asset_id: uuid.UUID,
    set_name: str | None,
    signal_move_pct: Decimal,
) -> float | None:
    """
    Return fraction of same-set assets showing same direction signal.
    Returns None if set_name is unknown or set has <5 assets with signals.
    """
    if not set_name:
        return None

    # Assets in the same set that have asset_signals
    set_asset_ids = db.scalars(
        select(Asset.id).where(
            Asset.set_name == set_name,
            Asset.id != asset_id,
        )
    ).all()

    if not set_asset_ids:
        return None

    signals = db.scalars(
        select(AssetSignal).where(AssetSignal.asset_id.in_(set_asset_ids))
    ).all()

    if len(signals) < 5:
        return None

    is_positive = signal_move_pct >= 0
    same_direction = sum(
        1 for s in signals
        if s.price_delta_pct is not None
        and (s.price_delta_pct >= 0) == is_positive
    )
    return same_direction / len(signals)


def attribute_signal(
    db: Session,
    *,
    asset_id: uuid.UUID,
    signal_move_pct: Decimal,
    signal_window_days: int,
    reference_time: datetime | None = None,
) -> DriverAttribution:
    """
    Attribute a price signal to its primary driver.

    Args:
        db:                 DB session.
        asset_id:           UUID of the asset whose signal we are attributing.
        signal_move_pct:    Signed price change percentage (+ = up, - = down).
        signal_window_days: Number of look-back days the signal was computed over.
        reference_time:     Override "now" for historical validation. Production
                            callers omit this (defaults to datetime.now(UTC)).

    Returns:
        DriverAttribution with driver, confidence, reason, and event reference.
    """
    now = reference_time or datetime.now(UTC)
    window_start = now - timedelta(days=signal_window_days)
    window_end = now

    asset = db.get(Asset, asset_id)
    if asset is None:
        return DriverAttribution(
            driver="UNKNOWN",
            confidence=UNKNOWN_CONFIDENCE,
            reason=f"Asset {asset_id} not found in database",
        )

    set_name = asset.set_name

    # ── Rule 1: EVENT_DRIVEN (INFLUENCER or TOURNAMENT) ─────────────────────
    event_driven_types = ["INFLUENCER", "TOURNAMENT"]
    ed_events = _matching_events(
        db,
        asset_id=asset_id,
        set_name=set_name,
        window_start=window_start,
        window_end=window_end,
        now=now,
        event_types=event_driven_types,
    )

    if ed_events:
        best = _best_event(ed_events, now)
        recency = _recency_score(best.event_date, now, best.expected_window_days)
        weight = _EVENT_TYPE_CONFIDENCE_WEIGHT.get(best.event_type, 0.6)
        confidence = round(recency * weight, 3)
        return DriverAttribution(
            driver="EVENT_DRIVEN",
            confidence=confidence,
            reason=(
                f"{best.event_type} event '{best.description[:80]}' "
                f"active {best.event_date.date()} "
                f"(recency={recency:.2f}, weight={weight})"
            ),
            event_id=best.id,
            event_description=best.description,
            event_type=best.event_type,
        )

    # ── Rule 2: MACRO (set-wide breadth) ────────────────────────────────────
    breadth = _check_macro_breadth(
        db,
        asset_id=asset_id,
        set_name=set_name,
        signal_move_pct=signal_move_pct,
    )
    if breadth is not None and breadth > MACRO_SET_BREADTH_THRESHOLD:
        # Also check if a RELEASE event for this set is active
        release_events = _matching_events(
            db,
            asset_id=asset_id,
            set_name=set_name,
            window_start=window_start,
            window_end=window_end,
            now=now,
            event_types=["RELEASE"],
        )
        confidence = round(min(0.85, 0.50 + breadth * 0.50), 3)
        event_note = ""
        best_release = None
        if release_events:
            best_release = _best_event(release_events, now)
            event_note = f" (corroborated by RELEASE event: {best_release.description[:60]})"
        return DriverAttribution(
            driver="MACRO",
            confidence=confidence,
            reason=(
                f"{breadth:.0%} of {set_name!r} set cards show same signal direction"
                f"{event_note}"
            ),
            event_id=best_release.id if best_release else None,
            event_description=best_release.description if best_release else None,
            event_type="RELEASE" if best_release else None,
        )

    # ── Rule 3: SUPPLY_SHOCK ─────────────────────────────────────────────────
    supply_window_start = window_start - timedelta(days=SUPPLY_LOOKBACK_EXTENSION_DAYS)
    supply_events = _matching_events(
        db,
        asset_id=asset_id,
        set_name=set_name,
        window_start=supply_window_start,
        window_end=window_end,
        now=now,
        event_types=["SUPPLY"],
    )

    if supply_events:
        best = _best_event(supply_events, now, extra_multiplier=0.8)
        recency = _recency_score(best.event_date, now, best.expected_window_days)
        weight = _EVENT_TYPE_CONFIDENCE_WEIGHT["SUPPLY"]
        confidence = round(recency * weight * 0.8, 3)
        return DriverAttribution(
            driver="SUPPLY_SHOCK",
            confidence=confidence,
            reason=(
                f"SUPPLY event '{best.description[:80]}' "
                f"on {best.event_date.date()} "
                f"(recency={recency:.2f})"
            ),
            event_id=best.id,
            event_description=best.description,
            event_type=best.event_type,
        )

    # ── Rule 4: EVENT_DRIVEN via card-specific RELEASE ───────────────────────
    # A RELEASE event that names this specific asset in affected_asset_ids signals
    # the card is a featured chase card (e.g. Mega Greninja ex on Chaos Rising launch).
    # Set-wide RELEASE events (affected_set_ids only) do NOT trigger this path —
    # those already had a chance to corroborate MACRO above.
    release_events = _matching_events(
        db,
        asset_id=asset_id,
        set_name=set_name,
        window_start=window_start,
        window_end=window_end,
        now=now,
        event_types=["RELEASE"],
    )
    asset_id_str = str(asset_id)
    card_specific_releases = [
        ev for ev in release_events
        if asset_id_str in [str(a) for a in (ev.affected_asset_ids or [])]
    ]
    if card_specific_releases:
        best = _best_event(card_specific_releases, now)
        recency = _recency_score(best.event_date, now, best.expected_window_days)
        weight = _EVENT_TYPE_CONFIDENCE_WEIGHT["RELEASE"]
        confidence = round(recency * weight, 3)
        return DriverAttribution(
            driver="EVENT_DRIVEN",
            confidence=confidence,
            reason=(
                f"RELEASE event '{best.description[:80]}' "
                f"explicitly targets this card "
                f"(recency={recency:.2f}, weight={weight})"
            ),
            event_id=best.id,
            event_description=best.description,
            event_type=best.event_type,
        )

    # ── Rule 5: UNKNOWN default ───────────────────────────────────────────────
    return DriverAttribution(
        driver="UNKNOWN",
        confidence=UNKNOWN_CONFIDENCE,
        reason=(
            f"No matching market event (INFLUENCER/TOURNAMENT/card-specific RELEASE) "
            f"or set-breadth or SUPPLY pattern found "
            f"within {signal_window_days}d window "
            f"(move={signal_move_pct:+.1f}%, set={set_name!r})"
        ),
    )
