from __future__ import annotations

import os
from enum import Enum

from backend.app.core.response_types import ProGateConfig


def _parse_dev_pro_emails(raw: str) -> frozenset[str]:
    return frozenset(e.strip().lower() for e in raw.split(",") if e.strip())


_DEV_PRO_EMAILS: frozenset[str] = _parse_dev_pro_emails(os.getenv("DEV_PRO_EMAILS", ""))


class Tier(str, Enum):
    FREE = "free"
    PLUS = "plus"
    PRO  = "pro"


class Feature(str, Enum):
    # ── Price history ────────────────────────────────────────────────────
    PRICE_HISTORY_FULL = "price_history_full"

    # ── Card Detail extras ───────────────────────────────────────────────
    CARD_SOURCE_BREAKDOWN = "card_source_breakdown"
    SIGNAL_EXPLANATION = "signal_explanation"

    # ── Signals feed ────────────────────────────────────────────────────
    SIGNALS_FULL_FEED = "signals_full_feed"
    SIGNALS_CONFIDENCE = "signals_confidence"
    SIGNALS_AI_EXPLANATION = "signals_ai_explanation"

    # ── Alerts ──────────────────────────────────────────────────────────
    ALERTS_EXTENDED = "alerts_extended"
    ALERTS_PCT_TRIGGER = "alerts_pct_trigger"
    ALERTS_UNLIMITED = "alerts_unlimited"

    # ── Watchlist ────────────────────────────────────────────────────────
    WATCHLIST_EXTENDED = "watchlist_extended"
    WATCHLIST_UNLIMITED = "watchlist_unlimited"

    # ── Top Movers / Dashboard ───────────────────────────────────────────
    MOVERS_DETAIL = "movers_detail"
    LIQUIDITY_SCORE = "liquidity_score"

    # ── Source comparison ────────────────────────────────────────────────
    SOURCE_COMPARISON = "source_comparison"

    # ── Pro Insights ─────────────────────────────────────────────────────
    PRO_INSIGHTS = "pro_insights"


# ── Feature → minimum tier required ─────────────────────────────────────────
# Plus features: extended data, AI analysis, unlimited usage
# Pro features: deep analytics, Pro-only outputs
FEATURE_TIER_REQUIREMENTS: dict[Feature, Tier] = {
    # ── Plus tier ─────────────────────────────────────────────────────────
    Feature.PRICE_HISTORY_FULL:      Tier.PLUS,
    Feature.CARD_SOURCE_BREAKDOWN:   Tier.PLUS,
    Feature.SIGNAL_EXPLANATION:      Tier.PLUS,
    Feature.SIGNALS_FULL_FEED:       Tier.PLUS,
    Feature.SIGNALS_CONFIDENCE:      Tier.PLUS,
    Feature.SIGNALS_AI_EXPLANATION:  Tier.PLUS,
    Feature.ALERTS_EXTENDED:         Tier.PLUS,
    Feature.ALERTS_PCT_TRIGGER:      Tier.PLUS,
    Feature.ALERTS_UNLIMITED:        Tier.PLUS,
    Feature.WATCHLIST_EXTENDED:      Tier.PLUS,
    Feature.WATCHLIST_UNLIMITED:     Tier.PLUS,
    Feature.MOVERS_DETAIL:           Tier.PLUS,
    Feature.SOURCE_COMPARISON:       Tier.PLUS,
    # ── Pro tier ──────────────────────────────────────────────────────────
    Feature.LIQUIDITY_SCORE:         Tier.PRO,
    Feature.PRO_INSIGHTS:            Tier.PRO,
}

# ── Hard limits (used by service layer, not just bool gates) ─────────────────

FREE_HISTORY_DAYS: int = 7
PLUS_HISTORY_DAYS: int = 180
PRO_HISTORY_DAYS:  int = 180   # same value today; separate constant for future expansion

FREE_ALERT_LIMIT: int = 5
PRO_ALERT_LIMIT: int | None = None           # None = unlimited

FREE_WATCHLIST_LIMIT: int = 10
PRO_WATCHLIST_LIMIT: int | None = None       # None = unlimited

FREE_SIGNALS_LIMIT: int = 5

DEEP_ANALYSIS_DAILY_LIMIT_PRO: int = 5


# ── Tier ordering for capability checks ─────────────────────────────────────
_TIER_ORDER: dict[str, int] = {
    Tier.FREE: 0,
    Tier.PLUS: 1,
    Tier.PRO:  2,
}

# ── Capability sets derived from FEATURE_TIER_REQUIREMENTS ──────────────────
# A tier can use a feature when TIER_ORDER[user_tier] >= TIER_ORDER[required_tier].
# _TIER_CAPABILITIES is derived once at module load for O(1) can() lookups.
def _build_capabilities() -> dict[str, frozenset[Feature]]:
    result: dict[str, frozenset[Feature]] = {"free": frozenset()}
    for tier in (Tier.PLUS, Tier.PRO):
        result[tier.value] = frozenset(
            f for f, required in FEATURE_TIER_REQUIREMENTS.items()
            if _TIER_ORDER[required] <= _TIER_ORDER[tier]
        )
    return result


_TIER_CAPABILITIES: dict[str, frozenset[Feature]] = _build_capabilities()


# ── Public API ───────────────────────────────────────────────────────────────

_ACTIVE_STATUSES = frozenset({"active", "trialing"})


def resolve_tier(
    email: str | None,
    access_tier: str,
    subscription_tier: str | None = None,
    subscription_status: str | None = None,
) -> str:
    """Return effective tier string.

    Priority:
      1. DEV_PRO_EMAILS override → always 'pro'
      2. Active/trialing LemonSqueezy subscription → subscription_tier value
      3. Legacy access_tier ('plus' or 'pro' granted manually) → access_tier
      4. Default → 'free'
    """
    if email and email.lower() in _DEV_PRO_EMAILS:
        return Tier.PRO

    if subscription_status in _ACTIVE_STATUSES and subscription_tier in (Tier.PLUS, Tier.PRO):
        return subscription_tier

    if access_tier in (Tier.PLUS, Tier.PRO):
        return access_tier

    return Tier.FREE


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
    """Return signals feed cap. None = unlimited (Plus/Pro). Int = top-N (Free)."""
    return None if can(access_tier, Feature.SIGNALS_FULL_FEED) else FREE_SIGNALS_LIMIT


def history_days(access_tier: str) -> int:
    """Return price history window in days for tier."""
    return PLUS_HISTORY_DAYS if can(access_tier, Feature.PRICE_HISTORY_FULL) else FREE_HISTORY_DAYS


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
    """Return ProGateConfig for feature+tier. Unlocked if Plus/Pro; locked with strategy if Free."""
    if (access_tier or "").lower() in (Tier.PLUS, Tier.PRO):
        return ProGateConfig(is_locked=False)
    strategy = _PRO_GATE_STRATEGIES.get(feature)
    if strategy is None:
        return ProGateConfig(is_locked=True, upgrade_reason="Upgrade to Pro for full access")
    return strategy
