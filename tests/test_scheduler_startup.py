"""
tests/test_scheduler_startup.py

Covers:
  a. prepare_scheduler_for_startup() resumes all 4 jobs with correct stagger
     Jobs in _STARTUP_DELAY: scheduled-ingestion (120s), bulk-set-price-refresh (300s),
     signal-sweep (600s), alert-heartbeat (720s).
     Note: retry-pass is intentionally omitted from _STARTUP_DELAY.
  b. Missing jobs log a warning rather than crashing
  c. _run_signal_sweep writes signal breakdown into meta_json on success
  d. _run_signal_sweep records status='error' when sweep_signals raises
  e. _run_signal_sweep alert threshold — only fires above settings threshold
"""
from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, call, patch


# ── a/b. prepare_scheduler_for_startup ───────────────────────────────────────

class TestPrepareSchedulerForStartup(unittest.TestCase):
    def _make_scheduler(self, registered_job_ids: list[str]) -> MagicMock:
        scheduler = MagicMock()
        scheduler.get_job.side_effect = lambda job_id: (
            MagicMock() if job_id in registered_job_ids else None
        )
        return scheduler

    def _call(self, scheduler, now=None):
        from backend.app.backstage.scheduler import prepare_scheduler_for_startup
        if now is None:
            now = datetime(2026, 4, 19, 12, 0, 0, tzinfo=UTC)
        prepare_scheduler_for_startup(scheduler, now=now)

    def test_all_four_jobs_resumed_when_all_registered(self):
        all_jobs = [
            "scheduled-ingestion",
            "bulk-set-price-refresh",
            "signal-sweep",
            "alert-heartbeat",
        ]
        scheduler = self._make_scheduler(all_jobs)
        self._call(scheduler)

        modified = {c.args[0] for c in scheduler.modify_job.call_args_list}
        self.assertEqual(modified, set(all_jobs))

    def test_first_run_times_are_strictly_increasing(self):
        # New startup order: ingestion(120s) < signal(600s) < heartbeat(720s) < bulk(900s)
        all_jobs = [
            "scheduled-ingestion",
            "bulk-set-price-refresh",
            "signal-sweep",
            "alert-heartbeat",
        ]
        now = datetime(2026, 4, 19, 12, 0, 0, tzinfo=UTC)
        scheduler = self._make_scheduler(all_jobs)
        self._call(scheduler, now=now)

        run_times: dict[str, datetime] = {}
        for c in scheduler.modify_job.call_args_list:
            run_times[c.args[0]] = c.kwargs["next_run_time"]

        # Verify the correct stagger order
        ordered = [
            run_times["scheduled-ingestion"],   # 120s
            run_times["signal-sweep"],           # 600s
            run_times["alert-heartbeat"],        # 720s
            run_times["bulk-set-price-refresh"], # 900s
        ]
        for i in range(len(ordered) - 1):
            self.assertLess(ordered[i], ordered[i + 1])

    def test_ingestion_is_first_bulk_is_last(self):
        # bulk-set-price-refresh moved to 900s to avoid deadlock with ingestion (120s)
        # New order: ingestion(120) < signal(600) < heartbeat(720) < bulk(900)
        all_jobs = [
            "scheduled-ingestion",
            "bulk-set-price-refresh",
            "signal-sweep",
            "alert-heartbeat",
        ]
        now = datetime(2026, 4, 19, 12, 0, 0, tzinfo=UTC)
        scheduler = self._make_scheduler(all_jobs)
        self._call(scheduler, now=now)

        run_times: dict[str, datetime] = {}
        for c in scheduler.modify_job.call_args_list:
            run_times[c.args[0]] = c.kwargs["next_run_time"]

        # ingestion is first
        self.assertLess(run_times["scheduled-ingestion"], run_times["signal-sweep"])
        # bulk is last — after both signal and heartbeat so no INSERT overlap
        self.assertGreater(run_times["bulk-set-price-refresh"], run_times["alert-heartbeat"])
        # heartbeat fires after signal-sweep (receives first sweep result before sending)
        self.assertGreater(run_times["alert-heartbeat"], run_times["signal-sweep"])

    def test_signal_sweep_first_run_is_10_minutes_after_now(self):
        now = datetime(2026, 4, 19, 12, 0, 0, tzinfo=UTC)
        scheduler = self._make_scheduler(["signal-sweep"])
        self._call(scheduler, now=now)

        for c in scheduler.modify_job.call_args_list:
            if c.args[0] == "signal-sweep":
                expected = now + timedelta(seconds=600)
                self.assertEqual(c.kwargs["next_run_time"], expected)
                return
        self.fail("signal-sweep was not modified")

    def test_alert_heartbeat_first_run_is_12_minutes_after_now(self):
        now = datetime(2026, 4, 19, 12, 0, 0, tzinfo=UTC)
        scheduler = self._make_scheduler(["alert-heartbeat"])
        self._call(scheduler, now=now)

        for c in scheduler.modify_job.call_args_list:
            if c.args[0] == "alert-heartbeat":
                expected = now + timedelta(seconds=720)
                self.assertEqual(c.kwargs["next_run_time"], expected)
                return
        self.fail("alert-heartbeat was not modified")

    def test_missing_job_does_not_raise(self):
        # Only ingestion registered, the other three are absent
        scheduler = self._make_scheduler(["scheduled-ingestion"])
        try:
            self._call(scheduler)
        except Exception as exc:
            self.fail(f"prepare_scheduler_for_startup raised unexpectedly: {exc}")

    def test_missing_job_logs_warning(self):
        scheduler = self._make_scheduler(["scheduled-ingestion"])
        with self.assertLogs("backend.app.backstage.scheduler", level="WARNING") as cm:
            self._call(scheduler)
        missing_warnings = [m for m in cm.output if "not found" in m]
        # bulk-set-price-refresh, signal-sweep, alert-heartbeat are all absent
        self.assertGreaterEqual(len(missing_warnings), 3)

    def test_no_jobs_registered_does_not_raise(self):
        scheduler = self._make_scheduler([])
        try:
            self._call(scheduler)
        except Exception as exc:
            self.fail(f"prepare_scheduler_for_startup raised unexpectedly: {exc}")

    def test_modify_job_called_only_for_registered_jobs(self):
        # Only signal-sweep is registered
        scheduler = self._make_scheduler(["signal-sweep"])
        self._call(scheduler)
        modified_ids = [c.args[0] for c in scheduler.modify_job.call_args_list]
        self.assertEqual(modified_ids, ["signal-sweep"])


