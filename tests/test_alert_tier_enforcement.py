"""
tests/test_alert_tier_enforcement.py

Covers:
  - PCT_TRIGGER_TYPES / FREE_ALERT_TYPES constant membership
  - is_tier_error() predicate
  - create_alert() pct-trigger gate (free tier blocked, pro allowed)
  - create_alert() alert count limit (free capped at FREE_ALERT_LIMIT)
  - _upgrade_banner_html / _progate_html structural contract
"""
from __future__ import annotations

import unittest
import uuid
from unittest.mock import MagicMock, patch

from sqlalchemy.orm import Session


# ── helpers ───────────────────────────────────────────────────────────────────

def _mock_user(*, access_tier: str = "free") -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.access_tier = access_tier
    return user


def _make_payload(
    *,
    alert_type: str = "TARGET_PRICE_HIT",
    discord_user_id: str | None = None,
) -> MagicMock:
    payload = MagicMock()
    payload.discord_user_id = discord_user_id or str(uuid.uuid4())[:20]
    payload.alert_type = alert_type
    payload.threshold_percent = None
    payload.target_price = None
    payload.direction = None
    return payload


# ── A: constants ──────────────────────────────────────────────────────────────

class TestPCTTriggerTypes(unittest.TestCase):
    def test_price_up_threshold_in_pct(self):
        from backend.app.services.alert_service import PCT_TRIGGER_TYPES
        self.assertIn("PRICE_UP_THRESHOLD", PCT_TRIGGER_TYPES)

    def test_price_down_threshold_in_pct(self):
        from backend.app.services.alert_service import PCT_TRIGGER_TYPES
        self.assertIn("PRICE_DOWN_THRESHOLD", PCT_TRIGGER_TYPES)

    def test_predict_up_prob_in_pct(self):
        from backend.app.services.alert_service import PCT_TRIGGER_TYPES
        self.assertIn("PREDICT_UP_PROBABILITY_ABOVE", PCT_TRIGGER_TYPES)

    def test_predict_down_prob_in_pct(self):
        from backend.app.services.alert_service import PCT_TRIGGER_TYPES
        self.assertIn("PREDICT_DOWN_PROBABILITY_ABOVE", PCT_TRIGGER_TYPES)

    def test_target_price_hit_not_in_pct(self):
        from backend.app.services.alert_service import PCT_TRIGGER_TYPES
        self.assertNotIn("TARGET_PRICE_HIT", PCT_TRIGGER_TYPES)

    def test_predict_signal_change_not_in_pct(self):
        from backend.app.services.alert_service import PCT_TRIGGER_TYPES
        self.assertNotIn("PREDICT_SIGNAL_CHANGE", PCT_TRIGGER_TYPES)


class TestFreeAlertTypes(unittest.TestCase):
    def test_target_price_hit_is_free(self):
        from backend.app.services.alert_service import FREE_ALERT_TYPES
        self.assertIn("TARGET_PRICE_HIT", FREE_ALERT_TYPES)

    def test_predict_signal_change_is_free(self):
        from backend.app.services.alert_service import FREE_ALERT_TYPES
        self.assertIn("PREDICT_SIGNAL_CHANGE", FREE_ALERT_TYPES)

    def test_pct_types_not_free(self):
        from backend.app.services.alert_service import FREE_ALERT_TYPES, PCT_TRIGGER_TYPES
        self.assertTrue(PCT_TRIGGER_TYPES.isdisjoint(FREE_ALERT_TYPES))


# ── B: is_tier_error predicate ────────────────────────────────────────────────

class TestIsTierError(unittest.TestCase):
    def test_tier_prefix_detected(self):
        from backend.app.services.alert_service import _TIER_ERROR_PREFIX, is_tier_error
        self.assertTrue(is_tier_error(f"{_TIER_ERROR_PREFIX} something"))

    def test_non_tier_message_false(self):
        from backend.app.services.alert_service import is_tier_error
        self.assertFalse(is_tier_error("No asset found matching 'Pikachu'"))

    def test_empty_message_false(self):
        from backend.app.services.alert_service import is_tier_error
        self.assertFalse(is_tier_error(""))

    def test_partial_prefix_false(self):
        from backend.app.services.alert_service import is_tier_error
        self.assertFalse(is_tier_error("tier error without bracket"))

    def test_actual_pct_gate_message_detected(self):
        from backend.app.services.alert_service import _TIER_ERROR_PREFIX, is_tier_error
        msg = f"{_TIER_ERROR_PREFIX} Alert type 'PRICE_UP_THRESHOLD' requires Pro."
        self.assertTrue(is_tier_error(msg))

    def test_actual_limit_message_detected(self):
        from backend.app.services.alert_service import _TIER_ERROR_PREFIX, is_tier_error
        msg = f"{_TIER_ERROR_PREFIX} Alert limit reached (5 active alerts)."
        self.assertTrue(is_tier_error(msg))


