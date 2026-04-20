"""Tests for bulk-set-price-refresh guard (TASK-011).

Verifies three behaviors:
  1. set_id with no assets in DB → fetch_cards_for_set NOT called
  2. set_id with existing assets → fetch_cards_for_set IS called
  3. bulk_refresh_auto_import_new_sets=True → guard bypassed, fetch IS called
"""
from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from sqlalchemy import JSON, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import backend.app.models  # noqa: F401
from backend.app.backstage.scheduler import _run_bulk_set_price_refresh
from backend.app.db.base import Base
from backend.app.models.asset import Asset


# ── SQLite helpers ─────────────────────────────────────────────────────────────

def _coerce_postgres_types_for_sqlite() -> None:
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()


@contextmanager
def session_scope():
    _coerce_postgres_types_for_sqlite()
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    LocalSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with LocalSession() as db_session:
        yield db_session
    Base.metadata.drop_all(engine)


def _make_session_ctx(session: Session) -> MagicMock:
    ctx = MagicMock()
    ctx.__enter__.return_value = session
    ctx.__exit__.return_value = False
    return ctx


def _make_asset(session: Session, *, set_id: str) -> Asset:
    asset = Asset(
        asset_class="TCG",
        category="Pokemon",
        name="Test Card",
        set_name="Test Set",
        card_number="1",
        year=2021,
        language="EN",
        variant="Normal",
        external_id=f"{set_id}-test-guard-1",
        metadata_json={"set_id": set_id},
    )
    session.add(asset)
    session.commit()
    session.refresh(asset)
    return asset


def _mock_settings(*, set_ids: list[str], auto_import: bool = False) -> MagicMock:
    s = MagicMock()
    s.bulk_set_id_list = set_ids
    s.bulk_refresh_auto_import_new_sets = auto_import
    return s


def _patched_importer(fetch_return: list) -> tuple[MagicMock, MagicMock]:
    """Return (importer_class_mock, importer_instance_mock)."""
    instance = MagicMock()
    instance.fetch_cards_for_set.return_value = fetch_return
    cls = MagicMock(return_value=instance)
    return cls, instance


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_bulk_refresh_skips_set_with_no_existing_assets() -> None:
    """When a set has 0 assets in DB and auto_import is False, the API must NOT be called."""
    with session_scope() as session:
        # No assets inserted for "swsh7"
        importer_cls, importer = _patched_importer([])

        with (
            patch("backend.app.backstage.scheduler.get_settings",
                  return_value=_mock_settings(set_ids=["swsh7"])),
            patch("backend.app.backstage.scheduler.SessionLocal",
                  return_value=_make_session_ctx(session)),
            patch("scripts.import_pokemon_cards.PokemonTCGImporter", importer_cls),
            patch("scripts.import_pokemon_cards.price_history_available", return_value=False),
        ):
            _run_bulk_set_price_refresh()

        importer.fetch_cards_for_set.assert_not_called()


def test_bulk_refresh_fetches_set_with_existing_assets() -> None:
    """When a set has assets in DB, the API fetch MUST be called."""
    with session_scope() as session:
        _make_asset(session, set_id="swsh7")
        importer_cls, importer = _patched_importer([])

        with (
            patch("backend.app.backstage.scheduler.get_settings",
                  return_value=_mock_settings(set_ids=["swsh7"])),
            patch("backend.app.backstage.scheduler.SessionLocal",
                  return_value=_make_session_ctx(session)),
            patch("scripts.import_pokemon_cards.PokemonTCGImporter", importer_cls),
            patch("scripts.import_pokemon_cards.price_history_available", return_value=False),
        ):
            _run_bulk_set_price_refresh()

        importer.fetch_cards_for_set.assert_called_once_with("swsh7")


def test_bulk_refresh_auto_import_bypasses_guard() -> None:
    """When bulk_refresh_auto_import_new_sets=True, fetch is called even with 0 assets in DB."""
    with session_scope() as session:
        # No assets inserted
        importer_cls, importer = _patched_importer([])

        with (
            patch("backend.app.backstage.scheduler.get_settings",
                  return_value=_mock_settings(set_ids=["swsh7"], auto_import=True)),
            patch("backend.app.backstage.scheduler.SessionLocal",
                  return_value=_make_session_ctx(session)),
            patch("scripts.import_pokemon_cards.PokemonTCGImporter", importer_cls),
            patch("scripts.import_pokemon_cards.price_history_available", return_value=False),
        ):
            _run_bulk_set_price_refresh()

        importer.fetch_cards_for_set.assert_called_once_with("swsh7")
