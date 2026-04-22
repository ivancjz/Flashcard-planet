"""
tests/test_bulk_refresh_runlog.py

TDD: _run_bulk_set_price_refresh() must call start_run/finish_run so the
job appears in /admin/stats.  Uses empty set_ids or forced exceptions to
exercise the code paths without touching real DB or the Pokemon TCG API.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch


def _mock_session_local():
    sl = MagicMock()
    sl.return_value.__enter__ = MagicMock(return_value=MagicMock())
    sl.return_value.__exit__ = MagicMock(return_value=False)
    return sl


def _empty_settings():
    s = MagicMock()
    s.bulk_set_id_list = []
    return s


class TestBulkRefreshRunLog(unittest.TestCase):
    """_run_bulk_set_price_refresh writes run-log audit rows."""

    # ── test 1: start_run is called with JOB_BULK_REFRESH ────────────────────

    def test_start_run_called_with_bulk_refresh_job_name(self):
        with (
            patch("backend.app.backstage.scheduler.SessionLocal", _mock_session_local()),
            patch("backend.app.backstage.scheduler.get_settings", return_value=_empty_settings()),
            patch("backend.app.backstage.scheduler.start_run", return_value=1) as mock_start,
            patch("backend.app.backstage.scheduler.finish_run"),
            patch("backend.app.backstage.scheduler.prune_old_runs"),
        ):
            from backend.app.backstage.scheduler import _run_bulk_set_price_refresh
            _run_bulk_set_price_refresh()

        from backend.app.services.scheduler_run_log_service import JOB_BULK_REFRESH
        mock_start.assert_called_once()
        self.assertEqual(mock_start.call_args[0][1], JOB_BULK_REFRESH)

    # ── test 2: finish_run(success) when set_ids is empty (skip path) ────────

    def test_finish_run_success_when_set_ids_empty(self):
        with (
            patch("backend.app.backstage.scheduler.SessionLocal", _mock_session_local()),
            patch("backend.app.backstage.scheduler.get_settings", return_value=_empty_settings()),
            patch("backend.app.backstage.scheduler.start_run", return_value=1),
            patch("backend.app.backstage.scheduler.finish_run") as mock_finish,
            patch("backend.app.backstage.scheduler.prune_old_runs"),
        ):
            from backend.app.backstage.scheduler import _run_bulk_set_price_refresh
            _run_bulk_set_price_refresh()

        mock_finish.assert_called_once()
        self.assertEqual(mock_finish.call_args[1]["status"], "success")

    # ── test 3: finish_run uses the run_id returned by start_run ─────────────

    def test_finish_run_receives_correct_run_id(self):
        with (
            patch("backend.app.backstage.scheduler.SessionLocal", _mock_session_local()),
            patch("backend.app.backstage.scheduler.get_settings", return_value=_empty_settings()),
            patch("backend.app.backstage.scheduler.start_run", return_value=42),
            patch("backend.app.backstage.scheduler.finish_run") as mock_finish,
            patch("backend.app.backstage.scheduler.prune_old_runs"),
        ):
            from backend.app.backstage.scheduler import _run_bulk_set_price_refresh
            _run_bulk_set_price_refresh()

        run_id_arg = mock_finish.call_args[0][1]
        self.assertEqual(run_id_arg, 42)

    # ── test 4: finish_run(error) when an exception is raised ────────────────

    def test_finish_run_error_when_get_settings_raises(self):
        with (
            patch("backend.app.backstage.scheduler.SessionLocal", _mock_session_local()),
            patch("backend.app.backstage.scheduler.get_settings", side_effect=RuntimeError("cfg")),
            patch("backend.app.backstage.scheduler.start_run", return_value=1),
            patch("backend.app.backstage.scheduler.finish_run") as mock_finish,
            patch("backend.app.backstage.scheduler.prune_old_runs"),
        ):
            from backend.app.backstage.scheduler import _run_bulk_set_price_refresh
            _run_bulk_set_price_refresh()

        mock_finish.assert_called_once()
        self.assertEqual(mock_finish.call_args[1]["status"], "error")

    # ── test 5: finish_run still called even when early return (no work done) ─

    def test_finish_run_still_called_on_early_return(self):
        """finish_run must be called even when we take the early-return path."""
        with (
            patch("backend.app.backstage.scheduler.SessionLocal", _mock_session_local()),
            patch("backend.app.backstage.scheduler.get_settings", return_value=_empty_settings()),
            patch("backend.app.backstage.scheduler.start_run", return_value=1),
            patch("backend.app.backstage.scheduler.finish_run") as mock_finish,
            patch("backend.app.backstage.scheduler.prune_old_runs"),
        ):
            from backend.app.backstage.scheduler import _run_bulk_set_price_refresh
            _run_bulk_set_price_refresh()

        self.assertEqual(mock_finish.call_count, 1)

    # ── test 6: prune_old_runs is called with JOB_BULK_REFRESH ───────────────

    def test_prune_old_runs_called_with_bulk_refresh_job_name(self):
        with (
            patch("backend.app.backstage.scheduler.SessionLocal", _mock_session_local()),
            patch("backend.app.backstage.scheduler.get_settings", return_value=_empty_settings()),
            patch("backend.app.backstage.scheduler.start_run", return_value=1),
            patch("backend.app.backstage.scheduler.finish_run"),
            patch("backend.app.backstage.scheduler.prune_old_runs") as mock_prune,
        ):
            from backend.app.backstage.scheduler import _run_bulk_set_price_refresh
            _run_bulk_set_price_refresh()

        from backend.app.services.scheduler_run_log_service import JOB_BULK_REFRESH
        mock_prune.assert_called_once()
        self.assertEqual(mock_prune.call_args[0][1], JOB_BULK_REFRESH)


if __name__ == "__main__":
    unittest.main()
