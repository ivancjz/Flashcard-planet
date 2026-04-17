import pytest
from backend.app.core.permissions import Feature, can, get_capabilities
from backend.app.models.enums import AccessTier


class TestAccessTierEnum:
    def test_free_value_matches_db_string(self):
        assert AccessTier.FREE.value == "free"

    def test_pro_value_matches_db_string(self):
        assert AccessTier.PRO.value == "pro"

    def test_enum_members_are_only_free_and_pro(self):
        values = {t.value for t in AccessTier}
        assert values == {"free", "pro"}


class TestGetCapabilities:
    def test_free_tier_returns_empty_frozenset(self):
        caps = get_capabilities(AccessTier.FREE)
        assert caps == frozenset()

    def test_pro_tier_returns_all_features(self):
        caps = get_capabilities(AccessTier.PRO)
        assert caps == frozenset(Feature)

    def test_unknown_tier_returns_empty_frozenset(self):
        assert get_capabilities("legacy_beta") == frozenset()
        assert get_capabilities("") == frozenset()
        assert get_capabilities("ADMIN") == frozenset()

    def test_returns_frozenset_type(self):
        assert isinstance(get_capabilities("free"), frozenset)
        assert isinstance(get_capabilities("pro"), frozenset)

    def test_string_lookup_works_same_as_enum_lookup(self):
        # AccessTier is str, Enum — "free" and AccessTier.FREE are the same key
        assert get_capabilities("free") == get_capabilities(AccessTier.FREE)
        assert get_capabilities("pro") == get_capabilities(AccessTier.PRO)


class TestCan:
    def test_free_user_cannot_access_any_pro_feature(self):
        for feature in Feature:
            assert can("free", feature) is False

    def test_pro_user_can_access_all_features(self):
        for feature in Feature:
            assert can("pro", feature) is True

    def test_unknown_tier_cannot_access_any_feature(self):
        for feature in Feature:
            assert can("unknown", feature) is False

    def test_returns_bool(self):
        result = can("pro", Feature.SIGNALS_FULL_FEED)
        assert type(result) is bool

    def test_specific_features_for_free(self):
        assert can("free", Feature.SIGNALS_FULL_FEED) is False
        assert can("free", Feature.PRICE_HISTORY_FULL) is False
        assert can("free", Feature.ALERTS_UNLIMITED) is False

    def test_specific_features_for_pro(self):
        assert can("pro", Feature.SIGNALS_FULL_FEED) is True
        assert can("pro", Feature.PRICE_HISTORY_FULL) is True
        assert can("pro", Feature.ALERTS_UNLIMITED) is True


class TestFeatureEnum:
    def test_all_expected_features_exist(self):
        expected = {
            "price_history_full",
            "card_source_breakdown",
            "signal_explanation",
            "signals_full_feed",
            "signals_confidence",
            "signals_ai_explanation",
            "alerts_extended",
            "alerts_pct_trigger",
            "alerts_unlimited",
            "watchlist_extended",
            "watchlist_unlimited",
            "movers_detail",
            "liquidity_score",
            "source_comparison",
            "pro_insights",
        }
        actual = {f.value for f in Feature}
        assert actual == expected

    def test_feature_is_str_enum(self):
        assert isinstance(Feature.SIGNALS_FULL_FEED, str)


class TestGetProGateConfig:
    def test_pro_user_returns_unlocked(self):
        from backend.app.core.permissions import get_pro_gate_config
        result = get_pro_gate_config("price_history", "pro")
        assert result.is_locked is False

    def test_free_user_price_history_is_locked(self):
        from backend.app.core.permissions import get_pro_gate_config
        result = get_pro_gate_config("price_history", "free")
        assert result.is_locked is True
        assert result.urgency == "medium"
        assert "180" in result.feature_name or "History" in result.feature_name

    def test_free_user_signals_full_is_high_urgency(self):
        from backend.app.core.permissions import get_pro_gate_config
        result = get_pro_gate_config("signals_full", "free")
        assert result.is_locked is True
        assert result.urgency == "high"

    def test_free_user_source_comparison_is_low_urgency(self):
        from backend.app.core.permissions import get_pro_gate_config
        result = get_pro_gate_config("source_comparison", "free")
        assert result.is_locked is True
        assert result.urgency == "low"

    def test_unknown_feature_returns_generic_locked_config(self):
        from backend.app.core.permissions import get_pro_gate_config
        result = get_pro_gate_config("nonexistent_feature", "free")
        assert result.is_locked is True
        assert result.upgrade_reason  # non-empty
