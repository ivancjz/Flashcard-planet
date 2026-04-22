"""
tests/test_scheduler_run_log_cleanup.py

TDD: cleanup_stale_runs() marks orphaned 'running' rows as 'error'.
Uses real SQLite in-memory DB so we test actual DB behaviour, not mocks.
"""
from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, text as sa_text
from sqlalchemy.orm import Session

from backend.app.models.scheduler_run_log import SchedulerRunLog

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS scheduler_run_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_name        VARCHAR(64)  NOT NULL,
    started_at      DATETIME     NOT NULL,
    finished_at     DATETIME,
    status          VARCHAR(16)  NOT NULL DEFAULT 'running',
    records_written INTEGER      NOT NULL DEFAULT 0,
    errors          INTEGER      NOT NULL DEFAULT 0,
    error_message   TEXT,
    meta_json       TEXT
)
"""


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    with engine.connect() as conn:
        conn.execute(sa_text(_CREATE_TABLE))
        conn.commit()
    return Session(engine)


def _insert_run(
    session: Session,
    *,
    job_name: str = "ingestion",
    status: str = "running",
    started_at: datetime,
    finished_at: datetime | None = None,
) -> SchedulerRunLog:
    row = SchedulerRunLog(
        job_name=job_name,
        started_at=started_at,
        finished_at=finished_at,
        status=status,
        records_written=0,
        errors=0,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


class TestCleanupStaleRuns(unittest.TestCase):
    def setUp(self):
        self.session = _make_session()
        self.now = datetime(2026, 4, 22, 9, 0, 0, tzinfo=UTC)

    def tearDown(self):
        self.session.close()

    def _call(self, stale_after_minutes: int = 120):
        from backend.app.services.scheduler_run_log_service import cleanup_stale_runs
        cleanup_stale_runs(self.session, now=self.now, stale_after_minutes=stale_after_minutes)

    # ── RED: orphaned rows get marked error ───────────────────────────────────

    def test_old_running_row_becomes_error(self):
        row = _insert_run(
            self.session,
            status="running",
            started_at=self.now - timedelta(hours=6),
        )
        self._call()
        self.session.refresh(row)
        self.assertEqual(row.status, "error")

    def test_old_running_row_gets_error_message(self):
        row = _insert_run(
            self.session,
            status="running",
            started_at=self.now - timedelta(hours=6),
        )
        self._call()
        self.session.refresh(row)
        self.assertIsNotNone(row.error_message)
        self.assertIn("orphan", row.error_message.lower())

    def test_old_running_row_gets_finished_at(self):
        row = _insert_run(
            self.session,
            status="running",
            started_at=self.now - timedelta(hours=6),
        )
        self._call()
        self.session.refresh(row)
        self.assertIsNotNone(row.finished_at)

    # ── boundary: recent running rows are untouched ───────────────────────────

    def test_recent_running_row_is_not_touched(self):
        row = _insert_run(
            self.session,
            status="running",
            started_at=self.now - timedelta(minutes=30),
        )
        self._call(stale_after_minutes=120)
        self.session.refresh(row)
        self.assertEqual(row.status, "running")

    def test_exactly_at_threshold_is_not_touched(self):
        row = _insert_run(
            self.session,
            status="running",
            started_at=self.now - timedelta(minutes=120),
        )
        self._call(stale_after_minutes=120)
        self.session.refresh(row)
        self.assertEqual(row.status, "running")

    def test_one_second_past_threshold_is_cleaned(self):
        row = _insert_run(
            self.session,
            status="running",
            started_at=self.now - timedelta(minutes=120, seconds=1),
        )
        self._call(stale_after_minutes=120)
        self.session.refresh(row)
        self.assertEqual(row.status, "error")

    # ── terminal rows are untouched ───────────────────────────────────────────

    def test_success_row_is_not_touched(self):
        row = _insert_run(
            self.session,
            status="success",
            started_at=self.now - timedelta(hours=6),
            finished_at=self.now - timedelta(hours=5),
        )
        self._call()
        self.session.refresh(row)
        self.assertEqual(row.status, "success")

    def test_error_row_is_not_touched(self):
        row = _insert_run(
            self.session,
            status="error",
            started_at=self.now - timedelta(hours=6),
            finished_at=self.now - timedelta(hours=5),
        )
        self._call()
        self.session.refresh(row)
        self.assertEqual(row.status, "error")

    # ── multiple jobs cleaned in one call ─────────────────────────────────────

    def test_cleans_multiple_jobs(self):
        ingestion = _insert_run(
            self.session, job_name="ingestion", status="running",
            started_at=self.now - timedelta(hours=6),
        )
        signals = _insert_run(
            self.session, job_name="signals", status="running",
            started_at=self.now - timedelta(hours=5),
        )
        self._call()
        self.session.refresh(ingestion)
        self.session.refresh(signals)
        self.assertEqual(ingestion.status, "error")
        self.assertEqual(signals.status, "error")

    def test_returns_count_of_cleaned_rows(self):
        _insert_run(self.session, status="running", started_at=self.now - timedelta(hours=6))
        _insert_run(self.session, status="running", started_at=self.now - timedelta(hours=7))
        from backend.app.services.scheduler_run_log_service import cleanup_stale_runs
        count = cleanup_stale_runs(self.session, now=self.now, stale_after_minutes=120)
        self.assertEqual(count, 2)


if __name__ == "__main__":
    unittest.main()
