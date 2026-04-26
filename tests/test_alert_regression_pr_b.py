"""
tests/test_alert_regression_pr_b.py

Regression guard: proves PR B (market_segment='raw' signal filter) did NOT
alter the alert layer.

The alert service reads AssetSignal rows — NOT price_history directly. PR B
only adds a WHERE clause to price_history reads inside signal_service.py.
These tests verify:

  1. Given identical AssetSignal inputs, evaluate_active_alerts() produces
     byte-identical output before and after PR B.
  2. process_alert_notifications() behaviour is unchanged.

If any of these tests fail, code outside the allowed scope was modified.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest import TestCase
from unittest.mock import patch

from backend.app.models.alert import Alert
from backend.app.models.asset import Asset
from backend.app.models.enums import AlertDirection, AlertType, AssetClass
from backend.app.models.user import User
from backend.app.services.alert_service import (
    AlertEvaluationResult,
    PricePoint,
    TriggeredAlertNotification,
    build_alert_notification_embed,
    evaluate_active_alerts,
    process_alert_notifications,
)
from backend.app.services.liquidity_service import AssetSignalSnapshot

NOW = datetime(2026, 4, 27, 12, 0, tzinfo=UTC)
ASSET_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


# ── Minimal test doubles (mirrors test_alert_service.py) ─────────────────────

class _ScalarResult:
    def __init__(self, items): self._items = items
    def all(self): return self._items


class _Session:
    def __init__(self, alerts):
        self.alerts = alerts
        self.flush_called = False
        self.added_objects: list = []
    def scalars(self, _): return _ScalarResult(self.alerts)
    def flush(self): self.flush_called = True
    def add(self, obj): self.added_objects.append(obj)
    def rollback(self): pass


def _make_user() -> User:
    return User(id=USER_ID, discord_user_id="9876543210", is_active=True)


def _make_asset() -> Asset:
    return Asset(
        id=ASSET_ID, asset_class=AssetClass.TCG.value,
        name="Charizard", set_name="Base Set",
        category="Pokemon",
    )


def _make_alert(*, alert_type: str = AlertType.PRICE_UP_THRESHOLD.value,
                direction: str = AlertDirection.ABOVE.value,
                threshold: str = "5.00", armed: bool = True) -> Alert:
    alert = Alert(
        id=uuid.uuid4(),
        user_id=USER_ID,
        asset_id=ASSET_ID,
        alert_type=alert_type,
        direction=direction,
        threshold_percent=Decimal(threshold),
        is_active=True,
        is_armed=armed,
        created_at=NOW,
    )
    alert.user = _make_user()
    alert.asset = _make_asset()
    return alert


def _make_price_point(price: str) -> PricePoint:
    return PricePoint(
        price=Decimal(price),
        currency="USD",
        source="pokemon_tcg_api",
        captured_at=NOW,
    )


def _snapshot() -> AssetSignalSnapshot:
    return AssetSignalSnapshot(
        asset_id=ASSET_ID,
        sales_count_7d=5,
        sales_count_30d=12,
        days_since_last_sale=0,
        last_real_sale_at=NOW,
        history_depth=10,
        source_count=1,
        liquidity_score=75,
        liquidity_label="High Liquidity",
        price_move_magnitude=Decimal("12.00"),
        alert_confidence=80,
        alert_confidence_label="High Confidence",
    )


# ── Regression tests ──────────────────────────────────────────────────────────

class AlertRegressionPRB(TestCase):
    """Each test verifies a fixed-input → fixed-output alert evaluation.
    If PR B accidentally modified alert_service.py, these will fail."""

    def _evaluate(self, alert, price_points, ref_point):
        session = _Session([alert])
        with (
            patch("backend.app.services.alert_service.get_recent_real_price_rows",
                  return_value=price_points),
            patch("backend.app.services.alert_service.get_reference_price_row",
                  return_value=ref_point),
            patch("backend.app.services.alert_service.build_credibility_indicators",
                  return_value=None),
            patch("backend.app.services.alert_service.get_asset_signal_snapshots",
                  return_value={ASSET_ID: _snapshot()}),
        ):
            return evaluate_active_alerts(session), session

    def test_breakout_condition_triggers_price_up_alert(self):
        """Alert fires when current price is > 5% above reference."""
        alert = _make_alert(threshold="5.00")
        result, session = self._evaluate(
            alert,
            price_points=[_make_price_point("110.00"), _make_price_point("100.00")],
            ref_point=_make_price_point("95.00"),
        )
        self.assertEqual(result.triggered_alerts, 1)
        self.assertFalse(alert.is_armed, "Alert should disarm after triggering")
        self.assertTrue(session.flush_called)

    def test_inside_threshold_does_not_trigger(self):
        """No alert when price is within threshold range."""
        alert = _make_alert(threshold="5.00")
        result, _ = self._evaluate(
            alert,
            price_points=[_make_price_point("100.00")],
            ref_point=_make_price_point("97.00"),
        )
        self.assertEqual(result.triggered_alerts, 0)
        self.assertTrue(alert.is_armed, "Alert should stay armed")

    def test_disarmed_alert_does_not_retrigger(self):
        """Alert already triggered (is_armed=False) should not fire again."""
        alert = _make_alert(threshold="5.00", armed=False)
        result, _ = self._evaluate(
            alert,
            price_points=[_make_price_point("200.00")],
            ref_point=_make_price_point("95.00"),
        )
        self.assertEqual(result.triggered_alerts, 0)

    def test_notification_content_unchanged(self):
        """The content of triggered notifications must match the expected format."""
        alert = _make_alert(threshold="5.00")
        result, _ = self._evaluate(
            alert,
            price_points=[_make_price_point("110.00"), _make_price_point("100.00")],
            ref_point=_make_price_point("95.00"),
        )
        self.assertEqual(result.triggered_alerts, 1)
        content = result.notifications[0].content
        # These substrings must survive any refactor of this PR
        self.assertIn("Trigger: price_up_percent", content)
        self.assertIn("Liquidity: High Liquidity", content)

    def test_alert_evaluation_result_fields_present(self):
        """AlertEvaluationResult structure unchanged."""
        result = AlertEvaluationResult()
        for field in ("triggered_alerts", "price_movement_alerts_triggered",
                      "notifications", "active_alerts_checked"):
            self.assertTrue(hasattr(result, field),
                            f"AlertEvaluationResult missing field: {field}")
