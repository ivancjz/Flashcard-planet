"""
tests/test_signal_history_prune.py

Tests for signal-history-prune scheduler job (TASK-105 Phase 2).

Three test concerns:
  1. SQL behaviour — old rows are deleted, new rows kept (real SQLite in-memory DB)
  2. Run-log wiring — start_run / finish_run / prune_old_runs called on every path
  3. meta_json shape — retention_days_applied, rows_deleted, oldest_remaining_at present
"""
from __future__ import annotations

import unittest
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, call, patch

from sqlalchemy import JSON, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.app.models  # noqa: F401 — registers all models
from backend.app.db.base import Base
from backend.app.models.asset_signal_history import AssetSignalHistory


# ── SQLite in-memory helpers ───────────────────────────────────────────────────

def _coerce_postgres_types() -> None:
    for table in Base.metadata.tables.values():
        for col in table.columns:
            if isinstance(col.type, JSONB):
                col.type = JSON()


def _make_engine():
    _coerce_postgres_types()
    return create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _seed_history(factory, *, days_old: int, label: str = "IDLE") -> uuid.UUID:
    asset_id = uuid.uuid4()
    row = AssetSignalHistory(
        asset_id=asset_id,
        label=label,
        computed_at=datetime.now(UTC) - timedelta(days=days_old),
    )
    with factory() as s:
        s.add(row)
        s.commit()
    return asset_id


def _make_session_local(factory):
    """Return a context-manager callable that yields SQLite sessions."""
    @contextmanager
    def _sl():
        with factory() as s:
            yield s
    return _sl


def _settings(retention_days: int = 30):
    s = MagicMock()
    s.signal_history_retention_days = retention_days
    return s


# ── SQL behaviour ──────────────────────────────────────────────────────────────

class TestSignalHistoryPruneSQL(unittest.TestCase):
    """Real SQLite DB — verifies DELETE correctness."""

    def setUp(self):
        self.engine = _make_engine()
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(
            bind=self.engine, autoflush=False, autocommit=False, future=True
        )

    def tearDown(self):
        Base.metadata.drop_all(self.engine)

    def _call(self, retention_days: int = 30):
        with (
            patch("backend.app.backstage.scheduler.SessionLocal", _make_session_local(self.factory)),
            patch("backend.app.backstage.scheduler.start_run", return_value=99),
            patch("backend.app.backstage.scheduler.finish_run"),
            patch("backend.app.backstage.scheduler.prune_old_runs"),
            patch("backend.app.backstage.scheduler.get_settings", return_value=_settings(retention_days)),
        ):
            from backend.app.backstage.scheduler import _run_signal_history_prune
            _run_signal_history_prune()

    def test_old_rows_are_deleted(self):
        _seed_history(self.factory, days_old=45)  # older than 30d → delete
        self._call(retention_days=30)
        with self.factory() as s:
            remaining = s.query(AssetSignalHistory).count()
        self.assertEqual(remaining, 0)

    def test_recent_rows_are_kept(self):
        _seed_history(self.factory, days_old=15)  # within 30d → keep
        self._call(retention_days=30)
        with self.factory() as s:
            remaining = s.query(AssetSignalHistory).count()
        self.assertEqual(remaining, 1)

    def test_boundary_only_old_deleted(self):
        _seed_history(self.factory, days_old=45)  # delete
        _seed_history(self.factory, days_old=15)  # keep
        self._call(retention_days=30)
        with self.factory() as s:
            remaining = s.query(AssetSignalHistory).count()
        self.assertEqual(remaining, 1)

    def test_empty_table_runs_cleanly(self):
        """No rows to prune — must not raise."""
        self._call(retention_days=30)
        with self.factory() as s:
            remaining = s.query(AssetSignalHistory).count()
        self.assertEqual(remaining, 0)


# ── Run-log wiring ─────────────────────────────────────────────────────────────

def _mock_sl():
    sl = MagicMock()
    sl.return_value.__enter__ = MagicMock(return_value=MagicMock())
    sl.return_value.__exit__ = MagicMock(return_value=False)
    return sl


