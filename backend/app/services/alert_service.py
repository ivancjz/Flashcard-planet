from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from backend.app.core.config import get_settings
from backend.app.core.permissions import Feature, alert_limit, can, get_pro_gate_config
from backend.app.core.price_sources import get_active_price_source_filter
from backend.app.models.alert import Alert
from backend.app.models.alert_history import AlertHistory
from backend.app.models.asset import Asset
from backend.app.models.enums import AlertDirection, AlertType
from backend.app.models.price_history import PriceHistory
from backend.app.models.user import User
from backend.app.schemas.alert import AlertCreateRequest, AlertHistoryItemResponse, AlertItemResponse
from backend.app.services.card_credibility_service import CredibilityIndicators, build_credibility_indicators  # boundary-ok: see docs/plan-v3.md §2 ST-1
from backend.app.services.liquidity_service import AssetSignalSnapshot, get_asset_signal_snapshots
from backend.app.services.price_service import PredictionComputation, get_prediction_state_for_asset
from backend.app.services.watchlist_service import get_or_create_user

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

# Alert types that use threshold_percent as a trigger condition — Pro-only.
PCT_TRIGGER_TYPES: frozenset[str] = frozenset({
    AlertType.PRICE_UP_THRESHOLD.value,
    AlertType.PRICE_DOWN_THRESHOLD.value,
    AlertType.PREDICT_UP_PROBABILITY_ABOVE.value,
    AlertType.PREDICT_DOWN_PROBABILITY_ABOVE.value,
})

# Alert types available to free-tier users.
FREE_ALERT_TYPES: frozenset[str] = frozenset({
    AlertType.TARGET_PRICE_HIT.value,
    AlertType.PREDICT_SIGNAL_CHANGE.value,
})

_TIER_ERROR_PREFIX = "[tier]"


def is_tier_error(msg: str) -> bool:
    """Return True when a ValueError message originated from a tier gate."""
    return msg.startswith(_TIER_ERROR_PREFIX)


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
    user_id: Any | None = None
    asset_id: Any | None = None
    asset_name: str = ""
    alert_type: str = ""
    triggered_at: datetime | None = None
    price_at_trigger: Decimal | None = None
    reference_price: Decimal | None = None
    percent_change: Decimal | None = None
    currency: str | None = None
    embed: dict | None = None


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


def create_alert(db: Session, payload: AlertCreateRequest) -> Alert:
    user = get_or_create_user(db, payload.discord_user_id)

    # Gate 1: pct-trigger alert types are Pro-only.
    if payload.alert_type in PCT_TRIGGER_TYPES and not can(user.access_tier, Feature.ALERTS_PCT_TRIGGER):
        raise ValueError(
            f"{_TIER_ERROR_PREFIX} Alert type '{payload.alert_type}' requires Pro. "
            "Upgrade to unlock percentage-trigger alerts."
        )

    # Gate 2: free-tier alert count limit.
    limit = alert_limit(user.access_tier)
    if limit is not None:
        current_count: int = db.scalar(
            select(func.count(Alert.id)).where(
                Alert.user_id == user.id,
                Alert.is_active.is_(True),
            )
        ) or 0
        if current_count >= limit:
            raise ValueError(
                f"{_TIER_ERROR_PREFIX} Alert limit reached ({limit} active alerts). "
                "Upgrade to Pro for unlimited alerts."
            )

    asset = db.scalar(
        select(Asset)
        .where(func.lower(Asset.name).contains(func.lower(payload.asset_name)))
        .limit(1)
    )
    if asset is None:
        raise ValueError(f"No asset found matching '{payload.asset_name}'")

    alert = Alert(
        user_id=user.id,
        asset_id=asset.id,
        alert_type=payload.alert_type,
        threshold_percent=payload.threshold_percent,
        target_price=payload.target_price,
        direction=payload.direction,
        is_active=True,
        is_armed=True,
    )
    db.add(alert)
    db.flush()
    return alert


def delete_alert(db: Session, alert_id: UUID) -> bool:
    alert = db.get(Alert, alert_id)
    if alert is None:
        return False
    db.delete(alert)
    return True