# ── C: pct-trigger gate ───────────────────────────────────────────────────────

class TestPCTTriggerGate(unittest.TestCase):
    """
    Tests the pct-trigger gate inside create_alert().
    We mock get_or_create_user to control access_tier without a real DB.
    The error is raised before any db.scalar call, so no DB setup needed.
    """

    def _create(self, *, alert_type: str, access_tier: str) -> Exception | None:
        from backend.app.services.alert_service import create_alert
        db = MagicMock(spec=Session)
        payload = _make_payload(alert_type=alert_type)
        user = _mock_user(access_tier=access_tier)
        with patch("backend.app.services.alert_service.get_or_create_user", return_value=user):
            try:
                create_alert(db, payload)
                return None
            except Exception as exc:
                return exc

    def test_free_pct_trigger_raises_value_error(self):
        exc = self._create(alert_type="PRICE_UP_THRESHOLD", access_tier="free")
        self.assertIsInstance(exc, ValueError)

    def test_free_pct_trigger_error_is_tier_error(self):
        from backend.app.services.alert_service import is_tier_error
        exc = self._create(alert_type="PRICE_UP_THRESHOLD", access_tier="free")
        self.assertTrue(is_tier_error(str(exc)))

    def test_free_price_down_blocked(self):
        exc = self._create(alert_type="PRICE_DOWN_THRESHOLD", access_tier="free")
        self.assertIsInstance(exc, ValueError)

    def test_free_predict_up_prob_blocked(self):
        exc = self._create(alert_type="PREDICT_UP_PROBABILITY_ABOVE", access_tier="free")
        self.assertIsInstance(exc, ValueError)

    def test_free_predict_down_prob_blocked(self):
        exc = self._create(alert_type="PREDICT_DOWN_PROBABILITY_ABOVE", access_tier="free")
        self.assertIsInstance(exc, ValueError)

    def test_free_target_price_hit_not_blocked_by_pct_gate(self):
        """TARGET_PRICE_HIT passes the pct gate (may fail later at asset lookup)."""
        exc = self._create(alert_type="TARGET_PRICE_HIT", access_tier="free")
        # Error must NOT be a tier error — it may be a ValueError for missing asset
        if exc is not None:
            from backend.app.services.alert_service import is_tier_error
            self.assertFalse(is_tier_error(str(exc)))

    def test_free_predict_signal_change_not_blocked_by_pct_gate(self):
        exc = self._create(alert_type="PREDICT_SIGNAL_CHANGE", access_tier="free")
        if exc is not None:
            from backend.app.services.alert_service import is_tier_error
            self.assertFalse(is_tier_error(str(exc)))

    def test_pro_pct_trigger_passes_gate(self):
        """Pro user should pass the pct gate (error can only come from asset lookup)."""
        exc = self._create(alert_type="PRICE_UP_THRESHOLD", access_tier="pro")
        if exc is not None:
            from backend.app.services.alert_service import is_tier_error
            self.assertFalse(is_tier_error(str(exc)))


# ── D: alert count limit ──────────────────────────────────────────────────────

