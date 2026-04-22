"""
tests/test_discord_alerting.py

Covers:
  a. send_discord_alert — webhook not configured (None / empty)
  b. send_discord_alert — successful HTTP request
  c. send_discord_alert — httpx exception does not propagate
  d. Kill switch: signal_sweep_enabled=False skips sweep entirely
  e. Kill switch: retry_pass_enabled=False skips retry pass
  f. _is_first_successful_sweep — count 1 → True, count 0/N → False
  g. Excessive-output alert fires when total > 500
  h. First-run success alert fires exactly on count==1
  i. _send_heartbeat — no recent runs → warning alert
  j. _send_heartbeat — recent runs → heartbeat sent
  k. _send_heartbeat — observation mode → always sends
  l. _send_heartbeat — normal mode, minute >= 10 → skips
"""
from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch


# ── helpers ───────────────────────────────────────────────────────────────────

def _fake_settings(**overrides):
    defaults = dict(
        discord_alert_webhook_url="https://discord.com/api/webhooks/TEST",
        signal_sweep_enabled=True,
        retry_pass_enabled=True,
        alert_heartbeat_enabled=True,
        deploy_observation_mode_until=None,
        signal_sweep_alert_threshold=5000,
        ebay_scheduled_ingest_enabled=False,
        ebay_app_id="",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ── a/b/c. send_discord_alert ─────────────────────────────────────────────────

class TestSendDiscordAlert(unittest.TestCase):
    def _call(self, level="info", title="Test", body="", settings=None):
        from backend.app.alerting.discord import send_discord_alert
        return send_discord_alert(level, title, body, settings=settings)

    def test_no_webhook_url_returns_false_no_exception(self):
        settings = SimpleNamespace(discord_alert_webhook_url=None)
        result = self._call(settings=settings)
        self.assertFalse(result)

    def test_empty_webhook_url_returns_false(self):
        settings = SimpleNamespace(discord_alert_webhook_url="")
        result = self._call(settings=settings)
        self.assertFalse(result)

    def test_successful_post_returns_true(self):
        settings = SimpleNamespace(discord_alert_webhook_url="https://example.com/webhook")
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        with patch("backend.app.alerting.discord.httpx.post", return_value=mock_resp) as mock_post:
            result = self._call(settings=settings, title="Hello", body="World")
        self.assertTrue(result)
        mock_post.assert_called_once()
        # Verify URL is NOT in the log (not tested here, but content is correct)
        payload = mock_post.call_args.kwargs["json"]["content"]
        self.assertIn("Hello", payload)
        self.assertIn("World", payload)

    def test_httpx_exception_returns_false_no_reraise(self):
        import httpx
        settings = SimpleNamespace(discord_alert_webhook_url="https://example.com/webhook")
        with patch("backend.app.alerting.discord.httpx.post", side_effect=httpx.ConnectError("refused")):
            result = self._call(settings=settings)
        self.assertFalse(result)

    def test_http_status_error_returns_false(self):
        import httpx
        settings = SimpleNamespace(discord_alert_webhook_url="https://example.com/webhook")
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "400", request=MagicMock(), response=MagicMock(status_code=400)
        )
        with patch("backend.app.alerting.discord.httpx.post", return_value=mock_resp):
            result = self._call(settings=settings)
        self.assertFalse(result)

    def test_body_truncated_to_1800_chars(self):
        settings = SimpleNamespace(discord_alert_webhook_url="https://example.com/webhook")
        long_body = "x" * 3000
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        with patch("backend.app.alerting.discord.httpx.post", return_value=mock_resp) as mock_post:
            self._call(settings=settings, body=long_body)
        content = mock_post.call_args.kwargs["json"]["content"]
        self.assertLessEqual(len(content), 2100)  # emoji + title + 1800 body + fences

    def test_webhook_url_not_in_error_log(self):
        """The webhook URL must not appear in log output — credential safety."""
        import httpx
        secret_url = "https://discord.com/api/webhooks/SECRET_TOKEN_HERE"
        settings = SimpleNamespace(discord_alert_webhook_url=secret_url)
        with patch("backend.app.alerting.discord.httpx.post",
                   side_effect=httpx.ConnectError("refused")):
            with self.assertLogs("backend.app.alerting.discord", level="ERROR") as cm:
                self._call(settings=settings)
        # The secret URL must not appear in any log record
        for record in cm.output:
            self.assertNotIn("SECRET_TOKEN_HERE", record)


# ── d/e. Kill switches ────────────────────────────────────────────────────────

