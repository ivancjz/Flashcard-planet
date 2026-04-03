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
    evaluate_active_alerts,
    process_alert_notifications,
)
from backend.app.services.price_service import PredictionComputation


NOW = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)


class FakeScalarResult:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


class FakeSession:
    def __init__(self, alerts):
        self.alerts = alerts
        self.flush_called = False
        self.commit_called = False
        self.rollback_called = False

    def scalars(self, _stmt):
        return FakeScalarResult(self.alerts)

    def flush(self):
        self.flush_called = True

    def commit(self):
        self.commit_called = True

    def rollback(self):
        self.rollback_called = True

    def get(self, _model, alert_id):
        for alert in self.alerts:
            if alert.id == alert_id:
                return alert
        return None


def make_price_point(price: str, *, captured_at: datetime | None = None) -> PricePoint:
    return PricePoint(
        price=Decimal(price),
        currency="USD",
        source="pokemon_tcg_api",
        captured_at=captured_at or NOW,
    )


def make_prediction(
    prediction: str,
    *,
    up: str | None,
    down: str | None,
    flat: str | None,
    points_used: int = 5,
) -> PredictionComputation:
    return PredictionComputation(
        prediction=prediction,
        up_probability=Decimal(up) if up is not None else None,
        down_probability=Decimal(down) if down is not None else None,
        flat_probability=Decimal(flat) if flat is not None else None,
        reason="test",
        points_used=points_used,
    )


def make_alert(
    *,
    alert_type: str,
    direction: str | None = None,
    threshold_percent: str | None = None,
    target_price: str | None = None,
    is_active: bool = True,
    is_armed: bool = True,
    last_observed_signal: str | None = None,
    last_triggered_at: datetime | None = None,
) -> Alert:
    user = User(
        id=uuid.uuid4(),
        discord_user_id="1234567890",
        is_active=True,
    )
    asset = Asset(
        id=uuid.uuid4(),
        asset_class=AssetClass.TCG.value,
        category="Pokemon",
        name="Charizard",
        set_name="Base Set",
    )
    alert = Alert(
        id=uuid.uuid4(),
        user_id=user.id,
        asset_id=asset.id,
        alert_type=alert_type,
        direction=direction,
        threshold_percent=Decimal(threshold_percent) if threshold_percent is not None else None,
        target_price=Decimal(target_price) if target_price is not None else None,
        is_active=is_active,
        is_armed=is_armed,
        last_observed_signal=last_observed_signal,
        last_triggered_at=last_triggered_at,
        created_at=NOW,
    )
    alert.user = user
    alert.asset = asset
    return alert