# ── c. _run_signal_sweep writes meta_json on success ─────────────────────────

class TestRunSignalSweepObservability(unittest.TestCase):
    def _make_sweep_result(self, **overrides):
        from backend.app.services.signal_service import SweepResult
        defaults = dict(
            total=100, breakout=5, move=20, watch=10,
            idle=15, insufficient_data=50, errors=0, duration_ms=123.4,
        )
        defaults.update(overrides)
        r = SweepResult()
        for k, v in defaults.items():
            setattr(r, k, v)
        return r

    def test_success_calls_finish_run_with_meta_json(self):
        sweep_result = self._make_sweep_result()

        with (
            patch("backend.app.backstage.scheduler.SessionLocal") as mock_sl,
            patch("backend.app.backstage.scheduler.sweep_signals", return_value=sweep_result),
            patch("backend.app.backstage.scheduler.start_run", return_value=42),
            patch("backend.app.backstage.scheduler.finish_run") as mock_finish,
            patch("backend.app.backstage.scheduler.prune_old_runs"),
        ):
            mock_sl.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)

            from backend.app.backstage.scheduler import _run_signal_sweep
            _run_signal_sweep()

        # find the success finish_run call (status="success")
        success_call = next(
            (c for c in mock_finish.call_args_list if c.kwargs.get("status") == "success"),
            None,
        )
        self.assertIsNotNone(success_call, "finish_run(status='success') not called")
        meta = success_call.kwargs.get("meta_json")
        self.assertIsNotNone(meta, "meta_json not passed to finish_run")
        self.assertEqual(meta["breakout"], 5)
        self.assertEqual(meta["move"], 20)
        self.assertEqual(meta["watch"], 10)
        self.assertEqual(meta["idle"], 15)
        self.assertEqual(meta["insufficient_data"], 50)

    def test_success_records_written_is_total(self):
        sweep_result = self._make_sweep_result(total=77)

        with (
            patch("backend.app.backstage.scheduler.SessionLocal") as mock_sl,
            patch("backend.app.backstage.scheduler.sweep_signals", return_value=sweep_result),
            patch("backend.app.backstage.scheduler.start_run", return_value=1),
            patch("backend.app.backstage.scheduler.finish_run") as mock_finish,
            patch("backend.app.backstage.scheduler.prune_old_runs"),
        ):
            mock_sl.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)

            from backend.app.backstage.scheduler import _run_signal_sweep
            _run_signal_sweep()

        success_call = next(
            c for c in mock_finish.call_args_list if c.kwargs.get("status") == "success"
        )
        self.assertEqual(success_call.kwargs["records_written"], 77)

    def test_exception_records_error_status(self):
        with (
            patch("backend.app.backstage.scheduler.SessionLocal") as mock_sl,
            patch("backend.app.backstage.scheduler.sweep_signals", side_effect=RuntimeError("boom")),
            patch("backend.app.backstage.scheduler.start_run", return_value=99),
            patch("backend.app.backstage.scheduler.finish_run") as mock_finish,
        ):
            mock_sl.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)

            from backend.app.backstage.scheduler import _run_signal_sweep
            _run_signal_sweep()  # should NOT raise

        error_call = next(
            (c for c in mock_finish.call_args_list if c.kwargs.get("status") == "error"),
            None,
        )
        self.assertIsNotNone(error_call, "finish_run(status='error') not called on exception")


