import backend.app.core.permissions as permissions
from backend.app.core.permissions import (
    FEATURE_TIER_REQUIREMENTS,
    FREE_PORTFOLIO_POSITION_LIMIT,
    Feature,
    Tier,
    can,
    portfolio_position_limit,
)


def test_portfolio_unlimited_requires_plus():
    assert Feature.PORTFOLIO_UNLIMITED.value == "portfolio_unlimited"
    assert FEATURE_TIER_REQUIREMENTS[Feature.PORTFOLIO_UNLIMITED] == Tier.PLUS


def test_free_portfolio_access_is_limited():
    assert can("free", Feature.PORTFOLIO_UNLIMITED) is False
    assert FREE_PORTFOLIO_POSITION_LIMIT == 10
    assert portfolio_position_limit("free") == 10


def test_plus_and_pro_portfolio_access_is_unlimited():
    for tier in ("plus", "pro"):
        assert can(tier, Feature.PORTFOLIO_UNLIMITED) is True
        assert portfolio_position_limit(tier) is None


def test_unknown_and_blank_portfolio_access_fails_closed():
    for tier in ("legacy_beta", ""):
        assert can(tier, Feature.PORTFOLIO_UNLIMITED) is False
        assert portfolio_position_limit(tier) == 10


def test_portfolio_limit_is_independent_from_watchlist_limit(monkeypatch):
    monkeypatch.setattr(permissions, "FREE_WATCHLIST_LIMIT", 3)

    assert portfolio_position_limit("free") == FREE_PORTFOLIO_POSITION_LIMIT
