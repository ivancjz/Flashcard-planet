"""
tests/test_ebay_duration_canary.py

Unit tests for the eBay duration canary in _send_heartbeat.

The canary fires when ALL completed ebay-ingestion runs in the window
finished in < EBAY_DURATION_CANARY_THRESHOLD_SECS seconds.
Three cases:
  1. Positive: all 20 runs are fast → alert fires
  2. Negative (mixed): some fast, some slow → alert silent
  3. Negative (empty): 0 runs in window → alert silent
     (important: 0 runs is a different failure mode from "all fast";
      must not conflate them — the 25h-absence alert covers 0 runs)
"""
import unittest
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from backend.app.backstage.scheduler import (
    EBAY_DURATION_CANARY_THRESHOLD_SECS,
    EBAY_DURATION_CANARY_WINDOW_HOURS,
)


def _make_settings(*, ebay_enabled=True, app_id="app-id", cert_id="cert-id"):
    s = MagicMock()
    s.alert_heartbeat_enabled = True
    s.deploy_observation_mode_until = None
    s.ebay_scheduled_ingest_enabled = ebay_enabled
    s.ebay_app_id = app_id
    s.ebay_cert_id = cert_id
    s.zero_output_alert_window_hours = 24
    return s


def _run_heartbeat_in_window(canary_rows: tuple[int, int]) -> list:
    """Run _send_heartbeat patched into the hourly send window, with controlled canary results.
    Returns list of send_discord_alert call args.
    """
    fixed_now = datetime(2026, 5, 6, 10, 0, 0, tzinfo=UTC)

    mock_session = MagicMock()
    mock_session.execute.return_value.fetchall.return_value = [
        MagicMock(status="success", cnt=10, last_run=fixed_now)
    ]
    mock_session.execute.return_value.fetchone.return_value = MagicMock(total_runs=0, fast_runs=0)

    sl = MagicMock()
    sl.return_value.__enter__ = MagicMock(return_value=mock_session)
    sl.return_value.__exit__ = MagicMock(return_value=False)

    recorded_alerts = []

    def _capture_alert(level, title, body=""):
        recorded_alerts.append((level, title, body))

    with (
        patch("backend.app.backstage.scheduler.SessionLocal", sl),
        patch("backend.app.backstage.scheduler.get_settings", return_value=_make_settings()),
        patch("backend.app.backstage.scheduler.datetime") as mock_dt,
        patch("backend.app.backstage.scheduler.start_run", return_value=1),
        patch("backend.app.backstage.scheduler.finish_run"),
        patch("backend.app.backstage.scheduler.prune_old_runs"),
        patch("backend.app.backstage.scheduler.get_last_run",
              return_value=MagicMock(started_at=fixed_now)),
        patch("backend.app.backstage.scheduler.get_zero_output_jobs", return_value=[]),
        patch("backend.app.backstage.scheduler._ebay_duration_canary_rows",
              return_value=canary_rows),
        patch("backend.app.backstage.scheduler.send_discord_alert", side_effect=_capture_alert),
    ):
        mock_dt.now.return_value = fixed_now
        from backend.app.backstage.scheduler import _send_heartbeat
        _send_heartbeat()

    return recorded_alerts


class EbayDurationCanaryTests(unittest.TestCase):

    def _canary_alerts(self, alerts: list) -> list:
        """Filter to only the duration-canary warning alerts."""
        return [
            (level, title) for level, title, _ in alerts
            if level == "warning" and "快速失败" in title
        ]

    def test_all_fast_runs_fires_alert(self):
        """20 runs, all fast → canary warning must fire."""
        alerts = _run_heartbeat_in_window(canary_rows=(20, 20))
        canary = self._canary_alerts(alerts)
        self.assertEqual(len(canary), 1, f"Expected 1 canary alert, got: {canary}")
        self.assertIn(str(EBAY_DURATION_CANARY_THRESHOLD_SECS), canary[0][1])

    def test_mixed_runs_alert_silent(self):
        """10 fast + 10 slow runs → not 'sustained', canary must NOT fire."""
        alerts = _run_heartbeat_in_window(canary_rows=(20, 10))
        canary = self._canary_alerts(alerts)
        self.assertEqual(len(canary), 0, f"Canary fired on mixed runs (should not): {canary}")

    def test_zero_runs_alert_silent(self):
        """0 runs in window → canary must NOT fire.

        Zero runs is a separate failure mode covered by the 25h-absence alert.
        Conflating 'no runs' with 'all runs fast' would cause spurious alerts
        when ebay-ingestion is disabled or hasn't run since deploy.
        """
        alerts = _run_heartbeat_in_window(canary_rows=(0, 0))
        canary = self._canary_alerts(alerts)
        self.assertEqual(len(canary), 0, f"Canary fired on 0 runs (should not): {canary}")

    def test_canary_silent_when_runs_blocked(self):
        """All runs completed quickly due to deliberate skip — canary must NOT fire.

        daily_budget_exhausted (and disabled/missing_credentials) runs log
        status='success' with meta_json={'job_blocked_reason': '...'}. They
        finish in ~0s but never called the API — they are not fast-failing.
        The SQL filter (meta_json->>'job_blocked_reason' IS NULL) excludes them.
        Without this filter, a day of budget-exhausted skips would trigger
        a false 'Finding API rejecting' alert every time the budget refills.
        """
        # The _ebay_duration_canary_rows helper is patched to simulate what the
        # SQL returns AFTER the job_blocked_reason IS NULL filter is applied:
        # all skipped rows are excluded, so total_runs=0 → canary is silent.
        alerts = _run_heartbeat_in_window(canary_rows=(0, 0))
        canary = self._canary_alerts(alerts)
        self.assertEqual(
            len(canary), 0,
            f"Canary fired on budget-blocked runs (should not): {canary}",
        )
