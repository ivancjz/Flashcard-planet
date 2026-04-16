from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from backend.app.core.banner import UPGRADE_URL
from backend.app.core.permissions import Feature, can, watchlist_limit
from backend.app.core.price_sources import get_active_price_source_filter
from backend.app.models.alert import Alert
from backend.app.models.asset import Asset
from backend.app.models.enums import AlertDirection, AlertType
from backend.app.models.price_history import PriceHistory
from backend.app.models.user import User
from backend.app.models.watchlist import Watchlist
from backend.app.schemas.watchlist import WatchlistCreateRequest, WatchlistItemResponse
_TIER_ERROR_PREFIX = "[tier]"  # must match alert_service._TIER_ERROR_PREFIX
from backend.app.services.price_service import get_prediction_state_for_asset


@dataclass
class WatchlistUpsertResult:
    watchlist: Watchlist
    created_watchlist: bool
    added_rule_labels: list[str]


def get_or_create_user(db: Session, discord_user_id: str) -> User:
    user = db.scalar(select(User).where(User.discord_user_id == discord_user_id))
    if user:
        return user

    user = User(discord_user_id=discord_user_id)
    db.add(user)
    db.flush()
    return user


def has_matching_alert(
    watchlist: Watchlist,
    *,
    alert_type: str,
    direction: str | None = None,
    threshold_percent: Decimal | None = None,
    target_price: Decimal | None = None,
) -> bool:
    for alert in watchlist.alerts:
        if not alert.is_active:
            continue
        if alert.alert_type != alert_type:
            continue
        if direction is not None and alert.direction != direction:
            continue
        if threshold_percent is not None and alert.threshold_percent != threshold_percent:
            continue
        if target_price is not None and alert.target_price != target_price:
            continue
        return True
    return False


def build_rule_label(
    *,
    alert_type: str,
    threshold_percent: Decimal | None = None,
    target_price: Decimal | None = None,
    currency: str = "USD",
    direction: str | None = None,
) -> str:
    if alert_type == AlertType.PRICE_UP_THRESHOLD.value and threshold_percent is not None:
        return f"up {threshold_percent:.2f}%"
    if alert_type == AlertType.PRICE_DOWN_THRESHOLD.value and threshold_percent is not None:
        return f"down {threshold_percent:.2f}%"
    if alert_type == AlertType.TARGET_PRICE_HIT.value and target_price is not None:
        comparator = ">=" if direction == AlertDirection.ABOVE.value else "<="
        return f"target {comparator} {target_price:.2f} {currency}"
    if alert_type == AlertType.PREDICT_SIGNAL_CHANGE.value:
        return "prediction signal change"
    if alert_type == AlertType.PREDICT_UP_PROBABILITY_ABOVE.value and threshold_percent is not None:
        return f"predict Up >= {threshold_percent:.2f}%"
    if alert_type == AlertType.PREDICT_DOWN_PROBABILITY_ABOVE.value and threshold_percent is not None:
        return f"predict Down >= {threshold_percent:.2f}%"
    return alert_type


