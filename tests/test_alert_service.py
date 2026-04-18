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
from backend.app.services.card_credibility_service import CredibilityIndicators
from backend.app.services.liquidity_service import AssetSignalSnapshot
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
        self.added_objects: list = []

    def scalars(self, _stmt):
        return FakeScalarResult(self.alerts)

    def flush(self):
        self.flush_called = True

    def commit(self):
        self.commit_called = True

    def rollback(self):
        self.rollback_called = True

    def add(self, obj) -> None:
        self.added_objects.append(obj)

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
            patch(
                "backend.app.services.alert_service.build_credibility_indicators",
                return_value=None,
            ),
            patch(
                "backend.app.services.alert_service.get_asset_signal_snapshots",
                return_value={
                    alert.asset_id: AssetSignalSnapshot(
                        asset_id=alert.asset_id,
                        sales_count_7d=4,
                        sales_count_30d=8,
                        days_since_last_sale=0,
                        last_real_sale_at=NOW,
                        history_depth=12,
                        source_count=1,
                        liquidity_score=82,
                        liquidity_label="High Liquidity",
                        price_move_magnitude=Decimal("10.00"),
                        alert_confidence=78,
                        alert_confidence_label="High Confidence",
                    )
                },
            ),
        ):
            result = evaluate_active_alerts(session)

        self.assertEqual(result.triggered_alerts, 1)
        self.assertEqual(result.price_movement_alerts_triggered, 1)
        self.assertFalse(alert.is_armed)
        self.assertIsNotNone(alert.last_triggered_at)
        self.assertTrue(session.flush_called)
        self.assertIn("Trigger: price_up_percent", result.notifications[0].content)
        self.assertIn("Liquidity: High Liquidity (82/100)", result.notifications[0].content)

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
                    user_id=alert.user_id,
                    asset_id=alert.asset_id,
                    asset_name=alert.asset.name,
                    alert_type=alert.alert_type,
                    discord_user_id="1234567890",
                    content="test",
                    triggered_at=NOW,
                    price_at_trigger=Decimal("110.00"),
                    reference_price=Decimal("100.00"),
                    percent_change=None,
                    currency="USD",
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


def _make_credibility(
    *,
    sample_size: int = 47,
    match_confidence: float | None = 0.94,
    confidence_status: str = "green",
) -> CredibilityIndicators:
    return CredibilityIndicators(
        sample_size=sample_size,
        data_age_hours=2.5,
        source_breakdown=None,
        match_confidence=match_confidence,
        data_age_label="Updated 2h ago",
        sample_size_label=f"Based on {sample_size} sales" if sample_size > 0 else "No sales data",
        confidence_status=confidence_status,
    )


class AlertEmbedCredibilityTests(TestCase):
    """Verify credibility enrichment in build_alert_notification_embed and evaluate_active_alerts."""

    def _price_up_embed(self, *, access_tier: str = "free", credibility: CredibilityIndicators | None = None) -> dict:
        alert = make_alert(
            alert_type=AlertType.PRICE_UP_THRESHOLD.value,
            direction=AlertDirection.ABOVE.value,
            threshold_percent="5.00",
        )
        return build_alert_notification_embed(
            alert,
            make_price_point("110.00"),
            None,
            previous_price=make_price_point("100.00"),
            credibility=credibility,
            access_tier=access_tier,
        )

    def _field_names(self, embed: dict) -> list[str]:
        return [f["name"] for f in embed["fields"]]

    def _field_values_joined(self, embed: dict) -> str:
        return " ".join(f["value"] for f in embed["fields"])

    def test_price_up_embed_includes_sample_size_when_available(self):
        embed = self._price_up_embed(credibility=_make_credibility(match_confidence=None), access_tier="pro")
        self.assertIn("Data quality", self._field_names(embed))
        self.assertIn("47", self._field_values_joined(embed))

    def test_price_up_embed_skips_sample_size_when_zero(self):
        embed = self._price_up_embed(
            credibility=_make_credibility(sample_size=0, match_confidence=None),
            access_tier="pro",
        )
        self.assertNotIn("Data quality", self._field_names(embed))

    def test_match_confidence_green_shows_checkmark(self):
        embed = self._price_up_embed(
            credibility=_make_credibility(match_confidence=0.94, confidence_status="green"),
            access_tier="pro",
        )
        values = self._field_values_joined(embed)
        self.assertIn("✅", values)
        self.assertIn("94%", values)

    def test_match_confidence_non_green_shows_warning(self):
        embed = self._price_up_embed(
            credibility=_make_credibility(match_confidence=0.72, confidence_status="yellow"),
            access_tier="pro",
        )
        values = self._field_values_joined(embed)
        self.assertIn("⚠️", values)
        self.assertIn("72%", values)

    def test_free_tier_embed_includes_pro_gate_nudge(self):
        embed = self._price_up_embed(credibility=_make_credibility(), access_tier="free")
        self.assertIn("Pro Only", self._field_values_joined(embed))

    def test_pro_tier_embed_has_no_pro_gate_nudge(self):
        embed = self._price_up_embed(credibility=_make_credibility(), access_tier="pro")
        self.assertNotIn("Pro Only", self._field_values_joined(embed))

    def test_embed_graceful_when_credibility_is_none(self):
        embed = self._price_up_embed(credibility=None, access_tier="free")
        self.assertIn("title", embed)
        self.assertNotIn("Data quality", self._field_names(embed))
        self.assertNotIn("Match confidence", self._field_names(embed))
        self.assertNotIn("Pro Only", self._field_values_joined(embed))

    def test_prediction_embed_not_enriched(self):
        alert = make_alert(
            alert_type=AlertType.PREDICT_SIGNAL_CHANGE.value,
            last_observed_signal="Flat",
        )
        session = FakeSession([alert])
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
            patch(
                "backend.app.services.alert_service.build_credibility_indicators",
            ) as mock_cred,
        ):
            result = evaluate_active_alerts(session)

        self.assertEqual(result.triggered_alerts, 1)
        mock_cred.assert_not_called()

    def test_credibility_not_fetched_twice_for_same_asset(self):
        alert1 = make_alert(
            alert_type=AlertType.PRICE_UP_THRESHOLD.value,
            threshold_percent="5.00",
        )
        alert2 = make_alert(
            alert_type=AlertType.PRICE_UP_THRESHOLD.value,
            threshold_percent="3.00",
        )
        alert2.asset_id = alert1.asset_id
        alert2.asset = alert1.asset
        alert1.user.access_tier = "free"
        alert2.user.access_tier = "free"

        session = FakeSession([alert1, alert2])
        with (
            patch(
                "backend.app.services.alert_service.get_recent_real_price_rows",
                return_value=[make_price_point("110.00"), make_price_point("100.00")],
            ),
            patch(
                "backend.app.services.alert_service.get_reference_price_row",
                return_value=make_price_point("95.00"),
            ),
            patch(
                "backend.app.services.alert_service.get_asset_signal_snapshots",
                return_value={},
            ),
            patch(
                "backend.app.services.alert_service.build_credibility_indicators",
                return_value=_make_credibility(),
            ) as mock_cred,
        ):
            result = evaluate_active_alerts(session)

        self.assertEqual(result.triggered_alerts, 2)
        self.assertEqual(mock_cred.call_count, 1)
