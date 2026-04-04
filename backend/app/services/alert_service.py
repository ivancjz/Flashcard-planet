from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.app.core.config import get_settings
from backend.app.core.price_sources import get_active_price_source_filter
from backend.app.models.alert import Alert
from backend.app.models.enums import AlertDirection, AlertType
from backend.app.models.price_history import PriceHistory
from backend.app.models.user import User
from backend.app.schemas.alert import AlertItemResponse
from backend.app.services.liquidity_service import AssetSignalSnapshot, get_asset_signal_snapshots
from backend.app.services.price_service import PredictionComputation, get_prediction_state_for_asset

logger = logging.getLogger(__name__)

DISCORD_API_BASE_URL = "https://discord.com/api/v10"
PRICE_MOVEMENT_ALERT_TYPES = {
    AlertType.PRICE_UP_THRESHOLD.value,
    AlertType.PRICE_DOWN_THRESHOLD.value,
}
PREDICTION_ALERT_TYPES = {
    AlertType.PREDICT_SIGNAL_CHANGE.value,
    AlertType.PREDICT_UP_PROBABILITY_ABOVE.value,
    AlertType.PREDICT_DOWN_PROBABILITY_ABOVE.value,
}


@dataclass
class PricePoint:
    price: Decimal
    currency: str
    source: str
    captured_at: datetime


@dataclass
class TriggeredAlertNotification:
    alert_id: Any
    discord_user_id: str
    content: str
    previous_is_active: bool
    previous_is_armed: bool
    previous_last_observed_signal: str | None
    previous_last_triggered_at: datetime | None


@dataclass
class AlertEvaluationResult:
    active_alerts_checked: int = 0
    triggered_alerts: int = 0
    prediction_alerts_triggered: int = 0
    price_movement_alerts_triggered: int = 0
    alerts_rearmed: int = 0
    target_alerts_deactivated: int = 0
    notifications: list[TriggeredAlertNotification] = field(default_factory=list)


@dataclass
class AlertProcessingResult:
    active_alerts_checked: int = 0
    triggered_alerts: int = 0
    prediction_alerts_triggered: int = 0
    price_movement_alerts_triggered: int = 0
    alerts_rearmed: int = 0
    notifications_sent: int = 0
    dm_delivery_failures: int = 0
    target_alerts_deactivated: int = 0


def get_recent_real_price_rows(db: Session, asset_id, *, limit: int = 2) -> list[PricePoint]:
    source_filter = get_active_price_source_filter(db)
    rows = db.execute(
        select(
            PriceHistory.price,
            PriceHistory.currency,
            PriceHistory.source,
            PriceHistory.captured_at,
        )
        .where(
            PriceHistory.asset_id == asset_id,
            source_filter,
        )
        .order_by(PriceHistory.captured_at.desc())
        .limit(limit)
    ).all()
    return [
        PricePoint(
            price=Decimal(row.price),
            currency=row.currency,
            source=row.source,
            captured_at=row.captured_at,
        )
        for row in rows
    ]


def get_reference_price_row(db: Session, asset_id, created_at: datetime) -> PricePoint | None:
    source_filter = get_active_price_source_filter(db)
    row = db.execute(
        select(
            PriceHistory.price,
            PriceHistory.currency,
            PriceHistory.source,
            PriceHistory.captured_at,
        )
        .where(
            PriceHistory.asset_id == asset_id,
            source_filter,
            PriceHistory.captured_at <= created_at,
        )
        .order_by(PriceHistory.captured_at.desc())
        .limit(1)
    ).first()
    if row is None:
        row = db.execute(
            select(
                PriceHistory.price,
                PriceHistory.currency,
                PriceHistory.source,
                PriceHistory.captured_at,
            )
            .where(
                PriceHistory.asset_id == asset_id,
                source_filter,
            )
            .order_by(PriceHistory.captured_at.asc())
            .limit(1)
        ).first()
    if row is None:
        return None
    return PricePoint(
        price=Decimal(row.price),
        currency=row.currency,
        source=row.source,
        captured_at=row.captured_at,
    )


def get_probability_value(alert: Alert, prediction_state: PredictionComputation) -> Decimal | None:
    if alert.alert_type == AlertType.PREDICT_UP_PROBABILITY_ABOVE.value:
        return prediction_state.up_probability
    if alert.alert_type == AlertType.PREDICT_DOWN_PROBABILITY_ABOVE.value:
        return prediction_state.down_probability
    return None


