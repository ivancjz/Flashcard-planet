from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.app.models.alert import Alert
from backend.app.models.asset import Asset
from backend.app.models.enums import AlertDirection, AlertType
from backend.app.models.user import User
from backend.app.models.watchlist import Watchlist
from backend.app.schemas.watchlist import WatchlistCreateRequest, WatchlistItemResponse


def get_or_create_user(db: Session, discord_user_id: str) -> User:
    user = db.scalar(select(User).where(User.discord_user_id == discord_user_id))
    if user:
        return user

    user = User(discord_user_id=discord_user_id)
    db.add(user)
    db.flush()
    return user


def add_watchlist_item(db: Session, payload: WatchlistCreateRequest) -> Watchlist:
    user = get_or_create_user(db, payload.discord_user_id)
    asset = db.scalar(select(Asset).where(Asset.name.ilike(payload.asset_name)))
    if not asset:
        raise ValueError(f"No asset found with exact name '{payload.asset_name}'.")

    existing = db.scalar(
        select(Watchlist).where(Watchlist.user_id == user.id, Watchlist.asset_id == asset.id)
    )
    if existing:
        return existing

    watchlist = Watchlist(user_id=user.id, asset_id=asset.id)
    db.add(watchlist)
    db.flush()

    alerts: list[Alert] = []
    if payload.threshold_up_percent is not None:
        alerts.append(
            Alert(
                user_id=user.id,
                asset_id=asset.id,
                watchlist_id=watchlist.id,
                alert_type=AlertType.PRICE_UP_THRESHOLD.value,
                direction=AlertDirection.ABOVE.value,
                threshold_percent=Decimal(str(payload.threshold_up_percent)),
            )
        )
    if payload.threshold_down_percent is not None:
        alerts.append(
            Alert(
                user_id=user.id,
                asset_id=asset.id,
                watchlist_id=watchlist.id,
                alert_type=AlertType.PRICE_DOWN_THRESHOLD.value,
                direction=AlertDirection.BELOW.value,
                threshold_percent=Decimal(str(payload.threshold_down_percent)),
            )
        )
    if payload.target_price is not None:
        alerts.append(
            Alert(
                user_id=user.id,
                asset_id=asset.id,
                watchlist_id=watchlist.id,
                alert_type=AlertType.TARGET_PRICE_HIT.value,
                direction=AlertDirection.BELOW.value,
                target_price=Decimal(str(payload.target_price)),
            )
        )

    db.add_all(alerts)
    db.flush()
    return watchlist


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
