from __future__ import annotations

from datetime import date
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from backend.app.core.config import Settings
from backend.app.services.daily_report_intelligence_service import (
    DailyReportIntelligenceRunResult,
)
from backend.app.services.scheduler_run_log_service import (
    JOB_DAILY_REPORT,
    JOB_DAILY_REPORT_INTELLIGENCE,
)


def test_daily_report_ai_is_disabled_by_default_and_interval_is_bounded():
    with patch.dict(os.environ, {}, clear=True):
        settings = Settings(_env_file=None)

    assert settings.daily_report_ai_enabled is False
    assert settings.daily_report_ai_interval_minutes == 60
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValidationError):
            Settings(
                _env_file=None,
                daily_report_ai_interval_minutes=14,
            )


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


def test_register_daily_report_intelligence_job_uses_configured_interval():
    from backend.app.backstage.scheduler import (
        _register_daily_report_intelligence_job,
    )

    scheduler = MagicMock()
    settings = SimpleNamespace(daily_report_ai_interval_minutes=60)

    _register_daily_report_intelligence_job(scheduler, settings)

    call_args = scheduler.add_job.call_args
    assert call_args.args[1] == "interval"
    assert call_args.kwargs == {
        "minutes": 60,
        "id": JOB_DAILY_REPORT_INTELLIGENCE,
        "replace_existing": True,
        "max_instances": 1,
        "coalesce": True,
        "next_run_time": None,
    }


@pytest.mark.parametrize(
    ("service_result", "expected_status", "records_written", "errors"),
    [
        (
            DailyReportIntelligenceRunResult(
                status="published",
                records_written=1,
            ),
            "success",
            1,
            0,
        ),
        (
            DailyReportIntelligenceRunResult(
                status="insufficient_evidence",
                records_written=1,
            ),
            "success",
            1,
            0,
        ),
        (
            DailyReportIntelligenceRunResult(
                status="noop",
                records_written=0,
                reason="already_published",
            ),
            "success",
            0,
            0,
        ),
        (
            DailyReportIntelligenceRunResult(
                status="failed",
                records_written=0,
                error_code="invalid_json",
            ),
            "error",
            0,
            1,
        ),
    ],
)
def test_ai_job_maps_service_result_to_run_log(
    service_result,
    expected_status,
    records_written,
    errors,
):
    from backend.app.backstage.scheduler import _run_daily_report_intelligence

    start_session = MagicMock(name="start_session")
    log_session = MagicMock(name="log_session")
    start_context = MagicMock()
    start_context.__enter__.return_value = start_session
    start_context.__exit__.return_value = False
    log_context = MagicMock()
    log_context.__enter__.return_value = log_session
    log_context.__exit__.return_value = False

    with (
        patch(
            "backend.app.backstage.scheduler.SessionLocal",
            side_effect=[start_context, log_context],
        ),
        patch("backend.app.backstage.scheduler.start_run", return_value=41),
        patch(
            "backend.app.backstage.scheduler."
            "run_latest_daily_report_intelligence",
            return_value=service_result,
        ),
        patch("backend.app.backstage.scheduler.finish_run") as finish,
        patch("backend.app.backstage.scheduler.prune_old_runs") as prune,
    ):
        _run_daily_report_intelligence()

    assert finish.call_args.args == (log_session, 41)
    assert finish.call_args.kwargs["status"] == expected_status
    assert finish.call_args.kwargs["records_written"] == records_written
    assert finish.call_args.kwargs["errors"] == errors
    assert (
        finish.call_args.kwargs["meta_json"]["intelligence_status"]
        == service_result.status
    )
    prune.assert_called_once_with(
        log_session,
        JOB_DAILY_REPORT_INTELLIGENCE,
    )


def test_ai_job_records_unexpected_failure_with_fresh_log_session():
    from backend.app.backstage.scheduler import _run_daily_report_intelligence

    start_session = MagicMock(name="start_session")
    log_session = MagicMock(name="log_session")
    start_context = MagicMock()
    start_context.__enter__.return_value = start_session
    start_context.__exit__.return_value = False
    log_context = MagicMock()
    log_context.__enter__.return_value = log_session
    log_context.__exit__.return_value = False

    with (
        patch(
            "backend.app.backstage.scheduler.SessionLocal",
            side_effect=[start_context, log_context],
        ),
        patch("backend.app.backstage.scheduler.start_run", return_value=42),
        patch(
            "backend.app.backstage.scheduler."
            "run_latest_daily_report_intelligence",
            side_effect=RuntimeError("unexpected preparation failure"),
        ),
        patch("backend.app.backstage.scheduler.finish_run") as finish,
        patch("backend.app.backstage.scheduler.prune_old_runs") as prune,
    ):
        _run_daily_report_intelligence()

    assert finish.call_args.args == (log_session, 42)
    assert finish.call_args.kwargs["status"] == "error"
    assert finish.call_args.kwargs["records_written"] == 0
    assert finish.call_args.kwargs["errors"] == 1
    assert finish.call_args.kwargs["meta_json"] == {
        "error_code": "internal_error"
    }
    prune.assert_called_once_with(
        log_session,
        JOB_DAILY_REPORT_INTELLIGENCE,
    )