def format_probability_triplet(prediction_state: PredictionComputation) -> str:
    if (
        prediction_state.up_probability is None
        or prediction_state.down_probability is None
        or prediction_state.flat_probability is None
    ):
        return "Probabilities unavailable"
    return (
        f"Up {prediction_state.up_probability}% | "
        f"Down {prediction_state.down_probability}% | "
        f"Flat {prediction_state.flat_probability}%"
    )


def list_active_alerts(db: Session, discord_user_id: str) -> list[AlertItemResponse]:
    stmt = (
        select(Alert)
        .options(
            selectinload(Alert.asset),
            selectinload(Alert.user),
        )
        .join(User, User.id == Alert.user_id)
        .where(
            User.discord_user_id == discord_user_id,
            Alert.is_active.is_(True),
        )
        .order_by(Alert.created_at.desc())
    )
    alerts = db.scalars(stmt).all()

    latest_cache: dict[Any, PricePoint | None] = {}
    prediction_cache: dict[Any, PredictionComputation] = {}
    items: list[AlertItemResponse] = []
    for alert in alerts:
        if alert.asset_id not in latest_cache:
            latest_rows = get_recent_real_price_rows(db, alert.asset_id, limit=1)
            latest_cache[alert.asset_id] = latest_rows[0] if latest_rows else None

        latest_row = latest_cache[alert.asset_id]
        prediction_state: PredictionComputation | None = None
        if alert.alert_type in PREDICTION_ALERT_TYPES:
            if alert.asset_id not in prediction_cache:
                prediction_cache[alert.asset_id] = get_prediction_state_for_asset(db, alert.asset_id)
            prediction_state = prediction_cache[alert.asset_id]

        items.append(
            AlertItemResponse(
                alert_id=alert.id,
                asset_id=alert.asset.id,
                asset_name=alert.asset.name,
                category=alert.asset.category,
                alert_type=alert.alert_type,
                direction=alert.direction,
                threshold_percent=alert.threshold_percent,
                target_price=alert.target_price,
                latest_price=latest_row.price if latest_row else None,
                currency=latest_row.currency if latest_row else None,
                is_active=alert.is_active,
                is_armed=alert.is_armed,
                last_observed_signal=alert.last_observed_signal,
                current_prediction=prediction_state.prediction if prediction_state else None,
                up_probability=prediction_state.up_probability if prediction_state else None,
                down_probability=prediction_state.down_probability if prediction_state else None,
                flat_probability=prediction_state.flat_probability if prediction_state else None,
                last_triggered_at=alert.last_triggered_at,
                created_at=alert.created_at,
            )
        )

    return items