class AlertServiceTests(TestCase):
    def test_price_threshold_crossing_triggers_and_disarms(self):
        alert = make_alert(
            alert_type=AlertType.PRICE_UP_THRESHOLD.value,
            direction=AlertDirection.ABOVE.value,
            threshold_percent="5.00",
        )
        session = FakeSession([alert])

        with (
            patch(
                "backend.app.services.alert_service.get_recent_real_price_rows",
                return_value=[make_price_point("110.00"), make_price_point("100.00")],
            ),
            patch(
                "backend.app.services.alert_service.get_reference_price_row",
                return_value=make_price_point("95.00"),
            ),
        ):
            result = evaluate_active_alerts(session)

        self.assertEqual(result.triggered_alerts, 1)
        self.assertEqual(result.price_movement_alerts_triggered, 1)
        self.assertFalse(alert.is_armed)
        self.assertIsNotNone(alert.last_triggered_at)
        self.assertTrue(session.flush_called)
        self.assertIn("Trigger: price_up_percent", result.notifications[0].content)

    def test_price_threshold_rearms_after_returning_inside_range(self):
        alert = make_alert(
            alert_type=AlertType.PRICE_UP_THRESHOLD.value,
            direction=AlertDirection.ABOVE.value,
            threshold_percent="5.00",
            is_armed=False,
        )
        session = FakeSession([alert])

        with (
            patch(
                "backend.app.services.alert_service.get_recent_real_price_rows",
                return_value=[make_price_point("101.00"), make_price_point("100.00")],
            ),
            patch(
                "backend.app.services.alert_service.get_reference_price_row",
                return_value=make_price_point("95.00"),
            ),
        ):
            result = evaluate_active_alerts(session)

        self.assertEqual(result.triggered_alerts, 0)
        self.assertEqual(result.alerts_rearmed, 1)
        self.assertTrue(alert.is_armed)

    def test_prediction_signal_change_tracks_then_triggers_on_label_change(self):
        alert = make_alert(
            alert_type=AlertType.PREDICT_SIGNAL_CHANGE.value,
            direction=None,
            is_armed=True,
            last_observed_signal=None,
        )
        session = FakeSession([alert])

        with (
            patch(
                "backend.app.services.alert_service.get_recent_real_price_rows",
                return_value=[make_price_point("100.00"), make_price_point("99.00")],
            ),
            patch(
                "backend.app.services.alert_service.get_reference_price_row",
                return_value=make_price_point("99.00"),
            ),
            patch(
                "backend.app.services.alert_service.get_prediction_state_for_asset",
                return_value=make_prediction("Flat", up="15.00", down="15.00", flat="70.00"),
            ),
        ):
            first_result = evaluate_active_alerts(session)

        self.assertEqual(first_result.triggered_alerts, 0)
        self.assertEqual(alert.last_observed_signal, "Flat")

        with (
            patch(
                "backend.app.services.alert_service.get_recent_real_price_rows",
                return_value=[make_price_point("102.00"), make_price_point("100.00")],
            ),
            patch(
                "backend.app.services.alert_service.get_reference_price_row",
                return_value=make_price_point("99.00"),
            ),
            patch(
                "backend.app.services.alert_service.get_prediction_state_for_asset",
                return_value=make_prediction("Up", up="68.00", down="10.00", flat="22.00"),
            ),
        ):
            second_result = evaluate_active_alerts(session)

        self.assertEqual(second_result.triggered_alerts, 1)
        self.assertEqual(second_result.prediction_alerts_triggered, 1)
        self.assertEqual(alert.last_observed_signal, "Up")
        self.assertIn("Prediction change: Flat -> Up", second_result.notifications[0].content)

    def test_prediction_probability_threshold_rearms_after_dropping_below_threshold(self):
        alert = make_alert(
            alert_type=AlertType.PREDICT_UP_PROBABILITY_ABOVE.value,
            threshold_percent="60.00",
            direction=None,
            is_armed=True,
        )
        session = FakeSession([alert])

        with (
            patch(
                "backend.app.services.alert_service.get_recent_real_price_rows",
                return_value=[make_price_point("105.00"), make_price_point("100.00")],
            ),
            patch(
                "backend.app.services.alert_service.get_reference_price_row",
                return_value=make_price_point("100.00"),
            ),
            patch(
                "backend.app.services.alert_service.get_prediction_state_for_asset",
                return_value=make_prediction("Up", up="67.00", down="12.00", flat="21.00"),
            ),
        ):
            trigger_result = evaluate_active_alerts(session)

        self.assertEqual(trigger_result.triggered_alerts, 1)
        self.assertFalse(alert.is_armed)

        with (
            patch(
                "backend.app.services.alert_service.get_recent_real_price_rows",
                return_value=[make_price_point("104.00"), make_price_point("103.00")],
            ),
            patch(
                "backend.app.services.alert_service.get_reference_price_row",
                return_value=make_price_point("100.00"),
            ),
            patch(
                "backend.app.services.alert_service.get_prediction_state_for_asset",
                return_value=make_prediction("Flat", up="55.00", down="20.00", flat="25.00"),
            ),
        ):
            rearm_result = evaluate_active_alerts(session)

        self.assertEqual(rearm_result.triggered_alerts, 0)
        self.assertEqual(rearm_result.alerts_rearmed, 1)
        self.assertTrue(alert.is_armed)

    def test_dm_failure_rolls_back_alert_state(self):
        alert = make_alert(
            alert_type=AlertType.TARGET_PRICE_HIT.value,
            direction=AlertDirection.ABOVE.value,
            target_price="110.00",
            is_active=False,
            is_armed=False,
            last_triggered_at=NOW,
        )
        session = FakeSession([alert])
        evaluation = AlertEvaluationResult(
            active_alerts_checked=1,
            triggered_alerts=1,
            target_alerts_deactivated=1,
            notifications=[
                TriggeredAlertNotification(
                    alert_id=alert.id,
                    discord_user_id="1234567890",
                    content="test",
                    previous_is_active=True,
                    previous_is_armed=True,
                    previous_last_observed_signal=None,
                    previous_last_triggered_at=None,
                )
            ],
        )

        with (
            patch(
                "backend.app.services.alert_service.evaluate_active_alerts",
                return_value=evaluation,
            ),
            patch(
                "backend.app.services.alert_service.send_discord_alert_notification",
                side_effect=RuntimeError("dm failure"),
            ),
            patch("backend.app.services.alert_service.logger.exception"),
        ):
            result = process_alert_notifications(session)

        self.assertEqual(result.dm_delivery_failures, 1)
        self.assertEqual(result.target_alerts_deactivated, 0)
        self.assertTrue(alert.is_active)
        self.assertTrue(alert.is_armed)
        self.assertIsNone(alert.last_triggered_at)
        self.assertTrue(session.commit_called)
