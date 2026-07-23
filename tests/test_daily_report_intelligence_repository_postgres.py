from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta
from threading import Barrier, Lock, Thread
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session

from backend.app.models.daily_market_report import DailyMarketReport
from backend.app.services.daily_report_commentary import PROMPT_VERSION
from backend.app.services.daily_report_intelligence_repository import (
    ClaimDecision,
    claim_generation_attempt,
)


DATABASE_URL = os.getenv("TEST_POSTGRES_DATABASE_URL")


@pytest.mark.skipif(
    not DATABASE_URL,
    reason="TEST_POSTGRES_DATABASE_URL is required for PostgreSQL contention",
)
def test_two_postgres_sessions_only_claim_a_cache_key_once() -> None:
    assert DATABASE_URL is not None
    engine = create_engine(DATABASE_URL, pool_size=2, max_overflow=0)
    report_id = uuid4()
    fixture_range_days = (date(8999, 12, 31) - date(2200, 1, 1)).days
    report_date = date(2200, 1, 1) + timedelta(
        days=report_id.int % fixture_range_days
    )
    now = datetime(2026, 7, 23, 7, 0, tzinfo=UTC)
    digest = "c" * 64

    with Session(engine) as db:
        db.add(
            DailyMarketReport(
                id=report_id,
                report_date=report_date,
                generated_at=now,
                status="published",
                title="PostgreSQL contention fixture",
                market_sentiment="neutral",
                confidence_label="medium",
                summary="Concurrency test fixture.",
                overview_json={},
                evidence_json=[],
                catalysts_json=[],
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()

    barrier = Barrier(2)
    results: list[ClaimDecision] = []
    errors: list[BaseException] = []
    result_lock = Lock()

    def claim() -> None:
        try:
            with Session(engine) as db:
                barrier.wait(timeout=5)
                decision = claim_generation_attempt(
                    db,
                    report_id,
                    digest,
                    PROMPT_VERSION,
                    now=now,
                )
            with result_lock:
                results.append(decision)
        except BaseException as exc:
            with result_lock:
                errors.append(exc)

    workers = [Thread(target=claim), Thread(target=claim)]
    try:
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=10)

        assert all(not worker.is_alive() for worker in workers)
        assert errors == []
        assert len(results) == 2
        assert sum(result.claim is not None for result in results) == 1
        assert sorted(result.reason for result in results) == [
            "claimed",
            "recent_pending",
        ]
    finally:
        with Session(engine) as db:
            db.execute(
                delete(DailyMarketReport).where(
                    DailyMarketReport.id == report_id
                )
            )
            db.commit()
        engine.dispose()