def build_alert_notification_content(
    alert: Alert,
    current_price: PricePoint,
    reference_price: PricePoint | None,
    *,
    previous_price: PricePoint | None = None,
    prediction_state: PredictionComputation | None = None,
    previous_signal: str | None = None,
    signal_snapshot: AssetSignalSnapshot | None = None,
) -> str:
    asset_name = alert.asset.name
    current_price_text = f"{current_price.price:.2f} {current_price.currency}"
    captured_at_text = current_price.captured_at.isoformat()

    if alert.alert_type == AlertType.TARGET_PRICE_HIT.value and alert.target_price is not None:
        return (
            "Flashcard Planet push alert\n"
            f"Card: {asset_name}\n"
            "Trigger: target_price\n"
            f"Target: {alert.target_price:.2f} {current_price.currency}\n"
            f"Current price: {current_price_text}\n"
            f"Timestamp: {captured_at_text}"
        )

    if alert.alert_type in (
        AlertType.PRICE_UP_THRESHOLD.value,
        AlertType.PRICE_DOWN_THRESHOLD.value,
    ):
        movement_reference = previous_price or reference_price
        if movement_reference is None or movement_reference.price == 0 or alert.threshold_percent is None:
            return (
                "Flashcard Planet push alert\n"
                f"Card: {asset_name}\n"
                f"Trigger: {alert.alert_type}\n"
                f"Current price: {current_price_text}\n"
                f"Timestamp: {captured_at_text}"
            )

        percent_change = ((current_price.price - movement_reference.price) / movement_reference.price) * Decimal("100")
        direction_label = "price_up_percent" if alert.alert_type == AlertType.PRICE_UP_THRESHOLD.value else "price_down_percent"
        message = (
            "Flashcard Planet push alert\n"
            f"Card: {asset_name}\n"
            f"Trigger: {direction_label}\n"
            f"Current price: {current_price_text}\n"
            f"Reference price: {movement_reference.price:.2f} {movement_reference.currency}\n"
            f"Percent move: {percent_change:+.2f}%\n"
            f"Threshold: {alert.threshold_percent:.2f}%\n"
            f"Timestamp: {captured_at_text}"
        )
        if signal_snapshot is not None:
            confidence_text = (
                f"{signal_snapshot.alert_confidence_label} ({signal_snapshot.alert_confidence}/100)"
                if signal_snapshot.alert_confidence is not None
                else "Not set"
            )
            message += (
                f"\nLiquidity: {signal_snapshot.liquidity_label} ({signal_snapshot.liquidity_score}/100)\n"
                f"Alert confidence: {confidence_text}"
            )
        return message

    if alert.alert_type == AlertType.PREDICT_SIGNAL_CHANGE.value and prediction_state is not None:
        return (
            "Flashcard Planet push alert\n"
            f"Card: {asset_name}\n"
            "Trigger: predict_signal_change\n"
            f"Current price: {current_price_text}\n"
            f"Prediction change: {previous_signal or 'Unknown'} -> {prediction_state.prediction}\n"
            f"Probabilities: {format_probability_triplet(prediction_state)}\n"
            f"Timestamp: {captured_at_text}"
        )

    if alert.alert_type in (
        AlertType.PREDICT_UP_PROBABILITY_ABOVE.value,
        AlertType.PREDICT_DOWN_PROBABILITY_ABOVE.value,
    ) and prediction_state is not None:
        probability_value = get_probability_value(alert, prediction_state)
        trigger_label = (
            "predict_up_probability_above"
            if alert.alert_type == AlertType.PREDICT_UP_PROBABILITY_ABOVE.value
            else "predict_down_probability_above"
        )
        probability_text = f"{probability_value:.2f}%" if probability_value is not None else "Unknown"
        threshold_text = f"{alert.threshold_percent:.2f}%" if alert.threshold_percent is not None else "Unknown"
        return (
            "Flashcard Planet push alert\n"
            f"Card: {asset_name}\n"
            f"Trigger: {trigger_label}\n"
            f"Current price: {current_price_text}\n"
            f"Prediction: {prediction_state.prediction}\n"
            f"Crossed probability: {probability_text} above {threshold_text}\n"
            f"Probabilities: {format_probability_triplet(prediction_state)}\n"
            f"Timestamp: {captured_at_text}"
        )

    return (
        "Flashcard Planet push alert\n"
        f"Card: {asset_name}\n"
        f"Trigger: {alert.alert_type}\n"
        f"Current price: {current_price_text}\n"
        f"Timestamp: {captured_at_text}"
    )


def is_target_crossed(
    target_price: Decimal,
    current_price: Decimal,
    previous_price: Decimal | None,
    reference_price: Decimal | None,
) -> bool:
    if reference_price is None:
        return False

    direction = (
        AlertDirection.ABOVE.value
        if reference_price < target_price
        else AlertDirection.BELOW.value
    )
    if direction == AlertDirection.ABOVE.value:
        if current_price < target_price:
            return False
        if previous_price is not None:
            return previous_price < target_price
        return reference_price < target_price

    if current_price > target_price:
        return False
    if previous_price is not None:
        return previous_price > target_price
    return reference_price > target_price


def is_threshold_crossed(
    alert: Alert,
    current_price: Decimal,
    previous_price: Decimal | None,
) -> bool:
    if previous_price is None or previous_price == 0 or alert.threshold_percent is None:
        return False

    current_change = ((current_price - previous_price) / previous_price) * Decimal("100")
    if alert.alert_type == AlertType.PRICE_UP_THRESHOLD.value:
        return current_change >= alert.threshold_percent

    if alert.alert_type == AlertType.PRICE_DOWN_THRESHOLD.value:
        target_change = -alert.threshold_percent
        return current_change <= target_change

    return False


