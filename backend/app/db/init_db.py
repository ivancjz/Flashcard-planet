import logging

from sqlalchemy import inspect, text

from backend.app.db.base import Base
from backend.app.db.session import engine
from backend.app.models import Alert, Asset, PriceHistory, User, Watchlist

logger = logging.getLogger(__name__)


def ensure_alert_schema() -> None:
    with engine.begin() as connection:
        inspector = inspect(connection)
        if "alerts" not in inspector.get_table_names():
            return

        existing_columns = {column["name"] for column in inspector.get_columns("alerts")}
        if "is_armed" not in existing_columns:
            connection.execute(
                text("ALTER TABLE alerts ADD COLUMN is_armed BOOLEAN NOT NULL DEFAULT TRUE")
            )
            logger.info("Added alerts.is_armed column for rearmable alert state.")

        if "last_observed_signal" not in existing_columns:
            connection.execute(
                text("ALTER TABLE alerts ADD COLUMN last_observed_signal VARCHAR(32)")
            )
            logger.info("Added alerts.last_observed_signal column for prediction change alerts.")


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_alert_schema()
