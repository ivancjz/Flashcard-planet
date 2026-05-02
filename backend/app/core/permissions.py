from __future__ import annotations

import os
from enum import Enum

from backend.app.core.response_types import ProGateConfig


def _parse_dev_pro_emails(raw: str) -> frozenset[str]:
    return frozenset(e.strip().lower() for e in raw.split(",") if e.strip())


_DEV_PRO_EMAILS: frozenset[str] = _parse_dev_pro_emails(os.getenv("DEV_PRO_EMAILS", ""))


class Feature(str, Enum):
    # ── Price history ────────────────────────────────────────────────────
    # Free  : 7-day window
    # Pro   : 180-day window
    PRICE_HISTORY_FULL = "price_history_full"

    # ── Card Detail extras ───────────────────────────────────────────────
    # Source breakdown (eBay % vs TCG %) and match-confidence badge
    CARD_SOURCE_BREAKDOWN = "card_source_breakdown"
    # Full AI signal explanation text
    SIGNAL_EXPLANATION = "signal_explanation"

    # ── Signals feed ────────────────────────────────────────────────────
    # Free  : top-5 by (confidence desc, computed_at desc), no scores shown
    # Pro   : full feed, confidence scores visible
    SIGNALS_FULL_FEED = "signals_full_feed"
    # Confidence score visible in the signals list / detail
    SIGNALS_CONFIDENCE = "signals_confidence"
    # AI explanation visible
    SIGNALS_AI_EXPLANATION = "signals_ai_explanation"

    # ── Alerts ──────────────────────────────────────────────────────────
    # Free  : up to FREE_ALERT_LIMIT alerts, absolute-price trigger only
    # Pro   : unlimited alerts, percentage triggers unlocked
    ALERTS_EXTENDED = "alerts_extended"
    ALERTS_PCT_TRIGGER = "alerts_pct_trigger"
    ALERTS_UNLIMITED = "alerts_unlimited"

    # ── Watchlist ────────────────────────────────────────────────────────
    # Free  : up to FREE_WATCHLIST_LIMIT cards
    # Pro   : unlimited
    WATCHLIST_EXTENDED = "watchlist_extended"
    WATCHLIST_UNLIMITED = "watchlist_unlimited"

    # ── Top Movers / Dashboard ───────────────────────────────────────────
    # Free  : basic name + price-change list
    # Pro   : liquidity score + volume trend columns
    MOVERS_DETAIL = "movers_detail"
    LIQUIDITY_SCORE = "liquidity_score"

    # ── Source comparison ────────────────────────────────────────────────
    SOURCE_COMPARISON = "source_comparison"

    # ── Pro Insights ─────────────────────────────────────────────────────
    # Curated subset of KPI data for Pro users (distinct from /admin/diagnostics)
    PRO_INSIGHTS = "pro_insights"


# ── Hard limits (used by service layer, not just bool gates) ─────────────────

FREE_HISTORY_DAYS: int = 7
PRO_HISTORY_DAYS: int = 180

FREE_ALERT_LIMIT: int = 5
PRO_ALERT_LIMIT: int | None = None           # None = unlimited

FREE_WATCHLIST_LIMIT: int = 10
PRO_WATCHLIST_LIMIT: int | None = None       # None = unlimited

FREE_SIGNALS_LIMIT: int = 5                  # top-N after sort by confidence


# ── Capability map ───────────────────────────────────────────────────────────

_TIER_CAPABILITIES: dict[str, frozenset[Feature]] = {
    "free": frozenset(),
    "pro":  frozenset(Feature),   # all features
}


# ── Public API ───────────────────────────────────────────────────────────────

def resolve_tier(email: str | None, stored_tier: str) -> str:
    """Return effective tier: promotes to 'pro' if email is in DEV_PRO_EMAILS whitelist."""
    if email and email.lower() in _DEV_PRO_EMAILS:
        return "pro"
    return stored_tier


def can(access_tier: str, feature: Feature) -> bool:
    """Return True if *access_tier* grants *feature*."""
    tier = access_tier.lower() if access_tier else "free"
    return feature in _TIER_CAPABILITIES.get(tier, frozenset())


def get_capabilities(access_tier: str) -> frozenset[Feature]:
    """Return the full capability set for *access_tier*."""
    tier = access_tier.lower() if access_tier else "free"
    return _TIER_CAPABILITIES.get(tier, frozenset())


def alert_limit(access_tier: str) -> int | None:
    """Return alert cap for tier. None = unlimited."""
    return PRO_ALERT_LIMIT if can(access_tier, Feature.ALERTS_EXTENDED) else FREE_ALERT_LIMIT


def watchlist_limit(access_tier: str) -> int | None:
    """Return watchlist cap for tier. None = unlimited."""
    return PRO_WATCHLIST_LIMIT if can(access_tier, Feature.WATCHLIST_EXTENDED) else FREE_WATCHLIST_LIMIT


def signals_limit(access_tier: str) -> int | None:
    """Return signals feed cap. None = unlimited (Pro). Int = take top-N (Free)."""
    return None if can(access_tier, Feature.SIGNALS_FULL_FEED) else FREE_SIGNALS_LIMIT


def history_days(access_tier: str) -> int:
    """Return price history window in days for tier."""
    return PRO_HISTORY_DAYS if can(access_tier, Feature.PRICE_HISTORY_FULL) else FREE_HISTORY_DAYS


_PRO_GATE_STRATEGIES: dict[str, ProGateConfig] = {
    "price_history": ProGateConfig(
        is_locked=True,
        feature_name="Extended Price History (180 days)",
        upgrade_reason="See long-term price patterns",
        urgency="medium",
    ),
    "signals_full": ProGateConfig(
        is_locked=True,
        feature_name="Unlimited Signals + AI Explanation",
        upgrade_reason="Get all market signals",
        urgency="high",
    ),
    "source_comparison": ProGateConfig(
        is_locked=True,
        feature_name="Detailed eBay vs TCG Comparison",
        upgrade_reason="Compare all price sources",
        urgency="low",
    ),
}


def get_pro_gate_config(feature: str, access_tier: str) -> ProGateConfig:
    """Return ProGateConfig for feature+tier. Unlocked if Pro; locked with strategy if Free."""
    if (access_tier or "").lower() == "pro":
        return ProGateConfig(is_locked=False)
    strategy = _PRO_GATE_STRATEGIES.get(feature)
    if strategy is None:
        return ProGateConfig(is_locked=True, upgrade_reason="Upgrade to Pro for full access")
    return strategy