def add_watchlist_item(db: Session, payload: WatchlistCreateRequest) -> WatchlistUpsertResult:
    user = get_or_create_user(db, payload.discord_user_id)

    # Tier: watchlist count limit
    _cap = watchlist_limit(user.access_tier)
    if _cap is not None:
        _active_count: int = int(
            db.scalar(select(func.count(Watchlist.id)).where(Watchlist.user_id == user.id)) or 0
        )
        if _active_count >= _cap:
            raise ValueError(
                f"{_TIER_ERROR_PREFIX} Free accounts are limited to {_cap} watchlist item(s). "
                f"You have {_active_count}. "
                f"Remove an item or upgrade to Pro for unlimited watchlists: {UPGRADE_URL}"
            )

    asset = db.scalar(select(Asset).where(Asset.name.ilike(payload.asset_name)))
    if not asset:
        raise ValueError(f"No asset found with exact name '{payload.asset_name}'.")

    existing = db.scalar(
        select(Watchlist).where(Watchlist.user_id == user.id, Watchlist.asset_id == asset.id)
    )
    created_watchlist = existing is None
    if existing:
        watchlist = db.scalar(
            select(Watchlist)
            .options(selectinload(Watchlist.alerts))
            .where(Watchlist.id == existing.id)
        )
    else:
        watchlist = Watchlist(user_id=user.id, asset_id=asset.id)
        db.add(watchlist)
        db.flush()
        db.refresh(watchlist, attribute_names=["alerts"])

    alerts: list[Alert] = []
    added_rule_labels: list[str] = []
    if payload.threshold_up_percent is not None:
        threshold_up = Decimal(str(payload.threshold_up_percent))
        if not has_matching_alert(
            watchlist,
            alert_type=AlertType.PRICE_UP_THRESHOLD.value,
            direction=AlertDirection.ABOVE.value,
            threshold_percent=threshold_up,
        ):
            alerts.append(
                Alert(
                    user_id=user.id,
                    asset_id=asset.id,
                    watchlist_id=watchlist.id,
                    alert_type=AlertType.PRICE_UP_THRESHOLD.value,
                    direction=AlertDirection.ABOVE.value,
                    threshold_percent=threshold_up,
                )
            )
            added_rule_labels.append(
                build_rule_label(
                    alert_type=AlertType.PRICE_UP_THRESHOLD.value,
                    threshold_percent=threshold_up,
                )
            )
    if payload.threshold_down_percent is not None:
        threshold_down = Decimal(str(payload.threshold_down_percent))
        if not has_matching_alert(
            watchlist,
            alert_type=AlertType.PRICE_DOWN_THRESHOLD.value,
            direction=AlertDirection.BELOW.value,
            threshold_percent=threshold_down,
        ):
            alerts.append(
                Alert(
                    user_id=user.id,
                    asset_id=asset.id,
                    watchlist_id=watchlist.id,
                    alert_type=AlertType.PRICE_DOWN_THRESHOLD.value,
                    direction=AlertDirection.BELOW.value,
                    threshold_percent=threshold_down,
                )
            )
            added_rule_labels.append(
                build_rule_label(
                    alert_type=AlertType.PRICE_DOWN_THRESHOLD.value,
                    threshold_percent=threshold_down,
                )
            )
    if payload.target_price is not None:
        target_price = Decimal(str(payload.target_price))
        source_filter = get_active_price_source_filter(db)
        latest_real_price = db.scalar(
            select(PriceHistory.price)
            .where(
                PriceHistory.asset_id == asset.id,
                source_filter,
            )
            .order_by(desc(PriceHistory.captured_at))
            .limit(1)
        )
        target_direction = (
            AlertDirection.ABOVE.value
            if latest_real_price is not None and target_price > Decimal(latest_real_price)
            else AlertDirection.BELOW.value
        )
        if not has_matching_alert(
            watchlist,
            alert_type=AlertType.TARGET_PRICE_HIT.value,
            direction=target_direction,
            target_price=target_price,
        ):
            alerts.append(
                Alert(
                    user_id=user.id,
                    asset_id=asset.id,
                    watchlist_id=watchlist.id,
                    alert_type=AlertType.TARGET_PRICE_HIT.value,
                    direction=target_direction,
                    target_price=target_price,
                )
            )
            added_rule_labels.append(
                build_rule_label(
                    alert_type=AlertType.TARGET_PRICE_HIT.value,
                    target_price=target_price,
                    currency="USD",
                    direction=target_direction,
                )
            )

    if payload.predict_signal_change:
        initial_prediction = get_prediction_state_for_asset(db, asset.id).prediction
        if initial_prediction == "Not enough data":
            initial_prediction = None
        if not has_matching_alert(
            watchlist,
            alert_type=AlertType.PREDICT_SIGNAL_CHANGE.value,
        ):
            alerts.append(
                Alert(
                    user_id=user.id,
                    asset_id=asset.id,
                    watchlist_id=watchlist.id,
                    alert_type=AlertType.PREDICT_SIGNAL_CHANGE.value,
                    direction=None,
                    last_observed_signal=initial_prediction,
                )
            )
            added_rule_labels.append(
                build_rule_label(
                    alert_type=AlertType.PREDICT_SIGNAL_CHANGE.value,
                )
            )

    if payload.predict_up_probability_above is not None:
        predict_up_threshold = Decimal(str(payload.predict_up_probability_above))
        if not has_matching_alert(
            watchlist,
            alert_type=AlertType.PREDICT_UP_PROBABILITY_ABOVE.value,
            threshold_percent=predict_up_threshold,
        ):
            alerts.append(
                Alert(
                    user_id=user.id,
                    asset_id=asset.id,
                    watchlist_id=watchlist.id,
                    alert_type=AlertType.PREDICT_UP_PROBABILITY_ABOVE.value,
                    direction=None,
                    threshold_percent=predict_up_threshold,
                )
            )
            added_rule_labels.append(
                build_rule_label(
                    alert_type=AlertType.PREDICT_UP_PROBABILITY_ABOVE.value,
                    threshold_percent=predict_up_threshold,
                )
            )

    if payload.predict_down_probability_above is not None:
        predict_down_threshold = Decimal(str(payload.predict_down_probability_above))
        if not has_matching_alert(
            watchlist,
            alert_type=AlertType.PREDICT_DOWN_PROBABILITY_ABOVE.value,
            threshold_percent=predict_down_threshold,
        ):
            alerts.append(
                Alert(
                    user_id=user.id,
                    asset_id=asset.id,
                    watchlist_id=watchlist.id,
                    alert_type=AlertType.PREDICT_DOWN_PROBABILITY_ABOVE.value,
                    direction=None,
                    threshold_percent=predict_down_threshold,
                )
            )
            added_rule_labels.append(
                build_rule_label(
                    alert_type=AlertType.PREDICT_DOWN_PROBABILITY_ABOVE.value,
                    threshold_percent=predict_down_threshold,
                )
            )

    if alerts:
        db.add_all(alerts)
        db.flush()
    return WatchlistUpsertResult(
        watchlist=watchlist,
        created_watchlist=created_watchlist,
        added_rule_labels=added_rule_labels,
    )


