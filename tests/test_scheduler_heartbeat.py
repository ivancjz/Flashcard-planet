"""
tests/test_scheduler_heartbeat.py

Tests for scheduler heartbeat utilities.
Currently covers get_zero_output_jobs() 304-skip filtering.
"""
from __future__ import annotations

import json
import unittest
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

from sqlalchemy import JSON, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.app.models  # noqa: F401 — registers all models with Base
from backend.app.db.base import Base
from backend.app.models.scheduler_run_log import SchedulerRunLog


def _coerce_jsonb_to_json():
    """Replace JSONB columns with JSON() so SQLite can handle them in tests."""
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()


@contextmanager
def _db():
    _coerce_jsonb_to_json()
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


def _insert_run(
    session,
    *,
    job_name: str,
    status: str = "success",
    records_written: int = 0,
    meta_json: dict | None = None,
    started_at: datetime,
    finished_at: datetime | None = None,
) -> SchedulerRunLog:
    row = SchedulerRunLog(
        job_name=job_name,
        status=status,
        records_written=records_written,
        meta_json=meta_json,
        started_at=started_at,
        finished_at=finished_at or started_at + timedelta(seconds=10),
        errors=0,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


class TestGetZeroOutputJobs(unittest.TestCase):
    """Tests for get_zero_output_jobs() — specifically the 304-skip exclusion."""

    def _call(self, session, job_names, window_hours=24, now=None):
        from backend.app.backstage.scheduler import get_zero_output_jobs
        if now is None:
            now = datetime.now(UTC)
        return get_zero_output_jobs(
            session,
            job_names=job_names,
            window_hours=window_hours,
            now=now,
        )

    def test_get_zero_output_jobs_excludes_not_modified_runs(self):
        """A cardmarket run with records_written=0 and meta_json={'not_modified': True}
        must NOT be flagged — it's a 304-skipped run, not a true zero-output failure."""
        now = datetime.now(UTC)
        with _db() as session:
            _insert_run(
                session,
                job_name="cardmarket-ingestion",
                status="success",
                records_written=0,
                meta_json={"not_modified": True},
                started_at=now - timedelta(minutes=30),
            )
            result = self._call(session, ["cardmarket-ingestion"], window_hours=24, now=now)
            self.assertEqual(result, [], "304-skipped run must not be flagged as zero-output")

    def test_get_zero_output_jobs_flags_normal_zero_output(self):
        """A job with records_written=0 and no not_modified flag must still be flagged."""
        now = datetime.now(UTC)
        with _db() as session:
            _insert_run(
                session,
                job_name="cardmarket-ingestion",
                status="success",
                records_written=0,
                meta_json={},
                started_at=now - timedelta(minutes=30),
            )
            result = self._call(session, ["cardmarket-ingestion"], window_hours=24, now=now)
            self.assertIn("cardmarket-ingestion", result, "Normal zero-output run must be flagged")

    def test_get_zero_output_jobs_flags_zero_output_with_none_meta(self):
        """A job with records_written=0 and meta_json=None must still be flagged."""
        now = datetime.now(UTC)
        with _db() as session:
            _insert_run(
                session,
                job_name="some-ingestion",
                status="success",
                records_written=0,
                meta_json=None,
                started_at=now - timedelta(minutes=30),
            )
            result = self._call(session, ["some-ingestion"], window_hours=24, now=now)
            self.assertIn("some-ingestion", result, "Zero-output run with null meta must be flagged")

    def test_get_zero_output_jobs_not_flagged_when_records_written(self):
        """A run that wrote records must not be flagged even if another run wrote zero."""
        now = datetime.now(UTC)
        with _db() as session:
            _insert_run(
                session,
                job_name="cardmarket-ingestion",
                status="success",
                records_written=0,
                meta_json={},
                started_at=now - timedelta(hours=2),
            )
            _insert_run(
                session,
                job_name="cardmarket-ingestion",
                status="success",
                records_written=5,
                meta_json={},
                started_at=now - timedelta(hours=1),
            )
            result = self._call(session, ["cardmarket-ingestion"], window_hours=24, now=now)
            self.assertEqual(result, [], "Job that wrote records in window must not be flagged")

    def test_get_zero_output_jobs_excludes_runs_outside_window(self):
        """Runs older than the window are not counted."""
        now = datetime.now(UTC)
        with _db() as session:
            _insert_run(
                session,
                job_name="cardmarket-ingestion",
                status="success",
                records_written=0,
                meta_json={},
                started_at=now - timedelta(hours=25),  # outside 24h window
            )
            result = self._call(session, ["cardmarket-ingestion"], window_hours=24, now=now)
            # No runs in window → not flagged (that's the 25h absence check's job)
            self.assertEqual(result, [], "Runs outside window must not be counted")


if __name__ == "__main__":
    unittest.main()
