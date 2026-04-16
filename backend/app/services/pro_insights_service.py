"""
Curated, read-only analytics surface for Pro users.

Intentionally distinct from /admin/diagnostics:
  /admin/diagnostics  → raw system health, scheduler state, error logs
                        admin-only, operational focus
  /insights           → curated data quality signals for the user
                        Pro-only, user-facing focus
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models.asset import Asset
from backend.app.models.asset_signal import AssetSignal
from backend.app.models.observation_match_log import ObservationMatchLog
from backend.app.models.price_history import PriceHistory


# ── Thresholds ───────────────────────────────────────────────────────────────

_OBSERVATION_DAILY_GREEN = 200
_OBSERVATION_DAILY_YELLOW = 50

_MATCH_RATE_GREEN = 80.0
_MATCH_RATE_YELLOW = 60.0

_MISSING_IMAGE_GREEN = 15.0   # pct — lower is better
_MISSING_IMAGE_YELLOW = 30.0

_MISSING_PRICE_GREEN = 20.0   # pct — lower is better
_MISSING_PRICE_YELLOW = 40.0


def _status_higher_is_better(value: float, green: float, yellow: float) -> str:
    return "green" if value >= green else ("yellow" if value >= yellow else "red")


def _status_lower_is_better(value: float, green: float, yellow: float) -> str:
    return "green" if value <= green else ("yellow" if value <= yellow else "red")


# ── Result types ─────────────────────────────────────────────────────────────

@dataclass
class InsightMetric:
    label: str
    value: str          # pre-formatted for display
    status: str         # "green" | "yellow" | "red"
    description: str


@dataclass
class ProInsightsResult:
    generated_at: datetime
    metrics: list[InsightMetric]
    daily_observations: list[int]   # last 7 days, oldest first
    daily_signals: list[int]        # last 7 days, oldest first


# ── Builder ──────────────────────────────────────────────────────────────────

def build_pro_insights(db: Session) -> ProInsightsResult:
    now = datetime.now(UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)
    window_7d = now - timedelta(days=7)

    # Yesterday's observation count
    obs_yesterday: int = db.scalar(
        select(func.count(ObservationMatchLog.id)).where(
            ObservationMatchLog.created_at >= yesterday_start
        )
    ) or 0

    # 7-day match rate
    obs_total_7d: int = db.scalar(
        select(func.count(ObservationMatchLog.id)).where(
            ObservationMatchLog.created_at >= window_7d
        )
    ) or 0
    obs_matched_7d: int = db.scalar(
        select(func.count(ObservationMatchLog.id)).where(
            ObservationMatchLog.created_at >= window_7d,
            ObservationMatchLog.matched_asset_id.isnot(None),
        )
    ) or 0
    match_rate = (obs_matched_7d / obs_total_7d * 100) if obs_total_7d > 0 else 0.0

    # Missing image (no "images.small" in metadata_json)
    total_assets: int = db.scalar(select(func.count(Asset.id))) or 1  # avoid /0
    # Assets without any price history in last 30 days = "missing reference price"
    assets_with_price: int = db.scalar(
        select(func.count(func.distinct(PriceHistory.asset_id))).where(
            PriceHistory.captured_at >= now - timedelta(days=30)
        )
    ) or 0
    missing_price = total_assets - assets_with_price
    missing_price_pct = missing_price / total_assets * 100

    # Signals count (7d) — AssetSignal.computed_at
    signals_7d: int = db.scalar(
        select(func.count(AssetSignal.id)).where(AssetSignal.computed_at >= window_7d)
    ) or 0

    # ── Trend arrays (7 days, oldest first) ──────────────────────────────────

    daily_observations: list[int] = []
    daily_signals: list[int] = []

    for day_offset in range(6, -1, -1):
        day_start = today_start - timedelta(days=day_offset)
        day_end = day_start + timedelta(days=1)

        obs_count = db.scalar(
            select(func.count(ObservationMatchLog.id)).where(
                ObservationMatchLog.created_at >= day_start,
                ObservationMatchLog.created_at < day_end,
            )
        ) or 0
        sig_count = db.scalar(
            select(func.count(AssetSignal.id)).where(
                AssetSignal.computed_at >= day_start,
                AssetSignal.computed_at < day_end,
            )
        ) or 0
        daily_observations.append(obs_count)
        daily_signals.append(sig_count)

    # ── Metrics ───────────────────────────────────────────────────────────────

    metrics: list[InsightMetric] = [
        InsightMetric(
            label="Yesterday's Observations",
            value=f"{obs_yesterday:,}",
            status=_status_higher_is_better(
                obs_yesterday, _OBSERVATION_DAILY_GREEN, _OBSERVATION_DAILY_YELLOW
            ),
            description="Raw listings captured in the last 24 hours.",
        ),
        InsightMetric(
            label="Match Rate (7d)",
            value=f"{match_rate:.1f}%",
            status=_status_higher_is_better(
                match_rate, _MATCH_RATE_GREEN, _MATCH_RATE_YELLOW
            ),
            description="Share of observations matched to a card in the last 7 days.",
        ),
        InsightMetric(
            label="Missing Reference Price",
            value=f"{missing_price_pct:.1f}%",
            status=_status_lower_is_better(
                missing_price_pct, _MISSING_PRICE_GREEN, _MISSING_PRICE_YELLOW
            ),
            description="Cards with no price data in the last 30 days.",
        ),
        InsightMetric(
            label="Signals (7d)",
            value=f"{signals_7d:,}",
            status="green" if signals_7d > 0 else "yellow",
            description="Total signal events generated in the last 7 days.",
        ),
    ]

    return ProInsightsResult(
        generated_at=now,
        metrics=metrics,
        daily_observations=daily_observations,
        daily_signals=daily_signals,
    )