def remove_watchlist_item(db: Session, discord_user_id: str, asset_name: str) -> bool:
    stmt = (
        select(Watchlist)
        .join(User, User.id == Watchlist.user_id)
        .join(Asset, Asset.id == Watchlist.asset_id)
        .where(User.discord_user_id == discord_user_id, Asset.name.ilike(asset_name))
    )
    watchlist = db.scalar(stmt)
    if not watchlist:
        return False
    db.delete(watchlist)
    db.flush()
    return True


def list_watchlist_items(db: Session, discord_user_id: str) -> list[WatchlistItemResponse]:
    stmt = (
        select(Watchlist)
        .options(
            selectinload(Watchlist.asset),
            selectinload(Watchlist.alerts),
        )
        .join(User, User.id == Watchlist.user_id)
        .where(User.discord_user_id == discord_user_id)
        .order_by(Watchlist.created_at.desc())
    )
    watchlists = db.scalars(stmt).all()

    items: list[WatchlistItemResponse] = []
    for watchlist in watchlists:
        threshold_up_percent: Decimal | None = None
        threshold_down_percent: Decimal | None = None
        target_price: Decimal | None = None

        for alert in watchlist.alerts:
            if alert.threshold_percent is not None:
                if alert.direction == AlertDirection.ABOVE.value:
                    threshold_up_percent = alert.threshold_percent
                elif alert.direction == AlertDirection.BELOW.value:
                    threshold_down_percent = alert.threshold_percent

            if alert.target_price is not None:
                target_price = alert.target_price

        items.append(
            WatchlistItemResponse(
                watchlist_id=watchlist.id,
                asset_id=watchlist.asset.id,
                name=watchlist.asset.name,
                category=watchlist.asset.category,
                added_at=watchlist.created_at,
                threshold_up_percent=threshold_up_percent,
                threshold_down_percent=threshold_down_percent,
                target_price=target_price,
            )
        )

    return items