class TestKillSwitches(unittest.TestCase):
    def _run_sweep(self, enabled: bool):
        s = _fake_settings(signal_sweep_enabled=enabled, discord_alert_webhook_url=None)
        with (
            patch("backend.app.backstage.scheduler.get_settings", return_value=s),
            patch("backend.app.backstage.scheduler.sweep_signals") as mock_sweep,
            patch("backend.app.backstage.scheduler.SessionLocal"),
            patch("backend.app.backstage.scheduler.start_run", return_value=1),
            patch("backend.app.backstage.scheduler.finish_run"),
            patch("backend.app.backstage.scheduler.prune_old_runs"),
        ):
            from backend.app.backstage.scheduler import _run_signal_sweep
            _run_signal_sweep()
            return mock_sweep

    def test_signal_sweep_kill_switch_prevents_sweep(self):
        mock_sweep = self._run_sweep(enabled=False)
        mock_sweep.assert_not_called()

    def test_signal_sweep_enabled_calls_sweep(self):
        mock_sweep = self._run_sweep(enabled=True)
        mock_sweep.assert_called_once()

    def test_retry_pass_kill_switch_prevents_execution(self):
        s = _fake_settings(retry_pass_enabled=False)
        with (
            patch("backend.app.backstage.scheduler.get_settings", return_value=s),
            patch("backend.app.backstage.scheduler.run_retry_pass") as mock_retry,
            patch("backend.app.backstage.scheduler.SessionLocal"),
            patch("backend.app.backstage.scheduler.start_run", return_value=1),
        ):
            from backend.app.backstage.scheduler import _run_retry_pass
            _run_retry_pass()
        mock_retry.assert_not_called()


# ── f. _is_first_successful_sweep ────────────────────────────────────────────

class TestIsFirstSuccessfulSweep(unittest.TestCase):
    def _call(self, count: int) -> bool:
        from backend.app.backstage.scheduler import _is_first_successful_sweep
        mock_session = MagicMock()
        mock_session.execute.return_value.scalar.return_value = count
        return _is_first_successful_sweep(mock_session)

    def test_count_1_is_first(self):
        self.assertTrue(self._call(1))

    def test_count_0_not_first(self):
        self.assertFalse(self._call(0))

    def test_count_10_not_first(self):
        self.assertFalse(self._call(10))


# ── g. Excessive-output alert ─────────────────────────────────────────────────

class TestExcessiveOutputAlert(unittest.TestCase):
    def _run_sweep_with_total(self, total: int):
        from backend.app.services.signal_service import SweepResult
        r = SweepResult(total=total, breakout=1, move=2, watch=1, idle=1, insufficient_data=total-5)

        s = _fake_settings()
        with (
            patch("backend.app.backstage.scheduler.get_settings", return_value=s),
            patch("backend.app.backstage.scheduler.sweep_signals", return_value=r),
            patch("backend.app.backstage.scheduler.SessionLocal") as mock_sl,
            patch("backend.app.backstage.scheduler.start_run", return_value=1),
            patch("backend.app.backstage.scheduler.finish_run"),
            patch("backend.app.backstage.scheduler.prune_old_runs"),
            patch("backend.app.backstage.scheduler._is_first_successful_sweep", return_value=False),
            patch("backend.app.backstage.scheduler.send_discord_alert") as mock_alert,
        ):
            mock_sl.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)
            from backend.app.backstage.scheduler import _run_signal_sweep
            _run_signal_sweep()
        return mock_alert

    def test_over_threshold_triggers_warning(self):
        mock_alert = self._run_sweep_with_total(5001)
        warning_calls = [c for c in mock_alert.call_args_list if c.args[0] == "warning"]
        self.assertEqual(len(warning_calls), 1)
        self.assertIn("异常", warning_calls[0].args[1])

    def test_under_threshold_no_warning(self):
        mock_alert = self._run_sweep_with_total(2300)
        warning_calls = [c for c in mock_alert.call_args_list if c.args[0] == "warning"]
        self.assertEqual(len(warning_calls), 0)


# ── h. First-run success alert ────────────────────────────────────────────────

class TestFirstRunAlert(unittest.TestCase):
    def _run_sweep_first_flag(self, is_first: bool):
        from backend.app.services.signal_service import SweepResult
        r = SweepResult(total=50, breakout=2, move=5, watch=3, idle=4, insufficient_data=36)

        s = _fake_settings()
        with (
            patch("backend.app.backstage.scheduler.get_settings", return_value=s),
            patch("backend.app.backstage.scheduler.sweep_signals", return_value=r),
            patch("backend.app.backstage.scheduler.SessionLocal") as mock_sl,
            patch("backend.app.backstage.scheduler.start_run", return_value=1),
            patch("backend.app.backstage.scheduler.finish_run"),
            patch("backend.app.backstage.scheduler.prune_old_runs"),
            patch("backend.app.backstage.scheduler._is_first_successful_sweep", return_value=is_first),
            patch("backend.app.backstage.scheduler.send_discord_alert") as mock_alert,
        ):
            mock_sl.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)
            from backend.app.backstage.scheduler import _run_signal_sweep
            _run_signal_sweep()
        return mock_alert

    def test_first_run_sends_success_alert(self):
        mock_alert = self._run_sweep_first_flag(is_first=True)
        success_calls = [c for c in mock_alert.call_args_list if c.args[0] == "success"]
        self.assertEqual(len(success_calls), 1)
        self.assertIn("首次", success_calls[0].args[1])

    def test_subsequent_run_no_success_alert(self):
        mock_alert = self._run_sweep_first_flag(is_first=False)
        success_calls = [c for c in mock_alert.call_args_list if c.args[0] == "success"]
        self.assertEqual(len(success_calls), 0)