def should_rearm_threshold_alert(
    alert: Alert,
    current_price: Decimal,
    previous_price: Decimal | None,
) -> bool:
    if previous_price is None or previous_price == 0 or alert.threshold_percent is None:
        return False

    current_change = ((current_price - previous_price) / previous_price) * Decimal("100")
    if alert.alert_type == AlertType.PRICE_UP_THRESHOLD.value:
        return current_change < alert.threshold_percent

    if alert.alert_type == AlertType.PRICE_DOWN_THRESHOLD.value:
        return current_change > -alert.threshold_percent

    return False


def should_trigger_prediction_threshold(alert: Alert, prediction_state: PredictionComputation) -> bool:
    current_probability = get_probability_value(alert, prediction_state)
    if current_probability is None or alert.threshold_percent is None:
        return False
    return current_probability >= alert.threshold_percent


def should_rearm_prediction_threshold(alert: Alert, prediction_state: PredictionComputation) -> bool:
    current_probability = get_probability_value(alert, prediction_state)
    if current_probability is None or alert.threshold_percent is None:
        return False
    return current_probability < alert.threshold_percent


def evaluate_active_alerts(db: Session) -> AlertEvaluationResult:
    stmt = (
        select(Alert)
        .options(
            selectinload(Alert.asset),
            selectinload(Alert.user),
        )
        .where(Alert.is_active.is_(True))
        .order_by(Alert.created_at.asc())
    )
    alerts = db.scalars(stmt).all()

    latest_cache: dict[Any, list[PricePoint]] = {}
    reference_cache: dict[tuple[Any, datetime], PricePoint | None] = {}
    prediction_cache: dict[Any, PredictionComputation] = {}
    result = AlertEvaluationResult(active_alerts_checked=len(alerts))
    triggered_at = datetime.now(UTC).replace(microsecond=0)

    for alert in alerts:
        previous_is_active = alert.is_active
        previous_is_armed = alert.is_armed
        previous_last_observed_signal = alert.last_observed_signal
        previous_last_triggered_at = alert.last_triggered_at

        if alert.asset_id not in latest_cache:
            latest_cache[alert.asset_id] = get_recent_real_price_rows(db, alert.asset_id, limit=2)

        latest_rows = latest_cache[alert.asset_id]
        if not latest_rows:
            continue

        current_row = latest_rows[0]
        previous_row = latest_rows[1] if len(latest_rows) > 1 else None

        reference_key = (alert.asset_id, alert.created_at)
        if reference_key not in reference_cache:
            reference_cache[reference_key] = get_reference_price_row(db, alert.asset_id, alert.created_at)
        reference_row = reference_cache[reference_key]

        prediction_state: PredictionComputation | None = None
        if alert.alert_type in PREDICTION_ALERT_TYPES:
            if alert.asset_id not in prediction_cache:
                prediction_cache[alert.asset_id] = get_prediction_state_for_asset(db, alert.asset_id)
            prediction_state = prediction_cache[alert.asset_id]

        triggered = False
        previous_signal: str | None = None
        signal_snapshot: AssetSignalSnapshot | None = None
        if alert.alert_type == AlertType.TARGET_PRICE_HIT.value and alert.target_price is not None:
            triggered = is_target_crossed(
                alert.target_price,
                current_row.price,
                previous_row.price if previous_row else None,
                reference_row.price if reference_row else None,
            )
        elif alert.alert_type in (
            AlertType.PRICE_UP_THRESHOLD.value,
            AlertType.PRICE_DOWN_THRESHOLD.value,
        ):
            is_crossed = is_threshold_crossed(
                alert,
                current_row.price,
                previous_row.price if previous_row else None,
            )
            if is_crossed and alert.is_armed:
                triggered = True
                alert.is_armed = False
            elif should_rearm_threshold_alert(
                alert,
                current_row.price,
                previous_row.price if previous_row else None,
            ):
                if not alert.is_armed:
                    result.alerts_rearmed += 1
                alert.is_armed = True
            if (
                triggered
                and previous_row is not None
                and previous_row.price != 0
            ):
                percent_change = (
                    (current_row.price - previous_row.price) / previous_row.price
                ) * Decimal("100")
                signal_snapshot = get_asset_signal_snapshots(
                    db,
                    [alert.asset_id],
                    percent_changes_by_asset={alert.asset_id: percent_change},
                ).get(alert.asset_id)
        elif (
            alert.alert_type == AlertType.PREDICT_SIGNAL_CHANGE.value
            and prediction_state is not None
            and prediction_state.prediction != "Not enough data"
        ):
            if alert.last_observed_signal is None:
                alert.last_observed_signal = prediction_state.prediction
            elif prediction_state.prediction != alert.last_observed_signal:
                previous_signal = alert.last_observed_signal
                triggered = True
                alert.last_observed_signal = prediction_state.prediction
        elif (
            alert.alert_type in (
                AlertType.PREDICT_UP_PROBABILITY_ABOVE.value,
                AlertType.PREDICT_DOWN_PROBABILITY_ABOVE.value,
            )
            and prediction_state is not None
        ):
            is_crossed = should_trigger_prediction_threshold(alert, prediction_state)
            if is_crossed and alert.is_armed:
                triggered = True
                alert.is_armed = False
            elif should_rearm_prediction_threshold(alert, prediction_state):
                if not alert.is_armed:
                    result.alerts_rearmed += 1
                alert.is_armed = True

        if not triggered:
            continue

        result.notifications.append(
            TriggeredAlertNotification(
                alert_id=alert.id,
                discord_user_id=alert.user.discord_user_id,
                content=build_alert_notification_content(
                    alert,
                    current_row,
                    reference_row,
                    previous_price=previous_row,
                    prediction_state=prediction_state,
                    previous_signal=previous_signal,
                    signal_snapshot=signal_snapshot,
                ),
                previous_is_active=previous_is_active,
                previous_is_armed=previous_is_armed,
                previous_last_observed_signal=previous_last_observed_signal,
                previous_last_triggered_at=previous_last_triggered_at,
            )
        )
        alert.last_triggered_at = triggered_at
        result.triggered_alerts += 1
        if alert.alert_type in PREDICTION_ALERT_TYPES:
            result.prediction_alerts_triggered += 1
        elif alert.alert_type in PRICE_MOVEMENT_ALERT_TYPES:
            result.price_movement_alerts_triggered += 1
        if alert.alert_type == AlertType.TARGET_PRICE_HIT.value:
            alert.is_active = False
            result.target_alerts_deactivated += 1

    db.flush()
    return result


