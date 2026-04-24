"""
tests/test_start_run_guard.py

When start_run() raises, each scheduler job must:
  1. Send a Discord alert with level="error"
  2. NOT execute the main job logic (sweep_signals, ingest, etc.)
  3. Return cleanly (no re-raise)

Covers all 7 jobs that call start_run().
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch


def _mock_sl() -> MagicMock:
    """SessionLocal context-manager mock."""
    sl = MagicMock()
    sl.return_value.__enter__ = MagicMock(return_value=MagicMock())
    sl.return_value.__exit__ = MagicMock(return_value=False)
    return sl


def _start_run_raises() -> MagicMock:
    return MagicMock(side_effect=RuntimeError("DB pool exhausted"))


class TestSignalSweepStartRunGuard(unittest.TestCase):
    def _run(self):
        settings = MagicMock()
        settings.signal_sweep_enabled = True
        settings.signal_sweep_alert_threshold = 9999
        with (
            patch("backend.app.backstage.scheduler.SessionLocal", _mock_sl()),
            patch("backend.app.backstage.scheduler.get_settings", return_value=settings),
            patch("backend.app.backstage.scheduler.start_run", _start_run_raises()),
            patch("backend.app.backstage.scheduler.send_discord_alert") as mock_alert,
            patch("backend.app.backstage.scheduler.sweep_signals") as mock_sweep,
        ):
            from backend.app.backstage.scheduler import _run_signal_sweep
            _run_signal_sweep()
        return mock_alert, mock_sweep

    def test_discord_alert_sent(self):
        mock_alert, _ = self._run()
        mock_alert.assert_called_once()

    def test_alert_level_is_error(self):
        mock_alert, _ = self._run()
        level = mock_alert.call_args[0][0]
        self.assertEqual(level, "error")

    def test_sweep_signals_not_called(self):
        _, mock_sweep = self._run()
        mock_sweep.assert_not_called()


class TestRetryPassStartRunGuard(unittest.TestCase):
    def _run(self):
        settings = MagicMock()
        settings.retry_pass_enabled = True
        with (
            patch("backend.app.backstage.scheduler.SessionLocal", _mock_sl()),
            patch("backend.app.backstage.scheduler.get_settings", return_value=settings),
            patch("backend.app.backstage.scheduler.start_run", _start_run_raises()),
            patch("backend.app.backstage.scheduler.send_discord_alert") as mock_alert,
            patch("backend.app.backstage.scheduler.run_retry_pass") as mock_retry,
        ):
            from backend.app.backstage.scheduler import _run_retry_pass
            _run_retry_pass()
        return mock_alert, mock_retry

    def test_discord_alert_sent(self):
        mock_alert, _ = self._run()
        mock_alert.assert_called_once()

    def test_alert_level_is_error(self):
        mock_alert, _ = self._run()
        self.assertEqual(mock_alert.call_args[0][0], "error")

    def test_retry_logic_not_called(self):
        _, mock_retry = self._run()
        mock_retry.assert_not_called()


class TestHeartbeatStartRunGuard(unittest.TestCase):
    def _run(self):
        settings = MagicMock()
        settings.alert_heartbeat_enabled = True
        settings.deploy_observation_mode_until = None
        settings.ebay_scheduled_ingest_enabled = False
        settings.ebay_app_id = ""
        settings.ebay_cert_id = ""
        with (
            patch("backend.app.backstage.scheduler.SessionLocal", _mock_sl()),
            patch("backend.app.backstage.scheduler.get_settings", return_value=settings),
            patch("backend.app.backstage.scheduler.start_run", _start_run_raises()),
            patch("backend.app.backstage.scheduler.send_discord_alert") as mock_alert,
            patch("backend.app.backstage.scheduler.finish_run") as mock_finish,
        ):
            from backend.app.backstage.scheduler import _send_heartbeat
            _send_heartbeat()
        return mock_alert, mock_finish

    def test_discord_alert_sent(self):
        mock_alert, _ = self._run()
        mock_alert.assert_called_once()

    def test_alert_level_is_error(self):
        mock_alert, _ = self._run()
        self.assertEqual(mock_alert.call_args[0][0], "error")

    def test_finish_run_not_called(self):
        # No _run_id was set, so finish_run must not be called
        _, mock_finish = self._run()
        mock_finish.assert_not_called()


class TestBulkRefreshStartRunGuard(unittest.TestCase):
    def _run(self):
        settings = MagicMock()
        settings.bulk_set_id_list = ["base1"]
        with (
            patch("backend.app.backstage.scheduler.SessionLocal", _mock_sl()),
            patch("backend.app.backstage.scheduler.get_settings", return_value=settings),
            patch("backend.app.backstage.scheduler.start_run", _start_run_raises()),
            patch("backend.app.backstage.scheduler.send_discord_alert") as mock_alert,
            patch("backend.app.backstage.scheduler.finish_run") as mock_finish,
        ):
            from backend.app.backstage.scheduler import _run_bulk_set_price_refresh
            _run_bulk_set_price_refresh()
        return mock_alert, mock_finish

    def test_discord_alert_sent(self):
        mock_alert, _ = self._run()
        mock_alert.assert_called_once()

    def test_alert_level_is_error(self):
        mock_alert, _ = self._run()
        self.assertEqual(mock_alert.call_args[0][0], "error")

    def test_finish_run_not_called(self):
        _, mock_finish = self._run()
        mock_finish.assert_not_called()


class TestScheduledIngestionStartRunGuard(unittest.TestCase):
    def _run(self):
        with (
            patch("backend.app.backstage.scheduler.SessionLocal", _mock_sl()),
            patch("backend.app.backstage.scheduler.get_tracked_pokemon_pools", return_value=[]),
            patch("backend.app.backstage.scheduler.get_configured_provider_ingestors", return_value=[]),
            patch("backend.app.backstage.scheduler.start_run", _start_run_raises()),
            patch("backend.app.backstage.scheduler.send_discord_alert") as mock_alert,
            patch("backend.app.backstage.scheduler.finish_run") as mock_finish,
        ):
            from backend.app.backstage.scheduler import _run_scheduled_ingestion
            _run_scheduled_ingestion()
        return mock_alert, mock_finish

    def test_discord_alert_sent(self):
        mock_alert, _ = self._run()
        mock_alert.assert_called_once()

    def test_alert_level_is_error(self):
        mock_alert, _ = self._run()
        self.assertEqual(mock_alert.call_args[0][0], "error")

    def test_finish_run_not_called(self):
        _, mock_finish = self._run()
        mock_finish.assert_not_called()


class TestEbayIngestionStartRunGuard(unittest.TestCase):
    def _run(self):
        settings = MagicMock()
        settings.ebay_scheduled_ingest_enabled = True
        settings.ebay_app_id = "app_id"
        settings.ebay_cert_id = "cert_id"
        settings.ebay_daily_budget_limit = 100
        settings.ebay_max_calls_per_run = 20
        with (
            patch("backend.app.backstage.scheduler.SessionLocal", _mock_sl()),
            patch("backend.app.backstage.scheduler.get_settings", return_value=settings),
            patch("backend.app.backstage.scheduler.start_run", _start_run_raises()),
            patch("backend.app.backstage.scheduler.send_discord_alert") as mock_alert,
            patch("backend.app.backstage.scheduler.finish_run") as mock_finish,
        ):
            from backend.app.backstage.scheduler import _run_ebay_ingestion
            result = _run_ebay_ingestion()
        return mock_alert, mock_finish, result

    def test_discord_alert_sent(self):
        mock_alert, _, _ = self._run()
        mock_alert.assert_called_once()

    def test_alert_level_is_error(self):
        mock_alert, _, _ = self._run()
        self.assertEqual(mock_alert.call_args[0][0], "error")

    def test_finish_run_not_called(self):
        _, mock_finish, _ = self._run()
        mock_finish.assert_not_called()

    def test_returns_failed_summary(self):
        _, _, result = self._run()
        self.assertIsNotNone(result)
        self.assertEqual(result.run_status, "failed")


class TestYgoIngestionStartRunGuard(unittest.TestCase):
    def _run(self):
        with (
            patch("backend.app.backstage.scheduler.SessionLocal", _mock_sl()),
            patch("backend.app.backstage.scheduler.start_run", _start_run_raises()),
            patch("backend.app.backstage.scheduler.send_discord_alert") as mock_alert,
            patch("backend.app.backstage.scheduler.finish_run") as mock_finish,
        ):
            from backend.app.backstage.scheduler import _run_ygo_ingestion
            _run_ygo_ingestion()
        return mock_alert, mock_finish

    def test_discord_alert_sent(self):
        mock_alert, _ = self._run()
        mock_alert.assert_called_once()

    def test_alert_level_is_error(self):
        mock_alert, _ = self._run()
        self.assertEqual(mock_alert.call_args[0][0], "error")

    def test_finish_run_not_called(self):
        _, mock_finish = self._run()
        mock_finish.assert_not_called()


if __name__ == "__main__":
    unittest.main()
