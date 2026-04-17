import importlib.util
import logging
import pkgutil
import subprocess
import sys
from pathlib import Path

from sqlalchemy import inspect

from backend.app.db.base import Base
from backend.app.db.session import engine

logger = logging.getLogger(__name__)

_ALEMBIC_INI = Path(__file__).resolve().parents[3] / "alembic.ini"
_VERSIONS_DIR = Path(__file__).resolve().parents[3] / "migrations" / "versions"


def _run_alembic(*args: str) -> None:
    cmd = [sys.executable, "-m", "alembic", "--config", str(_ALEMBIC_INI), *args]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout:
        logger.info("alembic stdout: %s", result.stdout.strip())
    if result.stderr:
        logger.info("alembic stderr: %s", result.stderr.strip())
    if result.returncode != 0:
        raise RuntimeError(
            f"alembic {' '.join(args)} failed (exit {result.returncode}):\n{result.stderr}"
        )


def _alembic_head_revision() -> str:
    revisions: dict[str, str | None] = {}
    for path in sorted(_VERSIONS_DIR.glob("*.py")):
        if path.name.startswith("__"):
            continue
        spec = importlib.util.spec_from_file_location(path.stem, path)
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        rev = getattr(mod, "revision", None)
        down = getattr(mod, "down_revision", None)
        if rev:
            revisions[rev] = down
    referenced = set(revisions.values()) - {None}
    heads = [r for r in revisions if r not in referenced]
    if not heads:
        raise RuntimeError("Could not determine Alembic head revision from migration files.")
    return sorted(heads)[-1]


def _expected_model_tables() -> set[str]:
    import backend.app.models as models_pkg

    for module_info in pkgutil.iter_modules(models_pkg.__path__, f"{models_pkg.__name__}."):
        importlib.import_module(module_info.name)
    return {table_name for table_name in Base.metadata.tables if table_name != "alembic_version"}


def _schema_matches_current_models(inspector: object, existing_tables: set[str]) -> bool:
    expected_tables = _expected_model_tables()
    if not expected_tables.issubset(existing_tables):
        return False

    for table_name in expected_tables:
        expected_columns = {column.name for column in Base.metadata.tables[table_name].columns}
        actual_columns = {
            column["name"]
            for column in inspector.get_columns(table_name)
        }
        if not expected_columns.issubset(actual_columns):
            return False
    return True


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
    head_revision = _alembic_head_revision()

    with engine.connect() as conn:
        inspector = inspect(conn)
        existing_tables = set(inspector.get_table_names())
        has_alembic_version = "alembic_version" in existing_tables
        current_revision = _current_alembic_revision(
            conn, has_alembic_version=has_alembic_version
        )
        schema_matches_head = _schema_matches_current_models(inspector, existing_tables)

    has_schema = "assets" in existing_tables

    if has_schema and current_revision is None:
        if schema_matches_head:
            logger.info(
                "Pre-Alembic database detected with full current schema. Stamping at head."
            )
            _run_alembic("stamp", "head")
        else:
            logger.info(
                "Pre-Alembic database detected with partial schema. Stamping at initial revision 0001."
            )
            _run_alembic("stamp", "0001")
    elif has_schema:
        if schema_matches_head and current_revision != head_revision:
            logger.info(
                "Database schema matches current head, but alembic_version=%s. Restamping at head %s.",
                current_revision,
                head_revision,
            )
            _run_alembic("stamp", "head")

    logger.info("Running Alembic migrations (upgrade head).")
    _run_alembic("upgrade", "head")