def send_discord_alert_notification(discord_user_id: str, content: str) -> None:
    settings = get_settings()
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is required for alert notifications.")

    headers = {
        "Authorization": f"Bot {settings.bot_token}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=10.0, headers=headers) as client:
        channel_response = client.post(
            f"{DISCORD_API_BASE_URL}/users/@me/channels",
            json={"recipient_id": discord_user_id},
        )
        channel_response.raise_for_status()
        channel_id = channel_response.json()["id"]

        message_response = client.post(
            f"{DISCORD_API_BASE_URL}/channels/{channel_id}/messages",
            json={"content": content},
        )
        message_response.raise_for_status()


def process_alert_notifications(db: Session) -> AlertProcessingResult:
    evaluation = evaluate_active_alerts(db)
    result = AlertProcessingResult(
        active_alerts_checked=evaluation.active_alerts_checked,
        triggered_alerts=evaluation.triggered_alerts,
        prediction_alerts_triggered=evaluation.prediction_alerts_triggered,
        price_movement_alerts_triggered=evaluation.price_movement_alerts_triggered,
        alerts_rearmed=evaluation.alerts_rearmed,
        target_alerts_deactivated=evaluation.target_alerts_deactivated,
    )
    if not evaluation.notifications:
        db.commit()
        return result

    for notification in evaluation.notifications:
        try:
            send_discord_alert_notification(notification.discord_user_id, notification.content)
        except Exception:
            alert = db.get(Alert, notification.alert_id)
            if alert is not None:
                alert.is_active = notification.previous_is_active
                alert.is_armed = notification.previous_is_armed
                alert.last_observed_signal = notification.previous_last_observed_signal
                alert.last_triggered_at = notification.previous_last_triggered_at
                if alert.alert_type == AlertType.TARGET_PRICE_HIT.value:
                    result.target_alerts_deactivated = max(0, result.target_alerts_deactivated - 1)
            logger.exception(
                "Failed to send Discord alert notification for alert %s and user %s.",
                notification.alert_id,
                notification.discord_user_id,
            )
            result.dm_delivery_failures += 1
            continue
        result.notifications_sent += 1

    db.commit()
    return result