class TestSignalHistoryPruneRunLog(unittest.TestCase):
    """Verifies start_run / finish_run / prune_old_runs are called on every path."""

    def _call(self):
        with (
            patch("backend.app.backstage.scheduler.SessionLocal", _mock_sl()),
            patch("backend.app.backstage.scheduler.start_run", return_value=99) as mock_start,
            patch("backend.app.backstage.scheduler.finish_run") as mock_finish,
            patch("backend.app.backstage.scheduler.prune_old_runs") as mock_prune,
            patch("backend.app.backstage.scheduler.get_settings", return_value=_settings()),
        ):
            from backend.app.backstage.scheduler import _run_signal_history_prune
            _run_signal_history_prune()
        return mock_start, mock_finish, mock_prune

    def test_start_run_called(self):
        mock_start, _, _ = self._call()
        mock_start.assert_called_once()

    def test_finish_run_called(self):
        _, mock_finish, _ = self._call()
        mock_finish.assert_called_once()

    def test_prune_called(self):
        _, _, mock_prune = self._call()
        mock_prune.assert_called_once()

    def test_finish_run_status_success_on_normal_path(self):
        _, mock_finish, _ = self._call()
        _, kwargs = mock_finish.call_args
        self.assertEqual(kwargs.get("status"), "success")

    def test_finish_run_error_status_on_exception(self):
        """When the DELETE raises, finish_run is called with status='error'."""
        with (
            patch("backend.app.backstage.scheduler.SessionLocal", _mock_sl()),
            patch("backend.app.backstage.scheduler.start_run", return_value=99),
            patch("backend.app.backstage.scheduler.finish_run") as mock_finish,
            patch("backend.app.backstage.scheduler.prune_old_runs"),
            patch("backend.app.backstage.scheduler.get_settings", return_value=_settings()),
            # Force the inner session.execute to raise
            patch("backend.app.backstage.scheduler.sa_text", side_effect=RuntimeError("db boom")),
        ):
            from backend.app.backstage.scheduler import _run_signal_history_prune
            with self.assertRaises(RuntimeError):
                _run_signal_history_prune()
        _, kwargs = mock_finish.call_args
        self.assertEqual(kwargs.get("status"), "error")


# ── meta_json shape ────────────────────────────────────────────────────────────

class TestSignalHistoryPruneMeta(unittest.TestCase):
    """Verifies finish_run receives the expected meta_json keys."""

    def setUp(self):
        self.engine = _make_engine()
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(
            bind=self.engine, autoflush=False, autocommit=False, future=True
        )

    def tearDown(self):
        Base.metadata.drop_all(self.engine)

    def _call(self, retention_days: int = 30):
        mock_finish = MagicMock()
        with (
            patch("backend.app.backstage.scheduler.SessionLocal", _make_session_local(self.factory)),
            patch("backend.app.backstage.scheduler.start_run", return_value=99),
            patch("backend.app.backstage.scheduler.finish_run", mock_finish),
            patch("backend.app.backstage.scheduler.prune_old_runs"),
            patch("backend.app.backstage.scheduler.get_settings", return_value=_settings(retention_days)),
        ):
            from backend.app.backstage.scheduler import _run_signal_history_prune
            _run_signal_history_prune()
        return mock_finish

    def test_meta_contains_retention_days_applied(self):
        mock_finish = self._call(retention_days=45)
        _, kwargs = mock_finish.call_args
        self.assertEqual(kwargs["meta_json"]["retention_days_applied"], 45)

    def test_meta_contains_rows_deleted(self):
        _seed_history(self.factory, days_old=60)
        mock_finish = self._call(retention_days=30)
        _, kwargs = mock_finish.call_args
        self.assertGreaterEqual(kwargs["meta_json"]["rows_deleted"], 1)

    def test_meta_rows_deleted_zero_when_nothing_pruned(self):
        _seed_history(self.factory, days_old=5)  # within retention window
        mock_finish = self._call(retention_days=30)
        _, kwargs = mock_finish.call_args
        self.assertEqual(kwargs["meta_json"]["rows_deleted"], 0)

    def test_meta_contains_oldest_remaining_at_key(self):
        mock_finish = self._call()
        _, kwargs = mock_finish.call_args
        self.assertIn("oldest_remaining_at", kwargs["meta_json"])


if __name__ == "__main__":
    unittest.main()
