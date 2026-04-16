from __future__ import annotations

from enum import Enum

from backend.app.models.enums import AccessTier


class Feature(str, Enum):
    SIGNALS_FULL_FEED       = "signals_full_feed"
    SIGNALS_CONFIDENCE      = "signals_confidence"
    SIGNALS_AI_EXPLANATION  = "signals_ai_explanation"
    PRICE_HISTORY_FULL      = "price_history_full"
    WATCHLIST_UNLIMITED     = "watchlist_unlimited"
    ALERTS_UNLIMITED        = "alerts_unlimited"
    LIQUIDITY_SCORE         = "liquidity_score"
    SOURCE_COMPARISON       = "source_comparison"


_TIER_CAPABILITIES: dict[str, frozenset[Feature]] = {
    AccessTier.FREE: frozenset(),
    AccessTier.PRO:  frozenset(Feature),
}


def get_capabilities(access_tier: str) -> frozenset[Feature]:
    """Return the frozenset of Features for the given access_tier string."""
    return _TIER_CAPABILITIES.get(access_tier, frozenset())


def can(access_tier: str, feature: Feature) -> bool:
    """Return True if access_tier grants the given feature."""
    return feature in get_capabilities(access_tier)