# ── e. alert threshold ────────────────────────────────────────────────────────

class TestRunSignalSweepAlertThreshold(unittest.TestCase):
    """_run_signal_sweep should only send a warning when total > threshold."""

    def _run_sweep_with_total(self, total: int):
        from backend.app.services.signal_service import SweepResult
        result = SweepResult()
        for k, v in dict(
            total=total, breakout=0, move=0, watch=0,
            idle=total, insufficient_data=0, errors=0, duration_ms=100.0,
        ).items():
            setattr(result, k, v)

        with (
            patch("backend.app.backstage.scheduler.SessionLocal") as mock_sl,
            patch("backend.app.backstage.scheduler.sweep_signals", return_value=result),
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

    def test_2300_below_5000_threshold_no_warning(self):
        mock_alert = self._run_sweep_with_total(2300)
        warning_calls = [c for c in mock_alert.call_args_list if c.args[0] == "warning"]
        self.assertEqual(len(warning_calls), 0, "Should not fire warning for 2300 < 5000")

    def test_5001_above_5000_threshold_fires_warning(self):
        mock_alert = self._run_sweep_with_total(5001)
        warning_calls = [c for c in mock_alert.call_args_list if c.args[0] == "warning"]
        self.assertEqual(len(warning_calls), 1, "Should fire warning for 5001 > 5000")

    def test_5000_exactly_at_threshold_no_warning(self):
        # threshold is strictly >, not >=
        mock_alert = self._run_sweep_with_total(5000)
        warning_calls = [c for c in mock_alert.call_args_list if c.args[0] == "warning"]
        self.assertEqual(len(warning_calls), 0, "Should not fire warning for exactly 5000")


if __name__ == "__main__":
    unittest.main()
