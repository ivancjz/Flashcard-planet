import pytest
import backend.app.core.permissions as perms_module
from backend.app.core.permissions import Feature, can, get_capabilities
from backend.app.models.enums import AccessTier


class TestAccessTierEnum:
    def test_free_value_matches_db_string(self):
        assert AccessTier.FREE.value == "free"

    def test_plus_value_matches_db_string(self):
        assert AccessTier.PLUS.value == "plus"

    def test_pro_value_matches_db_string(self):
        assert AccessTier.PRO.value == "pro"

    def test_enum_members_are_free_plus_pro(self):
        values = {t.value for t in AccessTier}
        assert values == {"free", "plus", "pro"}


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


class TestResolveDevProTier:
    def test_dev_pro_email_grants_pro(self, monkeypatch):
        from backend.app.core.permissions import resolve_tier
        monkeypatch.setattr(perms_module, "_DEV_PRO_EMAILS", frozenset({"ivan@test.com"}))
        assert resolve_tier("ivan@test.com", "free") == "pro"

    def test_dev_pro_email_case_insensitive(self, monkeypatch):
        from backend.app.core.permissions import resolve_tier
        monkeypatch.setattr(perms_module, "_DEV_PRO_EMAILS", frozenset({"ivan@test.com"}))
        assert resolve_tier("IVAN@TEST.COM", "free") == "pro"

    def test_no_env_var_means_no_override(self, monkeypatch):
        from backend.app.core.permissions import resolve_tier
        monkeypatch.setattr(perms_module, "_DEV_PRO_EMAILS", frozenset())
        assert resolve_tier("ivan@test.com", "free") == "free"

    def test_invalid_email_in_env_var_no_crash(self):
        from backend.app.core.permissions import _parse_dev_pro_emails
        assert _parse_dev_pro_emails("  ,  ,  ") == frozenset()
        assert _parse_dev_pro_emails("") == frozenset()
        assert _parse_dev_pro_emails("ivan@test.com, , ") == frozenset({"ivan@test.com"})


# ── New tests for TASK-301a ────────────────────────────────────────────────────

class TestTierEnum:
    """Tier enum lives in permissions.py (distinct from AccessTier in enums.py)."""

    def test_free_value(self):
        from backend.app.core.permissions import Tier
        assert Tier.FREE.value == "free"

    def test_plus_value(self):
        from backend.app.core.permissions import Tier
        assert Tier.PLUS.value == "plus"

    def test_pro_value(self):
        from backend.app.core.permissions import Tier
        assert Tier.PRO.value == "pro"

    def test_members_are_exactly_free_plus_pro(self):
        from backend.app.core.permissions import Tier
        assert {t.value for t in Tier} == {"free", "plus", "pro"}

    def test_is_str_enum(self):
        from backend.app.core.permissions import Tier
        assert isinstance(Tier.PLUS, str)
        assert Tier.PLUS == "plus"


class TestPlusTierCapabilities:
    def test_plus_gets_plus_gated_features(self):
        assert can("plus", Feature.SIGNAL_EXPLANATION) is True
        assert can("plus", Feature.PRICE_HISTORY_FULL) is True
        assert can("plus", Feature.SIGNALS_FULL_FEED) is True
        assert can("plus", Feature.ALERTS_UNLIMITED) is True
        assert can("plus", Feature.WATCHLIST_UNLIMITED) is True

    def test_plus_does_not_get_pro_only_features(self):
        assert can("plus", Feature.LIQUIDITY_SCORE) is False
        assert can("plus", Feature.PRO_INSIGHTS) is False

    def test_pro_still_gets_all_features(self):
        for feature in Feature:
            assert can("pro", feature) is True

    def test_free_still_gets_no_features(self):
        for feature in Feature:
            assert can("free", feature) is False

    def test_get_capabilities_plus_is_subset_of_pro(self):
        plus_caps = get_capabilities("plus")
        pro_caps = get_capabilities("pro")
        assert plus_caps.issubset(pro_caps)
        assert plus_caps != pro_caps   # plus is strictly smaller than pro

    def test_get_capabilities_plus_is_superset_of_free(self):
        assert get_capabilities("plus").issuperset(get_capabilities("free"))
        assert get_capabilities("plus") != get_capabilities("free")


