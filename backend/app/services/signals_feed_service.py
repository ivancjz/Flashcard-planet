"""
Tier-aware signals feed service.

Free tier:  top FREE_SIGNALS_LIMIT (5) by confidence desc, computed_at desc.
            confidence score and explanation hidden.
Pro tier:   full feed, all fields visible.

Call `build_signals_feed(db, access_tier)` from the route layer.
`SignalsFeedResult.truncated` and `hidden_count` let the template render
an accurate upgrade nudge ("X more signals available with Pro").
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.core.permissions import Feature, can, signals_limit
from backend.app.models.asset import Asset
from backend.app.models.asset_signal import AssetSignal


@dataclass
class SignalFeedRow:
    asset_id: uuid.UUID
    external_id: str | None      # for /cards/{external_id} link
    card_name: str
    set_name: str | None
    label: str                   # BREAKOUT / MOVE / WATCH / IDLE
    computed_at: datetime
    # Pro-only fields — None when gated
    confidence: int | None
    explanation: str | None
    liquidity_score: int | None


@dataclass
class SignalsFeedResult:
    rows: list[SignalFeedRow]
    truncated: bool              # True → Free tier cap applied
    hidden_count: int            # signals beyond the cap
    show_confidence: bool        # False → hide score column entirely
    show_explanation: bool       # False → hide explanation column


def build_signals_feed(
    db: Session,
    access_tier: str,
    label_filter: str | None = None,
) -> SignalsFeedResult:
    """
    Fetch and tier-gate the signals feed.

    Sorting: confidence DESC, computed_at DESC — so Free users always see
    the highest-confidence signals, not arbitrary ones.

    label_filter: optional BREAKOUT/MOVE/WATCH/IDLE to narrow results.
    """
    show_confidence = can(access_tier, Feature.SIGNALS_CONFIDENCE)
    show_explanation = can(access_tier, Feature.SIGNAL_EXPLANATION)
    cap = signals_limit(access_tier)   # None = unlimited, int = top-N

    # Join AssetSignal → Asset to get card identity fields
    base_q = (
        select(AssetSignal, Asset)
        .join(Asset, Asset.id == AssetSignal.asset_id)
        .order_by(AssetSignal.confidence.desc().nulls_last(), AssetSignal.computed_at.desc())
    )
    if label_filter:
        base_q = base_q.where(AssetSignal.label == label_filter)

    all_rows = db.execute(base_q).all()
    total_eligible = len(all_rows)

    if cap is not None:
        visible_rows = all_rows[:cap]
    else:
        visible_rows = all_rows

    hidden_count = max(0, total_eligible - len(visible_rows))

    rows = [
        SignalFeedRow(
            asset_id=sig.asset_id,
            external_id=asset.external_id,
            card_name=asset.name,
            set_name=asset.set_name,
            label=sig.label,
            computed_at=sig.computed_at,
            confidence=sig.confidence if show_confidence else None,
            explanation=sig.explanation if show_explanation else None,
            liquidity_score=sig.liquidity_score if show_confidence else None,
        )
        for sig, asset in visible_rows
    ]

    return SignalsFeedResult(
        rows=rows,
        truncated=(cap is not None and hidden_count > 0),
        hidden_count=hidden_count,
        show_confidence=show_confidence,
        show_explanation=show_explanation,
    )
