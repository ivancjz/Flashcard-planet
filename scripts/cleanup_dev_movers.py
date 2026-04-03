from __future__ import annotations

from sqlalchemy import delete

from backend.app.db.init_db import init_db
from backend.app.db.session import SessionLocal
from backend.app.models.price_history import PriceHistory

DEV_TEST_SOURCE = "dev_test"


def cleanup_dev_movers() -> int:
    init_db()
    with SessionLocal() as session:
        delete_result = session.execute(
            delete(PriceHistory).where(PriceHistory.source == DEV_TEST_SOURCE)
        )
        session.commit()
        return int(delete_result.rowcount or 0)


if __name__ == "__main__":
    deleted = cleanup_dev_movers()
    print(f"Deleted {deleted} dev_test price history row(s).")
