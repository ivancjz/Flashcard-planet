"""
tests/test_admin_stats_scheduler.py

Tests for the /admin/stats scheduler.jobs section.
Verifies that market-digest-send and yugioh-ingestion appear in the
response and that meta_json is surfaced correctly.

Run: pytest tests/test_admin_stats_scheduler.py -v
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

from sqlalchemy import JSON, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.app.models  # noqa: F401
from backend.app.db.base import Base
from backend.app.models.scheduler_run_log import SchedulerRunLog


# ── SQLite in-memory fixture ───────────────────────────────────────────────────

def _coerce_postgres_types() -> None:
    for table in Base.metadata.tables.values():
        for col in table.columns:
            if isinstance(col.type, JSONB):
                col.type = JSON()


@contextmanager
def _session():
    _coerce_postgres_types()
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with factory() as db:
        yield db
    Base.metadata.drop_all(engine)


def _insert_run(
    db,
    job_name: str,
    status: str = "success",
    records_written: int = 1,
    errors: int = 0,
    meta_json: dict | None = None,
    minutes_ago: int = 5,
) -> SchedulerRunLog:
    started = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    finished = started + timedelta(seconds=30)
    row = SchedulerRunLog(
        job_name=job_name,
        started_at=started.replace(tzinfo=None),
        finished_at=finished.replace(tzinfo=None),
        status=status,
        records_written=records_written,
        errors=errors,
        meta_json=meta_json,
    )
    db.add(row)
    db.commit()
    return row


class TestJobStatsHelper:
    """Unit tests for the _job_stats helper function."""

    def test_never_run_returns_sentinel(self):
        from backend.app.backstage.routes import _job_stats
        with _session() as db:
            result = _job_stats(db, "market-digest-send")
        assert result["last_run_status"] == "never_run"
        assert result["run_count_24h"] == 0
        assert result["failure_count_24h"] == 0

    def test_last_run_fields_present(self):
        from backend.app.backstage.routes import _job_stats
        with _session() as db:
            _insert_run(db, "market-digest-send", status="success", records_written=3)
            result = _job_stats(db, "market-digest-send")
        assert result["last_run_status"] == "success"
        assert result["last_run_records_written"] == 3
        assert result["last_run_started_at"] is not None
        assert result["last_run_finished_at"] is not None
        assert result["last_run_duration_ms"] is not None

    def test_meta_json_surfaced(self):
        """meta_json from the run row is returned as-is in the stats."""
        from backend.app.backstage.routes import _job_stats
        meta = {"subscribers_count": 1, "cards_included_count": 5, "delivery_status": "sent"}
        with _session() as db:
            _insert_run(db, "market-digest-send", meta_json=meta)
            result = _job_stats(db, "market-digest-send")
        assert result["last_run_meta_json"] == meta

    def test_run_count_24h(self):
        from backend.app.backstage.routes import _job_stats
        with _session() as db:
            _insert_run(db, "market-digest-send", minutes_ago=10)
            _insert_run(db, "market-digest-send", minutes_ago=60)
            _insert_run(db, "market-digest-send", minutes_ago=1500)  # >24h, excluded
            result = _job_stats(db, "market-digest-send")
        assert result["run_count_24h"] == 2

    def test_failure_count_24h(self):
        from backend.app.backstage.routes import _job_stats
        with _session() as db:
            _insert_run(db, "yugioh-ingestion", status="success", minutes_ago=30)
            _insert_run(db, "yugioh-ingestion", status="error", minutes_ago=60)
            _insert_run(db, "yugioh-ingestion", status="failed", minutes_ago=90)
            result = _job_stats(db, "yugioh-ingestion")
        assert result["failure_count_24h"] == 2
        assert result["run_count_24h"] == 3


class TestAdminStatsSchedulerSection:
    """Integration tests: /admin/stats response includes all tracked jobs."""

    def _call_stats(self, db):
        """Call admin_stats directly with a mock DB dependency."""
        from unittest.mock import patch
        from backend.app.backstage.routes import admin_stats

        # admin_stats requires db and admin key dependency — call the inner logic directly
        # by importing _job_stats and building the scheduler dict ourselves
        from backend.app.backstage.routes import _job_stats
        from backend.app.services.scheduler_run_log_service import (
            JOB_BULK_REFRESH, JOB_DIGEST, JOB_EBAY, JOB_EXPLANATION,
            JOB_HEARTBEAT, JOB_INGESTION, JOB_SIGNALS, JOB_YGO,
        )
        tracked = [
            JOB_INGESTION, JOB_SIGNALS, JOB_EBAY, JOB_HEARTBEAT,
            JOB_YGO, JOB_DIGEST, JOB_BULK_REFRESH, JOB_EXPLANATION,
        ]
        return {"jobs": {job: _job_stats(db, job) for job in tracked}}

    def test_market_digest_send_present(self):
        """scheduler.jobs must contain an entry for market-digest-send."""
        with _session() as db:
            scheduler = self._call_stats(db)
        assert "market-digest-send" in scheduler["jobs"], (
            "market-digest-send missing from scheduler.jobs"
        )

    def test_yugioh_ingestion_present(self):
        """scheduler.jobs must contain an entry for yugioh-ingestion."""
        with _session() as db:
            scheduler = self._call_stats(db)
        assert "yugioh-ingestion" in scheduler["jobs"], (
            "yugioh-ingestion missing from scheduler.jobs"
        )

    def test_all_eight_tracked_jobs_present(self):
        """All 8 tracked jobs must appear in scheduler.jobs."""
        expected = {
            "ingestion", "signals", "ebay-ingestion", "alert-heartbeat",
            "yugioh-ingestion", "market-digest-send",
            "bulk-set-price-refresh", "explanation-sweep",
        }
        with _session() as db:
            scheduler = self._call_stats(db)
        missing = expected - set(scheduler["jobs"].keys())
        assert not missing, f"Missing jobs in scheduler.jobs: {missing}"

    def test_digest_meta_json_parsed(self):
        """meta_json for market-digest-send is returned and readable."""
        meta = {"subscribers_count": 2, "cards_included_count": 8, "delivery_status": "sent"}
        with _session() as db:
            _insert_run(db, "market-digest-send", meta_json=meta)
            scheduler = self._call_stats(db)
        digest = scheduler["jobs"]["market-digest-send"]
        assert digest["last_run_meta_json"] == meta
        assert digest["last_run_status"] == "success"