def deactivate_alert(db: Session, alert_id: UUID) -> bool:
    alert = db.get(Alert, alert_id)
    if alert is None:
        return False
    alert.is_active = False
    return True


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
                game=alert.asset.game,
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


def list_alert_history(
    db: Session,
    discord_user_id: str,
    *,
    limit: int = 20,
    asset_name: str | None = None,
) -> list[AlertHistoryItemResponse]:
    stmt = (
        select(AlertHistory)
        .join(User, User.id == AlertHistory.user_id)
        .where(User.discord_user_id == discord_user_id)
    )
    if asset_name:
        stmt = stmt.where(AlertHistory.asset_name.ilike(f"%{asset_name}%"))
    stmt = stmt.order_by(AlertHistory.triggered_at.desc()).limit(limit)
    rows = db.scalars(stmt).all()
    return [
        AlertHistoryItemResponse(
            history_id=row.id,
            alert_id=row.alert_id,
            asset_id=row.asset_id,
            asset_name=row.asset_name,
            alert_type=row.alert_type,
            triggered_at=row.triggered_at,
            price_at_trigger=row.price_at_trigger,
            reference_price=row.reference_price,
            percent_change=row.percent_change,
            currency=row.currency,
            delivery_status=row.delivery_status,
            notification_content=row.notification_content,
        )
        for row in rows
    ]


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


_EMBED_COLOR_GREEN = 0x57F287   # price up / predict up
_EMBED_COLOR_RED = 0xED4245     # price down / predict down
_EMBED_COLOR_GOLD = 0xFEE75C    # target hit
_EMBED_COLOR_BLURPLE = 0x5865F2 # signal change / default


def _embed_field(name: str, value: str, *, inline: bool = True) -> dict:
    return {"name": name, "value": value or "—", "inline": inline}


def _credibility_fields(credibility: CredibilityIndicators | None, access_tier: str) -> list[dict]:
    """Return embed fields for data-quality indicators and a pro-gate nudge for free-tier users."""
    if credibility is None:
        return []
    result: list[dict] = []
    if credibility.sample_size > 0:
        result.append(_embed_field("Data quality", credibility.sample_size_label, inline=False))
    if credibility.match_confidence is not None:
        pct = int(round(credibility.match_confidence * 100))
        icon = "✅" if credibility.confidence_status == "green" else "⚠️"
        result.append(_embed_field("Match confidence", f"{icon} {pct}%", inline=False))
    bot_cfg = get_pro_gate_config("price_history", access_tier).to_bot_config()
    if bot_cfg:
        result.append(_embed_field("🔒 Pro feature", bot_cfg["locked_message"], inline=False))
    return result


