"""
tests/test_zero_output_alerting.py

Integration tests for zero-output job detection (P2 from audits/2026-05-01/REPORT.md).

A job that ran successfully but wrote zero records for the entire alert window is a
silent failure — scheduler_run_log shows 'success' but no data reaches the product.
The eBay ingest during the April 2026 outage is the canonical example.

TDD: tests written BEFORE the implementation. Each test FAILS on current main.
"""
from __future__ import annotations

import unittest
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

from sqlalchemy import JSON, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.app.models  # noqa: F401 — registers all models
from backend.app.db.base import Base
from backend.app.models.scheduler_run_log import SchedulerRunLog


# ── SQLite in-memory setup ─────────────────────────────────────────────────────

def _coerce_postgres_types() -> None:
    for table in Base.metadata.tables.values():
        for col in table.columns:
            if isinstance(col.type, JSONB):
                col.type = JSON()


@contextmanager
def _db_session():
    _coerce_postgres_types()
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with factory() as session:
        yield session
    Base.metadata.drop_all(engine)


def _run(session, job_name: str, *, hours_ago: float, records: int,
         status: str = "success") -> SchedulerRunLog:
    started = datetime.now(UTC) - timedelta(hours=hours_ago)
    row = SchedulerRunLog(
        job_name=job_name,
        started_at=started,
        finished_at=started + timedelta(minutes=2),
        status=status,
        records_written=records,
    )
    session.add(row)
    session.flush()
    return row


# ── Tests ──────────────────────────────────────────────────────────────────────

class TestGetZeroOutputJobs(unittest.TestCase):
    """
    get_zero_output_jobs(session, job_names, window_hours, now) returns a list
    of job names where ALL completed runs in the window had records_written=0.
    """

    def _call(self, session, job_names, window_hours=24):
        from backend.app.backstage.scheduler import get_zero_output_jobs
        return get_zero_output_jobs(
            session,
            job_names=job_names,
            window_hours=window_hours,
            now=datetime.now(UTC),
        )

    def test_job_with_all_zero_records_is_returned(self):
        """eBay ingest: 5 runs, all records_written=0 → must be flagged."""
        with _db_session() as db:
            for h in range(5):
                _run(db, "ebay-ingestion", hours_ago=h * 4, records=0)
            result = self._call(db, ["ebay-ingestion"])
        self.assertIn("ebay-ingestion", result)

    def test_job_with_some_nonzero_records_is_not_returned(self):
        """4 zero runs + 1 run with records → not zero-output (data is flowing)."""
        with _db_session() as db:
            _run(db, "ingestion", hours_ago=1, records=1500)
            for h in [4, 8, 12, 16]:
                _run(db, "ingestion", hours_ago=h, records=0)
            result = self._call(db, ["ingestion"])
        self.assertNotIn("ingestion", result)

    def test_job_with_no_runs_in_window_is_not_returned(self):
        """A job that never ran is NOT a zero-output job (that's the 25h absence check)."""
        with _db_session() as db:
            # Run exists but outside the 24h window
            _run(db, "ebay-ingestion", hours_ago=30, records=0)
            result = self._call(db, ["ebay-ingestion"], window_hours=24)
        self.assertNotIn("ebay-ingestion", result)

    def test_only_requested_jobs_are_checked(self):
        """If a job has zero output but is not in the job_names list, it is not returned."""
        with _db_session() as db:
            _run(db, "ebay-ingestion", hours_ago=1, records=0)
            _run(db, "ingestion", hours_ago=1, records=0)
            # Only check ingestion, not ebay-ingestion
            result = self._call(db, ["ingestion"])
        self.assertIn("ingestion", result)
        self.assertNotIn("ebay-ingestion", result)

    def test_running_rows_are_excluded(self):
        """Orphaned 'running' rows must not count as zero-output runs."""
        with _db_session() as db:
            # One orphaned running row (no finished_at)
            row = SchedulerRunLog(
                job_name="signals",
                started_at=datetime.now(UTC) - timedelta(hours=1),
                status="running",
                records_written=0,
            )
            db.add(row)
            db.flush()
            result = self._call(db, ["signals"])
        # An orphaned running row is not a completed run — should NOT trigger alert
        self.assertNotIn("signals", result)

    def test_error_runs_are_excluded(self):
        """Errored runs are not counted as zero-output successes."""
        with _db_session() as db:
            _run(db, "ingestion", hours_ago=2, records=0, status="error")
            result = self._call(db, ["ingestion"])
        self.assertNotIn("ingestion", result)

    def test_multiple_zero_output_jobs_all_returned(self):
        """When multiple jobs have zero output, all of them are returned."""
        with _db_session() as db:
            _run(db, "ebay-ingestion", hours_ago=2, records=0)
            _run(db, "ingestion", hours_ago=2, records=0)
            result = self._call(db, ["ebay-ingestion", "ingestion"])
        self.assertIn("ebay-ingestion", result)
        self.assertIn("ingestion", result)

    def test_window_hours_is_respected(self):
        """Runs older than window_hours are not counted."""
        with _db_session() as db:
            # This run is 10h ago — inside a 24h window but outside a 6h window
            _run(db, "bulk-set-price-refresh", hours_ago=10, records=0)
            result_24h = self._call(db, ["bulk-set-price-refresh"], window_hours=24)
            result_6h = self._call(db, ["bulk-set-price-refresh"], window_hours=6)
        self.assertIn("bulk-set-price-refresh", result_24h)
        self.assertNotIn("bulk-set-price-refresh", result_6h)
