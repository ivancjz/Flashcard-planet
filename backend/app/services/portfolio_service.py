from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.core.permissions import portfolio_position_limit, resolve_tier
from backend.app.models.asset import Asset
from backend.app.models.portfolio_lot import PortfolioLot
from backend.app.models.user import User
from backend.app.schemas.portfolio import (
    PortfolioLotCreateRequest,
    PortfolioLotPatchRequest,
)


class PortfolioAssetNotFoundError(ValueError):
    pass


class PortfolioLotNotFoundError(ValueError):
    pass


class PortfolioPositionLimitError(ValueError):
    def __init__(self, position_limit: int, position_count: int) -> None:
        self.position_limit = position_limit
        self.position_count = position_count
        super().__init__(
            "Portfolio position limit reached: "
            f"{position_count} of {position_limit} distinct positions are already in use."
        )


def _effective_tier(user: User) -> str:
    return resolve_tier(
        user.email,
        user.access_tier,
        user.subscription_tier,
        user.subscription_status,
    )


def _owned_lot(db: Session, user_id: UUID, lot_id: UUID) -> PortfolioLot:
    lot = db.scalar(
        select(PortfolioLot).where(
            PortfolioLot.id == lot_id,
            PortfolioLot.user_id == user_id,
        )
    )
    if lot is None:
        raise PortfolioLotNotFoundError(f"Portfolio lot {lot_id} was not found.")
    return lot


def create_portfolio_lot(
    db: Session,
    current_user: User,
    payload: PortfolioLotCreateRequest,
) -> PortfolioLot:
    asset_exists = db.scalar(select(Asset.id).where(Asset.id == payload.asset_id))
    if asset_exists is None:
        raise PortfolioAssetNotFoundError(
            f"Portfolio asset {payload.asset_id} was not found."
        )

    locked_user = db.scalar(
        select(User).where(User.id == current_user.id).with_for_update()
    )
    if locked_user is None:
        raise PortfolioLotNotFoundError("Portfolio owner was not found.")

    already_owned = db.scalar(
        select(PortfolioLot.id)
        .where(
            PortfolioLot.user_id == locked_user.id,
            PortfolioLot.asset_id == payload.asset_id,
        )
        .limit(1)
    )

    limit = portfolio_position_limit(_effective_tier(locked_user))
    if already_owned is None and limit is not None:
        position_count = int(
            db.scalar(
                select(func.count(func.distinct(PortfolioLot.asset_id))).where(
                    PortfolioLot.user_id == locked_user.id
                )
            )
            or 0
        )
        if position_count >= limit:
            raise PortfolioPositionLimitError(limit, position_count)

    lot = PortfolioLot(
        user_id=locked_user.id,
        asset_id=payload.asset_id,
        quantity=payload.quantity,
        unit_cost_usd=payload.unit_cost_usd,
        purchased_on=payload.purchased_on,
    )
    db.add(lot)
    db.flush()
    db.refresh(lot)
    return lot


def update_portfolio_lot(
    db: Session,
    current_user: User,
    lot_id: UUID,
    payload: PortfolioLotPatchRequest,
) -> PortfolioLot:
    lot = _owned_lot(db, current_user.id, lot_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(lot, field, value)
    db.flush()
    db.refresh(lot)
    return lot


def delete_portfolio_lot(
    db: Session,
    current_user: User,
    lot_id: UUID,
) -> None:
    lot = _owned_lot(db, current_user.id, lot_id)
    db.delete(lot)
    db.flush()