def build_alert_notification_embed(
    alert: Alert,
    current_price: PricePoint,
    reference_price: PricePoint | None,
    *,
    previous_price: PricePoint | None = None,
    prediction_state: PredictionComputation | None = None,
    previous_signal: str | None = None,
    signal_snapshot: AssetSignalSnapshot | None = None,
    credibility: CredibilityIndicators | None = None,
    access_tier: str = "free",
) -> dict:
    """Return a Discord embed dict (matches the Discord API embeds array element)."""
    asset_name = alert.asset.name
    set_name = getattr(alert.asset, "set_name", None)
    currency = current_price.currency
    ts = current_price.captured_at.isoformat()

    def price_str(p: Decimal) -> str:
        return f"{p:.2f} {currency}"

    if alert.alert_type == AlertType.TARGET_PRICE_HIT.value and alert.target_price is not None:
        fields = [
            _embed_field("Card", asset_name),
        ]
        if set_name:
            fields.append(_embed_field("Set", set_name))
        fields += [
            _embed_field("Target", f"{alert.target_price:.2f} {currency}"),
            _embed_field("Current price", price_str(current_price.price)),
        ]
        fields.extend(_credibility_fields(credibility, access_tier))
        return {
            "title": "🎯 Target Price Reached",
            "color": _EMBED_COLOR_GOLD,
            "fields": fields,
            "footer": {"text": "Flashcard Planet · one-shot alert — now deactivated"},
            "timestamp": ts,
        }

    if alert.alert_type in (AlertType.PRICE_UP_THRESHOLD.value, AlertType.PRICE_DOWN_THRESHOLD.value):
        is_up = alert.alert_type == AlertType.PRICE_UP_THRESHOLD.value
        movement_reference = previous_price or reference_price
        fields = [
            _embed_field("Card", asset_name),
        ]
        if set_name:
            fields.append(_embed_field("Set", set_name))
        fields.append(_embed_field("Current price", price_str(current_price.price)))
        if movement_reference is not None and movement_reference.price != 0:
            pct = ((current_price.price - movement_reference.price) / movement_reference.price) * Decimal("100")
            sign = "+" if pct >= 0 else ""
            fields += [
                _embed_field("Reference price", price_str(movement_reference.price)),
                _embed_field("Move", f"{sign}{pct:.2f}%"),
            ]
        if alert.threshold_percent is not None:
            fields.append(_embed_field("Threshold", f"{alert.threshold_percent:.2f}%"))
        if signal_snapshot is not None:
            if signal_snapshot.liquidity_label:
                liq = f"{signal_snapshot.liquidity_label} ({signal_snapshot.liquidity_score}/100)"
                fields.append(_embed_field("Liquidity", liq, inline=False))
            if signal_snapshot.alert_confidence is not None:
                conf = f"{signal_snapshot.alert_confidence_label} ({signal_snapshot.alert_confidence}/100)"
                fields.append(_embed_field("Confidence", conf, inline=False))
        fields.extend(_credibility_fields(credibility, access_tier))
        return {
            "title": "📈 Price Up Alert" if is_up else "📉 Price Down Alert",
            "color": _EMBED_COLOR_GREEN if is_up else _EMBED_COLOR_RED,
            "fields": fields,
            "footer": {"text": "Flashcard Planet · alert will rearm after move reverses"},
            "timestamp": ts,
        }

    if alert.alert_type == AlertType.PREDICT_SIGNAL_CHANGE.value and prediction_state is not None:
        fields = [
            _embed_field("Card", asset_name),
        ]
        if set_name:
            fields.append(_embed_field("Set", set_name))
        fields += [
            _embed_field("Signal", f"{previous_signal or '—'} → {prediction_state.prediction}", inline=False),
            _embed_field("Current price", price_str(current_price.price)),
        ]
        if prediction_state.up_probability is not None:
            fields.append(
                _embed_field(
                    "Probabilities",
                    f"Up {prediction_state.up_probability}% · Down {prediction_state.down_probability}% · Flat {prediction_state.flat_probability}%",
                    inline=False,
                )
            )
        return {
            "title": "🔮 Prediction Signal Changed",
            "color": _EMBED_COLOR_BLURPLE,
            "fields": fields,
            "footer": {"text": "Flashcard Planet · prediction alert"},
            "timestamp": ts,
        }

    if alert.alert_type in (
        AlertType.PREDICT_UP_PROBABILITY_ABOVE.value,
        AlertType.PREDICT_DOWN_PROBABILITY_ABOVE.value,
    ) and prediction_state is not None:
        is_up_prob = alert.alert_type == AlertType.PREDICT_UP_PROBABILITY_ABOVE.value
        probability_value = get_probability_value(alert, prediction_state)
        fields = [
            _embed_field("Card", asset_name),
        ]
        if set_name:
            fields.append(_embed_field("Set", set_name))
        fields += [
            _embed_field("Current price", price_str(current_price.price)),
            _embed_field("Prediction", prediction_state.prediction),
        ]
        if probability_value is not None:
            label = "Up probability" if is_up_prob else "Down probability"
            fields.append(_embed_field(label, f"{probability_value:.2f}%"))
        if alert.threshold_percent is not None:
            fields.append(_embed_field("Threshold", f"{alert.threshold_percent:.2f}%"))
        if prediction_state.up_probability is not None:
            fields.append(
                _embed_field(
                    "All probabilities",
                    f"Up {prediction_state.up_probability}% · Down {prediction_state.down_probability}% · Flat {prediction_state.flat_probability}%",
                    inline=False,
                )
            )
        return {
            "title": "📊 Prediction Probability Alert",
            "color": _EMBED_COLOR_GREEN if is_up_prob else _EMBED_COLOR_RED,
            "fields": fields,
            "footer": {"text": "Flashcard Planet · alert will rearm after probability drops"},
            "timestamp": ts,
        }

    # Fallback for unknown alert types
    return {
        "title": "🔔 Flashcard Planet Alert",
        "color": _EMBED_COLOR_BLURPLE,
        "fields": [
            _embed_field("Card", asset_name),
            _embed_field("Type", alert.alert_type),
            _embed_field("Current price", price_str(current_price.price)),
        ],
        "footer": {"text": "Flashcard Planet"},
        "timestamp": ts,
    }


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
    credibility_cache: dict[tuple[Any, str], CredibilityIndicators] = {}
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

        credibility: CredibilityIndicators | None = None
        if alert.alert_type in PRICE_MOVEMENT_ALERT_TYPES or alert.alert_type == AlertType.TARGET_PRICE_HIT.value:
            cred_key = (alert.asset_id, alert.user.access_tier)
            if cred_key not in credibility_cache:
                credibility_cache[cred_key] = build_credibility_indicators(  # boundary-ok: see docs/plan-v3.md §2 ST-1
                    db, asset_id=alert.asset_id, access_tier=alert.user.access_tier
                )
            credibility = credibility_cache[cred_key]

        # Compute percent_change for history record (price movement alerts only).
        _history_percent_change: Decimal | None = None
        _history_reference_price: Decimal | None = None
        if alert.alert_type in PRICE_MOVEMENT_ALERT_TYPES and previous_row is not None and previous_row.price != 0:
            _history_percent_change = ((current_row.price - previous_row.price) / previous_row.price) * Decimal("100")
            _history_reference_price = previous_row.price
        elif reference_row is not None:
            _history_reference_price = reference_row.price

        _shared_kwargs = dict(
            alert=alert,
            current_price=current_row,
            reference_price=reference_row,
            previous_price=previous_row,
            prediction_state=prediction_state,
            previous_signal=previous_signal,
            signal_snapshot=signal_snapshot,
        )
        result.notifications.append(
            TriggeredAlertNotification(
                alert_id=alert.id,
                user_id=alert.user_id,
                asset_id=alert.asset_id,
                asset_name=alert.asset.name,
                alert_type=alert.alert_type,
                discord_user_id=alert.user.discord_user_id,
                content=build_alert_notification_content(**_shared_kwargs),
                embed=build_alert_notification_embed(
                    **_shared_kwargs,
                    credibility=credibility,
                    access_tier=alert.user.access_tier,
                ),
                triggered_at=triggered_at,
                price_at_trigger=current_row.price,
                reference_price=_history_reference_price,
                percent_change=_history_percent_change,
                currency=current_row.currency,
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


def send_discord_alert_notification(
    discord_user_id: str,
    content: str,
    *,
    embed: dict | None = None,
) -> None:
    """Send a Discord DM alert to a user.

    If an embed dict is supplied it is sent as a rich embed message.
    The plain-text content is included as a fallback for clients that
    do not render embeds and is stored in alert_history regardless.
    """
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

        payload: dict = {}
        if embed is not None:
            payload["embeds"] = [embed]
        else:
            payload["content"] = content

        message_response = client.post(
            f"{DISCORD_API_BASE_URL}/channels/{channel_id}/messages",
            json=payload,
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
        delivery_status = "sent"
        try:
            send_discord_alert_notification(
                notification.discord_user_id,
                notification.content,
                embed=notification.embed,
            )
        except Exception:
            delivery_status = "failed"
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
        else:
            result.notifications_sent += 1

        history_row = AlertHistory(
            alert_id=notification.alert_id,
            user_id=notification.user_id,
            asset_id=notification.asset_id,
            alert_type=notification.alert_type,
            asset_name=notification.asset_name,
            triggered_at=notification.triggered_at,
            price_at_trigger=notification.price_at_trigger,
            reference_price=notification.reference_price,
            percent_change=notification.percent_change,
            currency=notification.currency,
            notification_content=notification.content,
            delivery_status=delivery_status,
        )
        db.add(history_row)

    db.commit()
    return result
