"""
backend/app/services/card_credibility_service.py  — B4

Computes the credibility indicators shown on Card Detail pages.

Four indicators:
  sample_size       — count of PriceHistory rows in the display window
  source_breakdown  — % eBay vs % TCG vs % other  (Pro only)
  match_confidence  — latest ObservationMatchLog confidence (Pro only)
  data_age          — hours since most recent PriceHistory row

All queries use indexed columns only.
Called once per Card Detail page load.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.core.permissions import Feature, can, history_days
from backend.app.models.observation_match_log import ObservationMatchLog
from backend.app.models.price_history import PriceHistory


# ── Result type ───────────────────────────────────────────────────────────────

@dataclass
class CredibilityIndicators:
    # Always visible (Free + Pro)
    sample_size: int
    data_age_hours: float | None     # None = no price history at all

    # Pro-only (None when gated)
    source_breakdown: dict | None    # {"ebay_sold": 0.72, "pokemon_tcg_api": 0.28}
    match_confidence: float | None   # 0.0–1.0

    # Display helpers
    data_age_label: str              # "Updated 3h ago" | "No data"
    sample_size_label: str           # "Based on 47 sales"
    confidence_status: str           # "green" | "yellow" | "red" | "unknown"


# ── Builder ───────────────────────────────────────────────────────────────────

def build_credibility_indicators(
    db: Session,
    asset_id: uuid.UUID,
    access_tier: str,
) -> CredibilityIndicators:
    """
    Compute all credibility indicators for a card detail page.

    source_breakdown and match_confidence require Feature.CARD_SOURCE_BREAKDOWN (Pro).
    """
    now = datetime.now(UTC)
    window_days = history_days(access_tier)
    cutoff = now - timedelta(days=window_days)
    show_provenance = can(access_tier, Feature.CARD_SOURCE_BREAKDOWN)

    # ── Sample size + data age ────────────────────────────────────────────────
    row = db.execute(
        select(
            func.count(PriceHistory.id).label("cnt"),
            func.max(PriceHistory.captured_at).label("latest"),
        ).where(
            PriceHistory.asset_id == asset_id,
            PriceHistory.captured_at >= cutoff,
        )
    ).one()

    sample_size: int = row.cnt or 0
    latest_captured: datetime | None = row.latest

    if latest_captured is not None:
        if latest_captured.tzinfo is None:
            latest_captured = latest_captured.replace(tzinfo=UTC)
        data_age_hours: float | None = (now - latest_captured).total_seconds() / 3600
    else:
        data_age_hours = None

    # ── Source breakdown (Pro only) ───────────────────────────────────────────
    source_breakdown: dict | None = None
    if show_provenance and sample_size > 0:
        source_rows = db.execute(
            select(
                PriceHistory.source,
                func.count(PriceHistory.id).label("cnt"),
            ).where(
                PriceHistory.asset_id == asset_id,
                PriceHistory.captured_at >= cutoff,
            ).group_by(PriceHistory.source)
        ).all()

        total = sum(r.cnt for r in source_rows)
        if total > 0:
            source_breakdown = {r.source: round(r.cnt / total, 3) for r in source_rows}

    # ── Match confidence (Pro only) ───────────────────────────────────────────
    match_confidence: float | None = None
    if show_provenance:
        conf_value = db.execute(
            select(ObservationMatchLog.confidence)
            .where(ObservationMatchLog.matched_asset_id == asset_id)
            .order_by(ObservationMatchLog.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()

        if conf_value is not None:
            match_confidence = float(conf_value)

    return CredibilityIndicators(
        sample_size=sample_size,
        data_age_hours=data_age_hours,
        source_breakdown=source_breakdown,
        match_confidence=match_confidence,
        data_age_label=_format_age(data_age_hours),
        sample_size_label=_format_sample_size(sample_size),
        confidence_status=_confidence_status(match_confidence),
    )


# ── Formatting helpers ────────────────────────────────────────────────────────

def _format_age(hours: float | None) -> str:
    if hours is None:
        return "No data"
    if hours < 1:
        return f"Updated {int(hours * 60)}m ago"
    if hours < 48:
        return f"Updated {int(hours)}h ago"
    return f"Updated {int(hours / 24)}d ago"


def _format_sample_size(n: int) -> str:
    if n == 0:
        return "No sales data"
    if n == 1:
        return "Based on 1 sale"
    return f"Based on {n:,} sales"


def _confidence_status(confidence: float | None) -> str:
    if confidence is None:
        return "unknown"
    if confidence >= 0.85:
        return "green"
    if confidence >= 0.70:
        return "yellow"
    return "red"


# ── Template render helper ────────────────────────────────────────────────────

def render_credibility_html(ind: CredibilityIndicators) -> str:
    """Render the credibility indicators block for card detail page."""
    source_html = ""
    if ind.source_breakdown is not None:
        chips = "".join(
            f'<span class="source-chip source-chip--{_source_css(src)}">'
            f"{_source_label(src)} {int(pct * 100)}%</span>"
            for src, pct in sorted(
                ind.source_breakdown.items(), key=lambda kv: kv[1], reverse=True
            )
        )
        source_html = f'<div class="credibility-sources">{chips}</div>'

    confidence_html = ""
    if ind.match_confidence is not None:
        confidence_html = (
            f'<span class="confidence-badge confidence-badge--{ind.confidence_status}"'
            f' title="Match confidence: {ind.match_confidence:.0%}">'
            f"{ind.match_confidence:.0%} match</span>"
        )

    return f"""
<div class="credibility-block" data-zh="数据可信度">
  <span class="credibility-item credibility-item--age" title="Last data update">
    {ind.data_age_label}
  </span>
  <span class="credibility-item credibility-item--sample" title="Price history sample size">
    {ind.sample_size_label}
  </span>
  {confidence_html}
  {source_html}
</div>
"""


def _source_label(source: str) -> str:
    return {
        "ebay_sold": "eBay",
        "pokemon_tcg_api": "TCG API",
        "manual_seed": "Manual",
        "sample": "Sample",
    }.get(source, source)


def _source_css(source: str) -> str:
    return {
        "ebay_sold": "ebay",
        "pokemon_tcg_api": "tcg",
        "manual_seed": "manual",
    }.get(source, "other")
