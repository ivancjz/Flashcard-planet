from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from backend.app.services.scheduler_run_log_service import JOB_DAILY_REPORT


def test_register_daily_market_report_job_uses_interval_trigger():
    from backend.app.backstage.scheduler import _register_daily_market_report_job

    scheduler = MagicMock()

    _register_daily_market_report_job(scheduler)

    scheduler.add_job.assert_called_once()
    call_args = scheduler.add_job.call_args
    assert call_args.args[1] == "interval"
    assert call_args.kwargs["hours"] == 24
    assert call_args.kwargs["id"] == JOB_DAILY_REPORT
    assert call_args.kwargs["next_run_time"] is None


def test_run_daily_market_report_snapshot_writes_success_run_log():
    from backend.app.backstage.scheduler import _run_daily_market_report_snapshot

    session = MagicMock()
    ctx = MagicMock()
    ctx.__enter__.return_value = session
    ctx.__exit__.return_value = False
    report = SimpleNamespace(
        report_date=date(2026, 7, 21),
        market_sentiment="bullish",
        confidence_label="medium",
    )

    with (
        patch("backend.app.backstage.scheduler.SessionLocal", return_value=ctx),
        patch("backend.app.backstage.scheduler.start_run", return_value=123) as start,
        patch("backend.app.services.daily_market_report_service.create_daily_market_report", return_value=report),
        patch("backend.app.backstage.scheduler.finish_run") as finish,
        patch("backend.app.backstage.scheduler.prune_old_runs") as prune,
    ):
        _run_daily_market_report_snapshot()

    start.assert_called_once_with(session, JOB_DAILY_REPORT)
    finish.assert_called_once()
    assert finish.call_args.kwargs["status"] == "success"
    assert finish.call_args.kwargs["records_written"] == 1
    assert finish.call_args.kwargs["meta_json"] == {
        "report_date": "2026-07-21",
        "market_sentiment": "bullish",
        "confidence_label": "medium",
    }
    prune.assert_called_once_with(session, JOB_DAILY_REPORT)


def test_run_daily_market_report_snapshot_writes_error_run_log():
    from backend.app.backstage.scheduler import _run_daily_market_report_snapshot

    session = MagicMock()
    ctx = MagicMock()
    ctx.__enter__.return_value = session
    ctx.__exit__.return_value = False

    with (
        patch("backend.app.backstage.scheduler.SessionLocal", return_value=ctx),
        patch("backend.app.backstage.scheduler.start_run", return_value=123),
        patch(
            "backend.app.services.daily_market_report_service.create_daily_market_report",
            side_effect=RuntimeError("report failed"),
        ),
        patch("backend.app.backstage.scheduler.finish_run") as finish,
        patch("backend.app.backstage.scheduler.prune_old_runs") as prune,
    ):
        _run_daily_market_report_snapshot()

    finish.assert_called_once()
    assert finish.call_args.kwargs["status"] == "error"
    assert finish.call_args.kwargs["records_written"] == 0
    assert finish.call_args.kwargs["errors"] == 1
    assert finish.call_args.kwargs["error_message"] == "report failed"
    prune.assert_called_once_with(session, JOB_DAILY_REPORT)


def test_run_daily_market_report_snapshot_recovers_with_fresh_log_session():
    from backend.app.backstage.scheduler import _run_daily_market_report_snapshot

    report_session = MagicMock(name="report_session")
    log_session = MagicMock(name="log_session")
    report_ctx = MagicMock()
    report_ctx.__enter__.return_value = report_session
    report_ctx.__exit__.return_value = False
    log_ctx = MagicMock()
    log_ctx.__enter__.return_value = log_session
    log_ctx.__exit__.return_value = False

    with (
        patch(
            "backend.app.backstage.scheduler.SessionLocal",
            side_effect=[report_ctx, log_ctx],
        ),
        patch("backend.app.backstage.scheduler.start_run", return_value=123),
        patch(
            "backend.app.services.daily_market_report_service.create_daily_market_report",
            side_effect=RuntimeError("report failed"),
        ),
        patch("backend.app.backstage.scheduler.finish_run") as finish,
        patch("backend.app.backstage.scheduler.prune_old_runs") as prune,
    ):
        _run_daily_market_report_snapshot()

    report_session.rollback.assert_called_once_with()
    finish.assert_called_once()
    assert finish.call_args.args == (log_session, 123)
    assert finish.call_args.kwargs["status"] == "error"
    assert finish.call_args.kwargs["records_written"] == 0
    assert finish.call_args.kwargs["errors"] == 1
    assert finish.call_args.kwargs["error_message"] == "report failed"
    prune.assert_called_once_with(log_session, JOB_DAILY_REPORT)


def test_run_daily_market_report_snapshot_logs_failure_when_rollback_fails():
    from backend.app.backstage.scheduler import _run_daily_market_report_snapshot

    report_session = MagicMock(name="report_session")
    report_session.rollback.side_effect = RuntimeError("connection lost")
    log_session = MagicMock(name="log_session")
    report_ctx = MagicMock()
    report_ctx.__enter__.return_value = report_session
    report_ctx.__exit__.return_value = False
    log_ctx = MagicMock()
    log_ctx.__enter__.return_value = log_session
    log_ctx.__exit__.return_value = False

    with (
        patch(
            "backend.app.backstage.scheduler.SessionLocal",
            side_effect=[report_ctx, log_ctx],
        ),
        patch("backend.app.backstage.scheduler.start_run", return_value=123),
        patch(
            "backend.app.services.daily_market_report_service.create_daily_market_report",
            side_effect=RuntimeError("report failed"),
        ),
        patch("backend.app.backstage.scheduler.finish_run") as finish,
        patch("backend.app.backstage.scheduler.prune_old_runs") as prune,
    ):
        _run_daily_market_report_snapshot()

    finish.assert_called_once()
    assert finish.call_args.args == (log_session, 123)
    assert finish.call_args.kwargs["status"] == "error"
    assert finish.call_args.kwargs["error_message"] == "report failed"
    prune.assert_called_once_with(log_session, JOB_DAILY_REPORT)
