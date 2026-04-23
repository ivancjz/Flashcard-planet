"""
backend/app/services/scheduler_run_log_service.py  — D series

Lightweight run-log for scheduler jobs.  Each job records a start row
(status="running") and updates it to "success" or "error" when done.
Old rows are pruned to keep the table small.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete as sa_delete, select
from sqlalchemy.orm import Session

from backend.app.models.scheduler_run_log import SchedulerRunLog

logger = logging.getLogger(__name__)

JOB_INGESTION    = "ingestion"
JOB_BACKFILL     = "backfill"
JOB_RETRY        = "retry"
JOB_SIGNALS      = "signals"
JOB_EBAY         = "ebay-ingestion"
JOB_BULK_REFRESH = "bulk-set-price-refresh"
JOB_HEARTBEAT    = "alert-heartbeat"
JOB_YGO          = "yugioh-ingestion"

_KEEP_RUNS = 50


def start_run(session: Session, job_name: str) -> int:
    """Insert a 'running' row and return its id.  Commits immediately."""
    row = SchedulerRunLog(
        job_name=job_name,
        started_at=datetime.now(UTC).replace(microsecond=0),
        status="running",
        records_written=0,
        errors=0,
    )
    session.add(row)
    session.flush()
    session.commit()
    return row.id


def finish_run(
    session: Session,
    run_id: int,
    *,
    status: str,
    records_written: int = 0,
    errors: int = 0,
    error_message: str | None = None,
    meta_json: dict | None = None,
) -> None:
    """Update the run row to its final state.  Commits immediately."""
    row = session.get(SchedulerRunLog, run_id)
    if row is None:
        logger.warning("finish_run: run_id=%s not found", run_id)
        return
    row.finished_at = datetime.now(UTC).replace(microsecond=0)
    row.status = status
    row.records_written = records_written
    row.errors = errors
    row.error_message = error_message
    row.meta_json = meta_json
    session.commit()


def prune_old_runs(session: Session, job_name: str, keep: int = _KEEP_RUNS) -> None:
    """Delete all but the `keep` most-recent rows for job_name.  Commits."""
    keep_ids = session.scalars(
        select(SchedulerRunLog.id)
        .where(SchedulerRunLog.job_name == job_name)
        .order_by(SchedulerRunLog.started_at.desc())
        .limit(keep)
    ).all()
    if not keep_ids:
        return
    session.execute(
        sa_delete(SchedulerRunLog).where(
            SchedulerRunLog.job_name == job_name,
            SchedulerRunLog.id.not_in(keep_ids),
        )
    )
    session.commit()


def cleanup_stale_runs(
    session: Session,
    *,
    now: datetime | None = None,
    stale_after_minutes: int = 120,
) -> int:
    """Mark 'running' rows older than stale_after_minutes as 'error'.

    Returns the number of rows updated. Called at startup to close out any
    rows left open by a previous container crash (Railway SIGKILL, OOM, etc.).
    """
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(minutes=stale_after_minutes)
    rows = session.scalars(
        select(SchedulerRunLog)
        .where(
            SchedulerRunLog.status == "running",
            SchedulerRunLog.started_at < cutoff,
        )
    ).all()
    for row in rows:
        row.status = "error"
        row.finished_at = now
        row.error_message = "Orphaned: container restart — finish_run never called"
    if rows:
        session.commit()
        logger.warning(
            "cleanup_stale_runs: closed %d orphaned 'running' row(s) older than %dm",
            len(rows),
            stale_after_minutes,
        )
    return len(rows)


def get_last_run(
    session: Session,
    job_name: str,
    *,
    only_statuses: list[str] | None = None,
) -> SchedulerRunLog | None:
    """Return the most-recent row for job_name, or None.

    Pass ``only_statuses`` to restrict to specific terminal statuses, e.g.
    ``["success", "partial", "warning"]`` to ignore failed/errored rows.
    """
    q = select(SchedulerRunLog).where(SchedulerRunLog.job_name == job_name)
    if only_statuses is not None:
        q = q.where(SchedulerRunLog.status.in_(only_statuses))
    return session.scalars(q.order_by(SchedulerRunLog.started_at.desc()).limit(1)).first()


def serialize_run(run: SchedulerRunLog | None) -> dict:
    """Serialise a run row to a plain dict suitable for JSON / diagnostics."""
    if run is None:
        return {"status": "never_run"}
    started = run.started_at
    finished = run.finished_at
    duration = (
        (finished - started).total_seconds()
        if finished is not None and started is not None
        else None
    )
    return {
        "status": run.status,
        "started_at": started.isoformat() if started else None,
        "finished_at": finished.isoformat() if finished else None,
        "duration_seconds": duration,
        "records_written": run.records_written,
        "errors": run.errors,
        "error_message": run.error_message,
        "meta_json": run.meta_json,
    }