# ── i/j/k/l. _send_heartbeat ─────────────────────────────────────────────────

class TestSendHeartbeat(unittest.TestCase):
    def _call_heartbeat(self, *, now: datetime, db_rows=None, settings_overrides=None):
        s = _fake_settings(**(settings_overrides or {}))
        if db_rows is None:
            # default: one success row in the last hour
            row = SimpleNamespace(status="success", cnt=4, last_run=now - timedelta(minutes=5))
            db_rows = [row]

        mock_result = MagicMock()
        mock_result.fetchall.return_value = db_rows

        with (
            patch("backend.app.backstage.scheduler.get_settings", return_value=s),
            patch("backend.app.backstage.scheduler.SessionLocal") as mock_sl,
            patch("backend.app.backstage.scheduler.send_discord_alert") as mock_alert,
        ):
            mock_session = MagicMock()
            mock_session.execute.return_value = mock_result
            mock_sl.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)

            with patch("backend.app.backstage.scheduler.datetime") as mock_dt:
                mock_dt.now.return_value = now
                mock_dt.fromisoformat = datetime.fromisoformat
                from backend.app.backstage.scheduler import _send_heartbeat
                _send_heartbeat()

        return mock_alert

    def test_no_recent_runs_sends_warning(self):
        now = datetime(2026, 4, 19, 12, 5, 0, tzinfo=UTC)  # minute=5, normal mode
        mock_alert = self._call_heartbeat(now=now, db_rows=[])
        warning_calls = [c for c in mock_alert.call_args_list if c.args[0] == "warning"]
        self.assertEqual(len(warning_calls), 1)

    def test_recent_runs_sends_heartbeat(self):
        now = datetime(2026, 4, 19, 12, 5, 0, tzinfo=UTC)
        mock_alert = self._call_heartbeat(now=now)
        hb_calls = [c for c in mock_alert.call_args_list if c.args[0] == "heartbeat"]
        self.assertEqual(len(hb_calls), 1)

    def test_observation_mode_always_sends(self):
        # minute=30 — normally skipped, but observation mode forces send
        now = datetime(2026, 4, 19, 12, 30, 0, tzinfo=UTC)
        obs_until = (now + timedelta(hours=2)).isoformat()
        mock_alert = self._call_heartbeat(
            now=now,
            settings_overrides={"deploy_observation_mode_until": obs_until},
        )
        self.assertTrue(mock_alert.called)

    def test_normal_mode_minute_above_10_skips(self):
        now = datetime(2026, 4, 19, 12, 30, 0, tzinfo=UTC)  # minute=30
        mock_alert = self._call_heartbeat(now=now)
        self.assertFalse(mock_alert.called)

    def test_normal_mode_minute_under_10_sends(self):
        now = datetime(2026, 4, 19, 12, 5, 0, tzinfo=UTC)  # minute=5
        mock_alert = self._call_heartbeat(now=now)
        self.assertTrue(mock_alert.called)

    def test_naive_observation_until_treated_as_utc(self):
        # A naive ISO string (no timezone suffix) must be treated as UTC,
        # not crash with TypeError on the aware-vs-naive comparison.
        now = datetime(2026, 4, 19, 12, 30, 0, tzinfo=UTC)  # minute=30, normally skipped
        obs_until = "2026-04-19T15:00:00"  # naive, 2.5 h in the future if read as UTC
        mock_alert = self._call_heartbeat(
            now=now,
            settings_overrides={"deploy_observation_mode_until": obs_until},
        )
        self.assertTrue(mock_alert.called)

    def test_heartbeat_disabled_skips_all(self):
        now = datetime(2026, 4, 19, 12, 5, 0, tzinfo=UTC)
        mock_alert = self._call_heartbeat(
            now=now,
            settings_overrides={"alert_heartbeat_enabled": False},
        )
        self.assertFalse(mock_alert.called)

    def test_observation_tag_in_title(self):
        now = datetime(2026, 4, 19, 12, 5, 0, tzinfo=UTC)
        obs_until = (now + timedelta(hours=1)).isoformat()
        mock_alert = self._call_heartbeat(
            now=now,
            settings_overrides={"deploy_observation_mode_until": obs_until},
        )
        hb_calls = [c for c in mock_alert.call_args_list if c.args[0] == "heartbeat"]
        self.assertTrue(any("观察期" in c.args[1] for c in hb_calls))


if __name__ == "__main__":
    unittest.main()