class TestResolveTierSubscription:
    def test_returns_plus_for_active_subscription_plus(self, monkeypatch):
        from backend.app.core.permissions import resolve_tier
        monkeypatch.setattr(perms_module, "_DEV_PRO_EMAILS", frozenset())
        assert resolve_tier(
            email=None,
            access_tier="free",
            subscription_tier="plus",
            subscription_status="active",
        ) == "plus"

    def test_returns_pro_for_active_subscription_pro(self, monkeypatch):
        from backend.app.core.permissions import resolve_tier
        monkeypatch.setattr(perms_module, "_DEV_PRO_EMAILS", frozenset())
        assert resolve_tier(
            email=None,
            access_tier="free",
            subscription_tier="pro",
            subscription_status="active",
        ) == "pro"

    def test_trialing_subscription_grants_tier(self, monkeypatch):
        from backend.app.core.permissions import resolve_tier
        monkeypatch.setattr(perms_module, "_DEV_PRO_EMAILS", frozenset())
        assert resolve_tier(
            email=None,
            access_tier="free",
            subscription_tier="plus",
            subscription_status="trialing",
        ) == "plus"

    def test_cancelled_subscription_falls_back_to_access_tier(self, monkeypatch):
        from backend.app.core.permissions import resolve_tier
        monkeypatch.setattr(perms_module, "_DEV_PRO_EMAILS", frozenset())
        assert resolve_tier(
            email=None,
            access_tier="free",
            subscription_tier="plus",
            subscription_status="cancelled",
        ) == "free"

    def test_expired_subscription_falls_back_to_access_tier(self, monkeypatch):
        from backend.app.core.permissions import resolve_tier
        monkeypatch.setattr(perms_module, "_DEV_PRO_EMAILS", frozenset())
        assert resolve_tier(
            email=None,
            access_tier="free",
            subscription_tier="pro",
            subscription_status="expired",
        ) == "free"

    def test_dev_email_beats_subscription_tier(self, monkeypatch):
        from backend.app.core.permissions import resolve_tier
        monkeypatch.setattr(perms_module, "_DEV_PRO_EMAILS", frozenset({"ivan@test.com"}))
        assert resolve_tier(
            email="ivan@test.com",
            access_tier="free",
            subscription_tier="plus",
            subscription_status="active",
        ) == "pro"

    def test_subscription_beats_access_tier(self, monkeypatch):
        from backend.app.core.permissions import resolve_tier
        monkeypatch.setattr(perms_module, "_DEV_PRO_EMAILS", frozenset())
        assert resolve_tier(
            email=None,
            access_tier="plus",
            subscription_tier="pro",
            subscription_status="active",
        ) == "pro"

    def test_access_tier_plus_grants_plus_when_no_subscription(self, monkeypatch):
        from backend.app.core.permissions import resolve_tier
        monkeypatch.setattr(perms_module, "_DEV_PRO_EMAILS", frozenset())
        assert resolve_tier(
            email=None,
            access_tier="plus",
            subscription_tier=None,
            subscription_status=None,
        ) == "plus"

    def test_default_is_free_when_nothing_set(self, monkeypatch):
        from backend.app.core.permissions import resolve_tier
        monkeypatch.setattr(perms_module, "_DEV_PRO_EMAILS", frozenset())
        assert resolve_tier(
            email=None,
            access_tier="free",
            subscription_tier=None,
            subscription_status=None,
        ) == "free"

    def test_backward_compat_two_arg_call_still_works(self, monkeypatch):
        from backend.app.core.permissions import resolve_tier
        monkeypatch.setattr(perms_module, "_DEV_PRO_EMAILS", frozenset())
        # Existing callers that pass only (email, access_tier) must keep working
        assert resolve_tier("user@test.com", "pro") == "pro"
        assert resolve_tier("user@test.com", "plus") == "plus"
        assert resolve_tier("user@test.com", "free") == "free"


class TestPermissionsConstants:
    def test_plus_history_days_is_180(self):
        from backend.app.core.permissions import PLUS_HISTORY_DAYS
        assert PLUS_HISTORY_DAYS == 180

    def test_pro_history_days_still_exists_and_is_180(self):
        from backend.app.core.permissions import PRO_HISTORY_DAYS
        assert PRO_HISTORY_DAYS == 180

    def test_deep_analysis_daily_limit_pro_is_5(self):
        from backend.app.core.permissions import DEEP_ANALYSIS_DAILY_LIMIT_PRO
        assert DEEP_ANALYSIS_DAILY_LIMIT_PRO == 5


class TestFeatureTierRequirements:
    def test_signal_explanation_maps_to_plus(self):
        from backend.app.core.permissions import FEATURE_TIER_REQUIREMENTS, Tier
        assert FEATURE_TIER_REQUIREMENTS[Feature.SIGNAL_EXPLANATION] == Tier.PLUS

    def test_price_history_full_maps_to_plus(self):
        from backend.app.core.permissions import FEATURE_TIER_REQUIREMENTS, Tier
        assert FEATURE_TIER_REQUIREMENTS[Feature.PRICE_HISTORY_FULL] == Tier.PLUS

    def test_liquidity_score_maps_to_pro(self):
        from backend.app.core.permissions import FEATURE_TIER_REQUIREMENTS, Tier
        assert FEATURE_TIER_REQUIREMENTS[Feature.LIQUIDITY_SCORE] == Tier.PRO

    def test_pro_insights_maps_to_pro(self):
        from backend.app.core.permissions import FEATURE_TIER_REQUIREMENTS, Tier
        assert FEATURE_TIER_REQUIREMENTS[Feature.PRO_INSIGHTS] == Tier.PRO

    def test_all_features_have_a_tier(self):
        from backend.app.core.permissions import FEATURE_TIER_REQUIREMENTS
        for feature in Feature:
            assert feature in FEATURE_TIER_REQUIREMENTS, (
                f"{feature} missing from FEATURE_TIER_REQUIREMENTS"
            )

    def test_all_tier_values_are_valid_tier_members(self):
        from backend.app.core.permissions import FEATURE_TIER_REQUIREMENTS, Tier
        valid = set(Tier)
        for feature, tier in FEATURE_TIER_REQUIREMENTS.items():
            assert tier in valid, f"{feature} mapped to unknown tier {tier!r}"

    def test_no_feature_maps_to_free_tier(self):
        from backend.app.core.permissions import FEATURE_TIER_REQUIREMENTS, Tier
        # All Feature enum values require at least Plus — Free users get none
        for feature, tier in FEATURE_TIER_REQUIREMENTS.items():
            assert tier != Tier.FREE, f"{feature} should not be Tier.FREE"