class TestAlertLimitGate(unittest.TestCase):
    """
    Tests the alert count limit gate inside create_alert().
    Use a free-type (TARGET_PRICE_HIT) to bypass the pct gate and hit the limit check.
    db.scalar returns the mocked active count.
    """

    def _create_with_count(self, *, access_tier: str, active_count: int) -> Exception | None:
        from backend.app.services.alert_service import create_alert
        db = MagicMock(spec=Session)
        db.scalar.return_value = active_count
        payload = _make_payload(alert_type="TARGET_PRICE_HIT")
        user = _mock_user(access_tier=access_tier)
        with patch("backend.app.services.alert_service.get_or_create_user", return_value=user):
            try:
                create_alert(db, payload)
                return None
            except Exception as exc:
                return exc

    def test_free_at_limit_raises(self):
        from backend.app.core.permissions import FREE_ALERT_LIMIT
        exc = self._create_with_count(access_tier="free", active_count=FREE_ALERT_LIMIT)
        self.assertIsInstance(exc, ValueError)

    def test_free_at_limit_is_tier_error(self):
        from backend.app.core.permissions import FREE_ALERT_LIMIT
        from backend.app.services.alert_service import is_tier_error
        exc = self._create_with_count(access_tier="free", active_count=FREE_ALERT_LIMIT)
        self.assertTrue(is_tier_error(str(exc)))

    def test_free_over_limit_raises(self):
        from backend.app.core.permissions import FREE_ALERT_LIMIT
        exc = self._create_with_count(access_tier="free", active_count=FREE_ALERT_LIMIT + 3)
        self.assertIsInstance(exc, ValueError)

    def test_free_under_limit_passes_gate(self):
        from backend.app.core.permissions import FREE_ALERT_LIMIT
        exc = self._create_with_count(access_tier="free", active_count=FREE_ALERT_LIMIT - 1)
        # Should not be a tier error (may error at asset lookup — that's fine)
        if exc is not None:
            from backend.app.services.alert_service import is_tier_error
            self.assertFalse(is_tier_error(str(exc)))

    def test_pro_ignores_limit(self):
        """Pro users have no limit; db.scalar should not be called for the count."""
        from backend.app.services.alert_service import create_alert
        db = MagicMock(spec=Session)
        # scalar returns None for asset lookup (simulates missing asset)
        db.scalar.return_value = None
        payload = _make_payload(alert_type="PRICE_UP_THRESHOLD")
        user = _mock_user(access_tier="pro")
        with patch("backend.app.services.alert_service.get_or_create_user", return_value=user):
            try:
                create_alert(db, payload)
            except ValueError as exc:
                from backend.app.services.alert_service import is_tier_error
                self.assertFalse(is_tier_error(str(exc)))

    def test_free_zero_alerts_allowed(self):
        exc = self._create_with_count(access_tier="free", active_count=0)
        if exc is not None:
            from backend.app.services.alert_service import is_tier_error
            self.assertFalse(is_tier_error(str(exc)))


# ── E: banner contract ────────────────────────────────────────────────────────

class TestUpgradeBannerHtml(unittest.TestCase):
    def test_contains_feature_label(self):
        from backend.app.core.banner import _upgrade_banner_html
        html = _upgrade_banner_html("the full signals feed")
        self.assertIn("the full signals feed", html)

    def test_contains_upgrade_url(self):
        from backend.app.core.banner import UPGRADE_URL, _upgrade_banner_html
        html = _upgrade_banner_html("unlimited alerts")
        self.assertIn(UPGRADE_URL, html)

    def test_hidden_count_shown_when_nonzero(self):
        from backend.app.core.banner import _upgrade_banner_html
        html = _upgrade_banner_html("signals", hidden_count=7)
        self.assertIn("7", html)

    def test_hidden_count_not_shown_when_zero(self):
        from backend.app.core.banner import _upgrade_banner_html
        html = _upgrade_banner_html("signals", hidden_count=0)
        self.assertNotIn("more available", html)

    def test_custom_cta_label(self):
        from backend.app.core.banner import _upgrade_banner_html
        html = _upgrade_banner_html("signals", cta_label="Go Pro Now")
        self.assertIn("Go Pro Now", html)


class TestProgateHtml(unittest.TestCase):
    def test_contains_blurred_content(self):
        from backend.app.core.banner import _progate_html
        html = _progate_html("View Full History", "<p>blurred</p>")
        self.assertIn("<p>blurred</p>", html)

    def test_contains_cta_label(self):
        from backend.app.core.banner import _progate_html
        html = _progate_html("View Full History", "<p>x</p>")
        self.assertIn("View Full History", html)

    def test_contains_upgrade_url(self):
        from backend.app.core.banner import UPGRADE_URL, _progate_html
        html = _progate_html("View Full History", "<p>x</p>")
        self.assertIn(UPGRADE_URL, html)

    def test_contains_feature_label_in_aria(self):
        from backend.app.core.banner import _progate_html
        html = _progate_html("View Full History", "<p>x</p>", "180-day price history")
        self.assertIn("180-day price history", html)

    def test_blur_class_present(self):
        from backend.app.core.banner import _progate_html
        html = _progate_html("Unlock", "<p>x</p>")
        self.assertIn("progate__blur", html)


if __name__ == "__main__":
    unittest.main()
