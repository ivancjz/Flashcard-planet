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


def _alembic_head_revision(cfg: Config) -> str:
    modules = command._load_revision_modules(cfg)
    referenced_revisions = {
        referenced_revision
        for module in modules
        for referenced_revision in command._normalize_down_revisions(
            getattr(module, "down_revision", None)
        )
    }
    head_revisions = sorted(
        getattr(module, "revision", "")
        for module in modules
        if getattr(module, "revision", "") not in referenced_revisions
    )
    if not head_revisions:
        raise RuntimeError("Could not determine Alembic head revision from local migration files.")
    return head_revisions[-1]


def _expected_model_tables() -> set[str]:
    import backend.app.models as models_pkg

    for module_info in pkgutil.iter_modules(models_pkg.__path__, f"{models_pkg.__name__}."):
        importlib.import_module(module_info.name)
    return {table_name for table_name in Base.metadata.tables if table_name != "alembic_version"}


def _current_alembic_revision(conn: object, *, has_alembic_version: bool) -> str | None:
    if not has_alembic_version:
        return None
    result = conn.exec_driver_sql("SELECT version_num FROM alembic_version")
    return result.scalar_one_or_none()


def init_db() -> None:
    """Bring the database schema up to the latest Alembic revision.

    Handles three cases:
    - Fresh database (no tables): runs all migrations from scratch.
    - Pre-Alembic database (tables exist but no alembic_version row):
      stamps at the correct baseline without re-running DDL, then upgrades
      any newer migrations that exist beyond that schema.
    - Already-managed database: runs upgrade head (no-op if already current).
    """
    cfg = _alembic_cfg()
    head_revision = _alembic_head_revision(cfg)

    with engine.connect() as conn:
        inspector = inspect(conn)
        existing_tables = set(inspector.get_table_names())
        has_alembic_version = "alembic_version" in existing_tables
        current_revision = _current_alembic_revision(
            conn, has_alembic_version=has_alembic_version
        )

    has_schema = "assets" in existing_tables

    if has_schema and current_revision is None:
        expected_tables = _expected_model_tables()
        if expected_tables.issubset(existing_tables):
            logger.info(
                "Pre-Alembic database detected with full current schema. Stamping at head."
            )
            command.stamp(cfg, "head")
        else:
            # Database was bootstrapped before Alembic was added, but it does
            # not yet match the current head schema. Stamp the initial revision
            # and let later migrations bring it forward.
            logger.info(
                "Pre-Alembic database detected with partial schema. Stamping at initial revision 0001."
            )
            command.stamp(cfg, "0001")
    elif has_schema:
        expected_tables = _expected_model_tables()
        if expected_tables.issubset(existing_tables) and current_revision != head_revision:
            logger.info(
                "Database schema matches current head, but alembic_version=%s. Restamping at head %s.",
                current_revision,
                head_revision,
            )
            command.stamp(cfg, "head")

    logger.info("Running Alembic migrations (upgrade head).")
    command.upgrade(cfg, "head")
