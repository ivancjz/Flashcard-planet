from sqlalchemy import select

from backend.app.db.init_db import init_db
from backend.app.db.session import SessionLocal
from backend.app.models.asset import Asset
from backend.app.models.price_history import PriceHistory
from database.sample_data import ASSETS, PRICE_HISTORY


def seed() -> None:
    init_db()
    with SessionLocal() as session:
        for asset_payload in ASSETS:
            existing = session.scalar(
                select(Asset).where(Asset.external_id == asset_payload["external_id"])
            )
            if existing:
                asset = existing
            else:
                asset = Asset(**asset_payload)
                session.add(asset)
                session.flush()

            for point in PRICE_HISTORY[asset.external_id]:
                already_exists = session.scalar(
                    select(PriceHistory).where(
                        PriceHistory.asset_id == asset.id,
                        PriceHistory.captured_at == point["captured_at"],
                    )
                )
                if already_exists:
                    continue

                session.add(
                    PriceHistory(
                        asset_id=asset.id,
                        source="sample_seed",
                        currency="USD",
                        price=point["price"],
                        captured_at=point["captured_at"],
                    )
                )

        session.commit()


if __name__ == "__main__":
    seed()
    print("Seeded sample assets and price history.")
