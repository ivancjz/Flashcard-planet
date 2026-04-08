import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from backend.app.db.session import engine

logger = logging.getLogger(__name__)

_ALEMBIC_INI = Path(__file__).resolve().parents[3] / "alembic.ini"


def _alembic_cfg() -> Config:
    return Config(str(_ALEMBIC_INI))


def init_db() -> None:
    """Bring the database schema up to the latest Alembic revision.

    Handles three cases:
    - Fresh database (no tables): runs all migrations from scratch.
    - Pre-Alembic database (tables exist but no alembic_version row):
      stamps at the initial revision without re-running DDL, then upgrades
      any newer migrations that exist beyond the initial schema.
    - Already-managed database: runs upgrade head (no-op if already current).
    """
    with engine.connect() as conn:
        inspector = inspect(conn)
        existing_tables = set(inspector.get_table_names())

    has_schema = "assets" in existing_tables
    has_alembic_version = "alembic_version" in existing_tables

    if has_schema and not has_alembic_version:
        # Database was bootstrapped with create_all() before Alembic was added.
        # Stamp it at the initial revision so Alembic knows the baseline,
        # then upgrade in case any migrations beyond 0001 were added.
        logger.info(
            "Pre-Alembic database detected. Stamping at initial revision 0001."
        )
        command.stamp(_alembic_cfg(), "0001")

    logger.info("Running Alembic migrations (upgrade head).")
    command.upgrade(_alembic_cfg(), "head")
