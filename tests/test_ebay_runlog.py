"""
tests/test_ebay_runlog.py

TDD: _run_ebay_ingestion() must call start_run/finish_run/prune_old_runs on
EVERY exit path — including early-return "skipped" paths where no actual
ingestion happens (disabled, budget_exhausted).

Before this fix, start_run was conditional (only called after budget checks),
so disabled/skipped runs produced zero DB rows and showed as "never_run" in
/admin/stats despite the job executing.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch


def _mock_sl():
    sl = MagicMock()
    sl.return_value.__enter__ = MagicMock(return_value=MagicMock())
    sl.return_value.__exit__ = MagicMock(return_value=False)
    return sl


def _settings(*, enabled=True, app_id="aid", cert_id="cid", budget=100, max_calls=50):
    s = MagicMock()
    s.ebay_scheduled_ingest_enabled = enabled
    s.ebay_app_id = app_id
    s.ebay_cert_id = cert_id
    s.ebay_daily_budget_limit = budget
    s.ebay_max_calls_per_run = max_calls
    return s


class TestEbayRunLogDisabledPath(unittest.TestCase):
    """When ebay_scheduled_ingest_enabled=False, run_log must still be written."""

    def _run(self):
        with (
            patch("backend.app.backstage.scheduler.SessionLocal", _mock_sl()),
            patch("backend.app.backstage.scheduler.get_settings", return_value=_settings(enabled=False)),
            patch("backend.app.backstage.scheduler.start_run", return_value=3) as mock_start,
            patch("backend.app.backstage.scheduler.finish_run") as mock_finish,
            patch("backend.app.backstage.scheduler.prune_old_runs") as mock_prune,
        ):
            from backend.app.backstage.scheduler import _run_ebay_ingestion
            _run_ebay_ingestion()
        return mock_start, mock_finish, mock_prune

    def test_start_run_called_when_disabled(self):
        mock_start, _, _ = self._run()
        mock_start.assert_called_once()

    def test_finish_run_called_when_disabled(self):
        _, mock_finish, _ = self._run()
        mock_finish.assert_called_once()

    def test_prune_called_when_disabled(self):
        _, _, mock_prune = self._run()
        from backend.app.services.scheduler_run_log_service import JOB_EBAY
        mock_prune.assert_called_once()
        self.assertEqual(mock_prune.call_args[0][1], JOB_EBAY)


class TestEbayRunLogBudgetExhaustedPath(unittest.TestCase):
    """When daily budget is 0, run_log must still be written."""

    def _run(self):
        # Session returns empty asset list so calls_today=0, budget=0 → effective_limit=0
        session_mock = MagicMock()
        session_mock.scalars.return_value.all.return_value = []

        sl = MagicMock()
        sl.return_value.__enter__ = MagicMock(return_value=session_mock)
        sl.return_value.__exit__ = MagicMock(return_value=False)

        with (
            patch("backend.app.backstage.scheduler.SessionLocal", sl),
            patch("backend.app.backstage.scheduler.get_settings", return_value=_settings(budget=0)),
            patch("backend.app.backstage.scheduler.start_run", return_value=3) as mock_start,
            patch("backend.app.backstage.scheduler.finish_run") as mock_finish,
            patch("backend.app.backstage.scheduler.prune_old_runs") as mock_prune,
        ):
            from backend.app.backstage.scheduler import _run_ebay_ingestion
            _run_ebay_ingestion()
        return mock_start, mock_finish, mock_prune

    def test_start_run_called_when_budget_exhausted(self):
        mock_start, _, _ = self._run()
        mock_start.assert_called_once()

    def test_finish_run_called_when_budget_exhausted(self):
        _, mock_finish, _ = self._run()
        mock_finish.assert_called_once()

    def test_prune_called_when_budget_exhausted(self):
        _, _, mock_prune = self._run()
        mock_prune.assert_called_once()


class TestEbayRunLogExceptionErrorMessage(unittest.TestCase):
    """When an exception fires in the eBay ingestion body, finish_run must be
    called with error_message set (not just errors=0 and no message).
    (Codex finding #2)"""

    def _run(self):
        # Counter to let the first SessionLocal call (start_run) succeed,
        # then raise on the second call (the inner work session).
        _call_n: list[int] = [0]

        def _sl_factory():
            _call_n[0] += 1
            if _call_n[0] == 2:
                raise RuntimeError("DB down during ingestion")
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=MagicMock())
            ctx.__exit__ = MagicMock(return_value=False)
            return ctx

        sl = MagicMock(side_effect=_sl_factory)

        with (
            patch("backend.app.backstage.scheduler.SessionLocal", sl),
            patch("backend.app.backstage.scheduler.get_settings",
                  return_value=_settings(enabled=True)),
            patch("backend.app.backstage.scheduler.start_run", return_value=5) as mock_start,
            patch("backend.app.backstage.scheduler.finish_run") as mock_finish,
            patch("backend.app.backstage.scheduler.prune_old_runs") as mock_prune,
        ):
            from backend.app.backstage.scheduler import _run_ebay_ingestion
            _run_ebay_ingestion()
        return mock_start, mock_finish, mock_prune

    def test_finish_run_carries_error_message_on_exception(self):
        _, mock_finish, _ = self._run()
        mock_finish.assert_called_once()
        _, kwargs = mock_finish.call_args
        self.assertIsNotNone(kwargs.get("error_message"),
                             "finish_run must be called with error_message when an exception occurs")


if __name__ == "__main__":
    unittest.main()
