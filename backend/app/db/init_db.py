import importlib
import logging
from pathlib import Path
import pkgutil

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from backend.app.db.base import Base
from backend.app.db.session import engine

logger = logging.getLogger(__name__)

_ALEMBIC_INI = Path(__file__).resolve().parents[3] / "alembic.ini"


def _alembic_cfg() -> Config:
    return Config(str(_ALEMBIC_INI))


def _expected_model_tables() -> set[str]:
    import backend.app.models as models_pkg

    for module_info in pkgutil.iter_modules(models_pkg.__path__, f"{models_pkg.__name__}."):
        importlib.import_module(module_info.name)
    return {table_name for table_name in Base.metadata.tables if table_name != "alembic_version"}


def init_db() -> None:
    """Bring the database schema up to the latest Alembic revision.

    Handles three cases:
    - Fresh database (no tables): runs all migrations from scratch.
    - Pre-Alembic database (tables exist but no alembic_version row):
      stamps at the correct baseline without re-running DDL, then upgrades
      any newer migrations that exist beyond that schema.
    - Already-managed database: runs upgrade head (no-op if already current).
    """
    with engine.connect() as conn:
        inspector = inspect(conn)
        existing_tables = set(inspector.get_table_names())

    has_schema = "assets" in existing_tables
    has_alembic_version = "alembic_version" in existing_tables

    if has_schema and not has_alembic_version:
        expected_tables = _expected_model_tables()
        if expected_tables.issubset(existing_tables):
            logger.info(
                "Pre-Alembic database detected with full current schema. Stamping at head."
            )
            command.stamp(_alembic_cfg(), "head")
        else:
            # Database was bootstrapped before Alembic was added, but it does
            # not yet match the current head schema. Stamp the initial revision
            # and let later migrations bring it forward.
            logger.info(
                "Pre-Alembic database detected with partial schema. Stamping at initial revision 0001."
            )
            command.stamp(_alembic_cfg(), "0001")

    logger.info("Running Alembic migrations (upgrade head).")
    command.upgrade(_alembic_cfg(), "head")
