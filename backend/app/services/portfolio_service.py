from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from backend.app.core.permissions import portfolio_position_limit, resolve_tier
from backend.app.core.price_sources import get_active_price_source_filter
from backend.app.models.asset import Asset
from backend.app.models.portfolio_lot import PortfolioLot
from backend.app.models.price_history import PriceHistory
from backend.app.models.user import User
from backend.app.schemas.portfolio import (
    PortfolioAllocationResponse,
    PortfolioLotCreateRequest,
    PortfolioLotPatchRequest,
    PortfolioLotResponse,
    PortfolioPositionResponse,
    PortfolioResponse,
    PortfolioSummaryResponse,
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
        select(User)
        .where(User.id == current_user.id)
        .with_for_update()
        .execution_options(populate_existing=True)
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


MONEY_QUANTUM = Decimal("0.01")
PERCENT_QUANTUM = Decimal("0.01")
ZERO_MONEY = Decimal("0.00")


@dataclass(frozen=True)
class _LatestPrice:
    price: Decimal
    captured_at: datetime


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _percent(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    if denominator == 0:
        return None
    return (numerator / denominator * Decimal("100")).quantize(
        PERCENT_QUANTUM,
        rounding=ROUND_HALF_UP,
    )


def _latest_raw_prices(
    db: Session,
    asset_ids: set[UUID],
) -> dict[UUID, _LatestPrice]:
    if not asset_ids:
        return {}

    ranked = (
        select(
            PriceHistory.asset_id.label("asset_id"),
            PriceHistory.price.label("price"),
            PriceHistory.captured_at.label("captured_at"),
            func.row_number()
            .over(
                partition_by=PriceHistory.asset_id,
                order_by=(
                    PriceHistory.captured_at.desc(),
                    PriceHistory.id.desc(),
                ),
            )
            .label("row_number"),
        )
        .where(
            PriceHistory.asset_id.in_(asset_ids),
            PriceHistory.market_segment == "raw",
            PriceHistory.currency == "USD",
            get_active_price_source_filter(db),
        )
        .subquery()
    )
    rows = db.execute(
        select(
            ranked.c.asset_id,
            ranked.c.price,
            ranked.c.captured_at,
        ).where(ranked.c.row_number == 1)
    ).all()
    return {
        row.asset_id: _LatestPrice(
            price=Decimal(row.price),
            captured_at=row.captured_at,
        )
        for row in rows
    }


def _lot_response(lot: PortfolioLot) -> PortfolioLotResponse:
    return PortfolioLotResponse.model_validate(lot, from_attributes=True)


def _empty_portfolio(current_user: User) -> PortfolioResponse:
    return PortfolioResponse(
        summary=PortfolioSummaryResponse(
            total_cost_basis=ZERO_MONEY,
            priced_cost_basis=ZERO_MONEY,
            total_market_value=ZERO_MONEY,
            unrealized_pnl=ZERO_MONEY,
            unrealized_pnl_percent=None,
            position_count=0,
            priced_position_count=0,
            unpriced_position_count=0,
            valuation_coverage_percent=ZERO_MONEY,
            position_limit=portfolio_position_limit(_effective_tier(current_user)),
        ),
        allocations=[],
        positions=[],
    )


def get_portfolio(db: Session, current_user: User) -> PortfolioResponse:
    lots = db.scalars(
        select(PortfolioLot)
        .options(selectinload(PortfolioLot.asset))
        .where(PortfolioLot.user_id == current_user.id)
        .order_by(
            PortfolioLot.asset_id.asc(),
            PortfolioLot.purchased_on.desc(),
            PortfolioLot.created_at.desc(),
            PortfolioLot.id.asc(),
        )
    ).all()
    if not lots:
        return _empty_portfolio(current_user)

    grouped_lots: dict[UUID, list[PortfolioLot]] = defaultdict(list)
    for lot in lots:
        grouped_lots[lot.asset_id].append(lot)

    latest_prices = _latest_raw_prices(db, set(grouped_lots))
    positions: list[PortfolioPositionResponse] = []
    for asset_id, asset_lots in grouped_lots.items():
        asset = asset_lots[0].asset
        quantity = sum(lot.quantity for lot in asset_lots)
        cost_basis = _money(
            sum(
                (
                    Decimal(lot.quantity) * Decimal(lot.unit_cost_usd)
                    for lot in asset_lots
                ),
                Decimal("0"),
            )
        )
        average_unit_cost = _money(cost_basis / Decimal(quantity))
        latest = latest_prices.get(asset_id)

        if latest is None:
            latest_raw_price = None
            latest_price_at = None
            market_value = None
            unrealized_pnl = None
            unrealized_pnl_percent = None
            valuation_status = "unpriced"
        else:
            latest_raw_price = _money(latest.price)
            latest_price_at = latest.captured_at
            market_value = _money(Decimal(quantity) * latest_raw_price)
            unrealized_pnl = _money(market_value - cost_basis)
            unrealized_pnl_percent = _percent(unrealized_pnl, cost_basis)
            valuation_status = "priced"

        positions.append(
            PortfolioPositionResponse(
                asset_id=asset_id,
                name=asset.name,
                set_name=asset.set_name,
                card_number=asset.card_number,
                game=asset.game,
                quantity=quantity,
                average_unit_cost_usd=average_unit_cost,
                cost_basis_usd=cost_basis,
                latest_raw_price_usd=latest_raw_price,
                latest_price_at=latest_price_at,
                market_value_usd=market_value,
                unrealized_pnl_usd=unrealized_pnl,
                unrealized_pnl_percent=unrealized_pnl_percent,
                valuation_status=valuation_status,
                lots=[_lot_response(lot) for lot in asset_lots],
            )
        )

    positions.sort(
        key=lambda position: (
            position.name.casefold(),
            (position.set_name or "").casefold(),
            str(position.asset_id),
        )
    )
    priced_positions = [
        position
        for position in positions
        if position.market_value_usd is not None
    ]
    total_cost_basis = _money(
        sum((position.cost_basis_usd for position in positions), Decimal("0"))
    )
    priced_cost_basis = _money(
        sum(
            (position.cost_basis_usd for position in priced_positions),
            Decimal("0"),
        )
    )
    total_market_value = _money(
        sum(
            (
                position.market_value_usd
                for position in priced_positions
                if position.market_value_usd is not None
            ),
            Decimal("0"),
        )
    )
    unrealized_pnl = _money(total_market_value - priced_cost_basis)
    position_count = len(positions)
    priced_position_count = len(priced_positions)

    allocation_values: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    allocation_counts: dict[str, int] = defaultdict(int)
    for position in priced_positions:
        allocation_values[position.game] += position.market_value_usd or ZERO_MONEY
        allocation_counts[position.game] += 1

    allocations: list[PortfolioAllocationResponse] = []
    if total_market_value > 0:
        allocation_rows = sorted(
            allocation_values.items(),
            key=lambda item: (-item[1], item[0].casefold()),
        )
        allocations = [
            PortfolioAllocationResponse(
                game=game,
                market_value_usd=_money(value),
                percentage=_percent(value, total_market_value) or ZERO_MONEY,
                priced_position_count=allocation_counts[game],
            )
            for game, value in allocation_rows
        ]
        residual = Decimal("100.00") - sum(
            (allocation.percentage for allocation in allocations),
            Decimal("0"),
        )
        allocations[0].percentage = _money(allocations[0].percentage + residual)

    return PortfolioResponse(
        summary=PortfolioSummaryResponse(
            total_cost_basis=total_cost_basis,
            priced_cost_basis=priced_cost_basis,
            total_market_value=total_market_value,
            unrealized_pnl=unrealized_pnl,
            unrealized_pnl_percent=_percent(unrealized_pnl, priced_cost_basis),
            position_count=position_count,
            priced_position_count=priced_position_count,
            unpriced_position_count=position_count - priced_position_count,
            valuation_coverage_percent=(
                _percent(
                    Decimal(priced_position_count),
                    Decimal(position_count),
                )
                or ZERO_MONEY
            ),
            position_limit=portfolio_position_limit(_effective_tier(current_user)),
        ),
        allocations=allocations,
        positions=positions,
    )
