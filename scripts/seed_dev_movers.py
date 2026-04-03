from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import delete, func, select

from backend.app.db.init_db import init_db
from backend.app.db.session import SessionLocal
from backend.app.models.asset import Asset
from backend.app.models.price_history import PriceHistory

DEV_TEST_SOURCE = "dev_test"


def quantize_price(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def build_latest_real_prices_subquery():
    return (
        select(
            PriceHistory.asset_id,
            func.max(PriceHistory.captured_at).label("max_captured_at"),
        )
        .where(
            PriceHistory.source != "sample_seed",
            PriceHistory.source != DEV_TEST_SOURCE,
        )
        .group_by(PriceHistory.asset_id)
        .subquery()
    )


def build_dev_price(latest_price: Decimal, index: int) -> Decimal:
    if index % 2 == 0:
        return quantize_price(latest_price * Decimal("0.85"))
    return quantize_price(latest_price * Decimal("1.15"))


def seed_dev_movers(limit: int = 2) -> int:
    init_db()
    with SessionLocal() as session:
        latest_real_prices = build_latest_real_prices_subquery()
        rows = session.execute(
            select(Asset, PriceHistory)
            .join(PriceHistory, Asset.id == PriceHistory.asset_id)
            .join(
                latest_real_prices,
                (latest_real_prices.c.asset_id == PriceHistory.asset_id)
                & (latest_real_prices.c.max_captured_at == PriceHistory.captured_at),
            )
            .order_by(Asset.name.asc())
            .limit(limit)
        ).all()

        if not rows:
            raise RuntimeError("No real ingested assets were found. Run scripts.ingest_pokemon_tcg first.")

        asset_ids = [asset.id for asset, _ in rows]
        session.execute(
            delete(PriceHistory).where(
                PriceHistory.asset_id.in_(asset_ids),
                PriceHistory.source == DEV_TEST_SOURCE,
            )
        )

        inserted = 0
        for index, (asset, latest_price_row) in enumerate(rows):
            dev_price = build_dev_price(Decimal(latest_price_row.price), index)
            captured_at = latest_price_row.captured_at - timedelta(hours=index + 1)

            session.add(
                PriceHistory(
                    asset_id=asset.id,
                    source=DEV_TEST_SOURCE,
                    currency=latest_price_row.currency,
                    price=dev_price,
                    captured_at=captured_at,
                )
            )
            inserted += 1

        session.commit()
        return inserted


if __name__ == "__main__":
    inserted = seed_dev_movers()
    print(f"Inserted {inserted} dev_test price history row(s) for top movers verification.")
