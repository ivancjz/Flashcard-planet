"""
tests/test_heartbeat_runlog.py

TDD: _send_heartbeat() must call start_run/finish_run/prune_old_runs on every
execution path, including the no-op early-return paths (disabled, outside the
hourly send window). This makes "heartbeat is running but not in send window"
distinguishable from "heartbeat is not running at all" in /admin/stats.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch
from datetime import UTC, datetime


def _mock_sl():
    sl = MagicMock()
    sl.return_value.__enter__ = MagicMock(return_value=MagicMock())
    sl.return_value.__exit__ = MagicMock(return_value=False)
    return sl


def _settings(*, enabled=True, obs_until=None):
    s = MagicMock()
    s.alert_heartbeat_enabled = enabled
    s.deploy_observation_mode_until = obs_until
    s.ebay_scheduled_ingest_enabled = False
    s.ebay_app_id = ""
    s.ebay_cert_id = ""
    return s


class TestHeartbeatRunLogDisabled(unittest.TestCase):
    """When alert_heartbeat_enabled=False, run_log must still be written."""

    def _run(self):
        with (
            patch("backend.app.backstage.scheduler.SessionLocal", _mock_sl()),
            patch("backend.app.backstage.scheduler.get_settings", return_value=_settings(enabled=False)),
            patch("backend.app.backstage.scheduler.start_run", return_value=9) as mock_start,
            patch("backend.app.backstage.scheduler.finish_run") as mock_finish,
            patch("backend.app.backstage.scheduler.prune_old_runs") as mock_prune,
        ):
            from backend.app.backstage.scheduler import _send_heartbeat
            _send_heartbeat()
        return mock_start, mock_finish, mock_prune

    def test_start_run_called_when_disabled(self):
        mock_start, _, _ = self._run()
        mock_start.assert_called_once()

    def test_finish_run_called_when_disabled(self):
        _, mock_finish, _ = self._run()
        mock_finish.assert_called_once()

    def test_prune_called_when_disabled(self):
        _, _, mock_prune = self._run()
        mock_prune.assert_called_once()


class TestHeartbeatRunLogNoopWindow(unittest.TestCase):
    """When in the no-op window (minute >= 10, not observation mode),
    run_log must still be written."""

    def _run(self):
        # minute=30 → outside send window → early return
        now = datetime(2026, 4, 22, 10, 30, 0, tzinfo=UTC)
        with (
            patch("backend.app.backstage.scheduler.SessionLocal", _mock_sl()),
            patch("backend.app.backstage.scheduler.get_settings", return_value=_settings()),
            patch("backend.app.backstage.scheduler.start_run", return_value=9) as mock_start,
            patch("backend.app.backstage.scheduler.finish_run") as mock_finish,
            patch("backend.app.backstage.scheduler.prune_old_runs") as mock_prune,
            patch("backend.app.backstage.scheduler.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = now
            mock_dt.fromisoformat.side_effect = datetime.fromisoformat
            from backend.app.backstage.scheduler import _send_heartbeat
            _send_heartbeat()
        return mock_start, mock_finish, mock_prune

    def test_start_run_called_in_noop_window(self):
        mock_start, _, _ = self._run()
        mock_start.assert_called_once()

    def test_finish_run_called_in_noop_window(self):
        _, mock_finish, _ = self._run()
        mock_finish.assert_called_once()

    def test_prune_called_in_noop_window(self):
        _, _, mock_prune = self._run()
        mock_prune.assert_called_once()


class TestHeartbeatRunLogException(unittest.TestCase):
    """When an exception occurs inside _send_heartbeat, finish_run must be called
    with status='error', not 'success'.  (Codex finding #1)"""

    def _run(self):
        with (
            patch("backend.app.backstage.scheduler.SessionLocal", _mock_sl()),
            patch("backend.app.backstage.scheduler.get_settings", return_value=_settings()),
            patch("backend.app.backstage.scheduler.start_run", return_value=9) as mock_start,
            patch("backend.app.backstage.scheduler.finish_run") as mock_finish,
            patch("backend.app.backstage.scheduler.prune_old_runs") as mock_prune,
            patch("backend.app.backstage.scheduler.datetime") as mock_dt,
        ):
            # datetime.now() raises — simulates DB or Discord failure mid-body
            mock_dt.now.side_effect = RuntimeError("clock exploded")
            mock_dt.fromisoformat.side_effect = datetime.fromisoformat
            from backend.app.backstage.scheduler import _send_heartbeat
            with self.assertRaises(RuntimeError):
                _send_heartbeat()
        return mock_start, mock_finish, mock_prune

    def test_finish_run_called_with_error_status_on_exception(self):
        _, mock_finish, _ = self._run()
        mock_finish.assert_called_once()
        _, kwargs = mock_finish.call_args
        self.assertEqual(kwargs.get("status"), "error")

    def test_prune_called_even_on_exception(self):
        _, _, mock_prune = self._run()
        mock_prune.assert_called_once()


class TestHeartbeatRunLogMeta(unittest.TestCase):
    """No-op paths (disabled, outside window) should write meta_json so
    /admin/stats can distinguish 'heartbeat skipped this tick' from 'success'.
    (Codex finding #4)"""

    def test_finish_run_has_meta_when_disabled(self):
        with (
            patch("backend.app.backstage.scheduler.SessionLocal", _mock_sl()),
            patch("backend.app.backstage.scheduler.get_settings", return_value=_settings(enabled=False)),
            patch("backend.app.backstage.scheduler.start_run", return_value=9),
            patch("backend.app.backstage.scheduler.finish_run") as mock_finish,
            patch("backend.app.backstage.scheduler.prune_old_runs"),
        ):
            from backend.app.backstage.scheduler import _send_heartbeat
            _send_heartbeat()
        _, kwargs = mock_finish.call_args
        meta = kwargs.get("meta_json") or {}
        self.assertIn("skipped_reason", meta)

    def test_finish_run_has_meta_in_noop_window(self):
        now = datetime(2026, 4, 22, 10, 30, 0, tzinfo=UTC)
        with (
            patch("backend.app.backstage.scheduler.SessionLocal", _mock_sl()),
            patch("backend.app.backstage.scheduler.get_settings", return_value=_settings()),
            patch("backend.app.backstage.scheduler.start_run", return_value=9),
            patch("backend.app.backstage.scheduler.finish_run") as mock_finish,
            patch("backend.app.backstage.scheduler.prune_old_runs"),
            patch("backend.app.backstage.scheduler.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = now
            mock_dt.fromisoformat.side_effect = datetime.fromisoformat
            from backend.app.backstage.scheduler import _send_heartbeat
            _send_heartbeat()
        _, kwargs = mock_finish.call_args
        meta = kwargs.get("meta_json") or {}
        self.assertIn("skipped_reason", meta)


if __name__ == "__main__":
    unittest.main()
