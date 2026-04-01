from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models.asset import Asset
from backend.app.models.price_history import PriceHistory
from backend.app.schemas.price import AssetPriceResponse, TopMoverResponse


def aliased_subquery(subquery, alias_name: str, rank: int):
    return select(subquery).where(subquery.c.price_rank == rank).subquery(alias_name)


def get_asset_prices_by_name(db: Session, asset_name: str) -> list[AssetPriceResponse]:
    latest_subquery = (
        select(
            PriceHistory.asset_id,
            func.max(PriceHistory.captured_at).label("max_captured_at"),
        )
        .group_by(PriceHistory.asset_id)
        .subquery()
    )

    stmt = (
        select(Asset, PriceHistory)
        .join(PriceHistory, Asset.id == PriceHistory.asset_id)
        .join(
            latest_subquery,
            (latest_subquery.c.asset_id == PriceHistory.asset_id)
            & (latest_subquery.c.max_captured_at == PriceHistory.captured_at),
        )
        .where(Asset.name.ilike(f"%{asset_name}%"))
        .order_by(Asset.name.asc())
    )

    rows = db.execute(stmt).all()
    return [
        AssetPriceResponse(
            asset_id=asset.id,
            asset_class=asset.asset_class,
            category=asset.category,
            name=asset.name,
            set_name=asset.set_name,
            card_number=asset.card_number,
            year=asset.year,
            variant=asset.variant,
            grade_company=asset.grade_company,
            grade_score=asset.grade_score,
            latest_price=price.price,
            currency=price.currency,
            source=price.source,
            captured_at=price.captured_at,
        )
        for asset, price in rows
    ]


def get_top_movers(db: Session, limit: int = 10) -> list[TopMoverResponse]:
    ranked = (
        select(
            PriceHistory.asset_id,
            PriceHistory.price,
            PriceHistory.captured_at,
            func.row_number()
            .over(partition_by=PriceHistory.asset_id, order_by=PriceHistory.captured_at.desc())
            .label("price_rank"),
        )
        .subquery()
    )

    current = aliased_subquery(ranked, "current", 1)
    previous = aliased_subquery(ranked, "previous", 2)

    stmt = (
        select(
            Asset.id,
            Asset.name,
            Asset.category,
            current.c.price.label("latest_price"),
            previous.c.price.label("previous_price"),
        )
        .join(current, current.c.asset_id == Asset.id)
        .join(previous, previous.c.asset_id == Asset.id)
    )

    rows = db.execute(stmt).all()
    movers: list[TopMoverResponse] = []
    for row in rows:
        previous_price = Decimal(row.previous_price)
        latest_price = Decimal(row.latest_price)
        if previous_price == 0:
            continue
        absolute_change = latest_price - previous_price
        percent_change = (absolute_change / previous_price) * Decimal("100")
        movers.append(
            TopMoverResponse(
                asset_id=row.id,
                name=row.name,
                category=row.category,
                latest_price=latest_price,
                previous_price=previous_price,
                absolute_change=absolute_change.quantize(Decimal("0.01")),
                percent_change=percent_change.quantize(Decimal("0.01")),
            )
        )

    movers.sort(key=lambda item: abs(item.percent_change), reverse=True)
    return movers[:limit]
