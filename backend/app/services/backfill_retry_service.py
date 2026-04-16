"""
backend/app/services/backfill_retry_service.py  — B3

Independent retry queue for backfill failures.

Two entry points for the scheduler:

  record_backfill_failure(db, asset_id, exc, failure_type=None)
    — called by run_backfill_pass() on each per-card exception
    — upserts into failed_backfill_queue
    — marks is_permanent=True after MAX_RETRY_ATTEMPTS

  run_retry_pass(db, batch_size, backfill_fn) -> RetryPassResult
    — processes non-permanent queue entries oldest-first
    — on success: deletes the queue row
    — on failure: increments attempt_count, may mark permanent

FailureType enum is the canonical list of categorised failure modes.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.asset import Asset
from backend.app.models.failed_backfill_queue import FailedBackfillQueue

logger = logging.getLogger(__name__)

MAX_RETRY_ATTEMPTS: int = 3
MAX_ERROR_LENGTH: int = 500


class FailureType(str, Enum):
    API_TIMEOUT         = "api_timeout"
    NO_RESULT           = "no_result"
    MAPPING_FAILED      = "mapping_failed"
    IMAGE_FETCH_FAILED  = "image_fetch_failed"
    PRICE_FETCH_FAILED  = "price_fetch_failed"
    UNKNOWN             = "unknown"


def _classify_exception(exc: Exception) -> FailureType:
    msg = str(exc).lower()
    if "timeout" in msg or "timed out" in msg or "read timeout" in msg:
        return FailureType.API_TIMEOUT
    if "no result" in msg or "not found" in msg or "404" in msg:
        return FailureType.NO_RESULT
    if "image" in msg or "thumbnail" in msg:
        return FailureType.IMAGE_FETCH_FAILED
    if "price" in msg or "price_history" in msg:
        return FailureType.PRICE_FETCH_FAILED
    if "mapping" in msg or "match" in msg or "confidence" in msg:
        return FailureType.MAPPING_FAILED
    return FailureType.UNKNOWN


# ── Write side ────────────────────────────────────────────────────────────────

def record_backfill_failure(
    db: Session,
    asset_id: uuid.UUID,
    exc: Exception,
    failure_type: FailureType | None = None,
) -> FailedBackfillQueue:
    """
    Upsert a failure record for asset_id.

    If a non-permanent row already exists, increment attempt_count and update
    last_attempted_at / last_error. Create a new row otherwise.
    Marks is_permanent=True once attempt_count reaches MAX_RETRY_ATTEMPTS.
    Caller owns the commit.
    """
    now = datetime.now(UTC)
    ftype = failure_type or _classify_exception(exc)
    error_text = str(exc)[:MAX_ERROR_LENGTH]

    existing: FailedBackfillQueue | None = db.execute(
        select(FailedBackfillQueue).where(
            FailedBackfillQueue.asset_id == asset_id,
            FailedBackfillQueue.is_permanent.is_(False),
        )
    ).scalar_one_or_none()

    if existing:
        existing.attempt_count += 1
        existing.last_attempted_at = now
        existing.last_error = error_text
        existing.failure_type = ftype.value
        if existing.attempt_count >= MAX_RETRY_ATTEMPTS:
            existing.is_permanent = True
            logger.warning(
                '{"event": "backfill_permanent_failure", "asset_id": "%s", '
                '"attempts": %d, "failure_type": "%s"}',
                asset_id, existing.attempt_count, ftype.value,
            )
        row = existing
    else:
        row = FailedBackfillQueue(
            id=uuid.uuid4(),
            asset_id=asset_id,
            failure_type=ftype.value,
            attempt_count=1,
            last_attempted_at=now,
            last_error=error_text,
            is_permanent=False,
            created_at=now,
        )
        db.add(row)

    db.flush()
    logger.info(
        '{"event": "backfill_failure_recorded", "asset_id": "%s", '
        '"failure_type": "%s", "attempt": %d, "permanent": %s}',
        asset_id, ftype.value, row.attempt_count, str(row.is_permanent).lower(),
    )
    return row


def clear_backfill_failure(db: Session, asset_id: uuid.UUID) -> None:
    """Remove all queue entries for asset_id on successful backfill."""
    rows = db.execute(
        select(FailedBackfillQueue).where(FailedBackfillQueue.asset_id == asset_id)
    ).scalars().all()
    for row in rows:
        db.delete(row)


# ── Read side ─────────────────────────────────────────────────────────────────

@dataclass
class RetryPassResult:
    attempted: int = 0
    recovered: int = 0
    still_failing: int = 0
    newly_permanent: int = 0
    skipped_permanent: int = 0


def run_retry_pass(
    db: Session,
    batch_size: int = 50,
    backfill_fn: object = None,
) -> RetryPassResult:
    """
    Process non-permanent queue entries, oldest-first.

    backfill_fn: callable(db: Session, asset: Asset) -> bool
    Pass it in from the scheduler to avoid a circular import.
    """
    result = RetryPassResult()

    rows: list[FailedBackfillQueue] = db.execute(
        select(FailedBackfillQueue)
        .where(FailedBackfillQueue.is_permanent.is_(False))
        .order_by(FailedBackfillQueue.last_attempted_at.asc())
        .limit(batch_size)
    ).scalars().all()

    for row in rows:
        asset: Asset | None = db.get(Asset, row.asset_id)
        if asset is None:
            db.delete(row)
            continue

        result.attempted += 1
        try:
            success = backfill_fn(db, asset) if backfill_fn else False
            if success:
                clear_backfill_failure(db, asset.id)
                result.recovered += 1
                logger.info('{"event": "backfill_retry_success", "asset_id": "%s"}', asset.id)
            else:
                _handle_retry_failure(db, row, Exception("backfill returned False"), result)
        except Exception as exc:  # noqa: BLE001
            _handle_retry_failure(db, row, exc, result)

        db.commit()

    logger.info(
        '{"event": "retry_pass_complete", "attempted": %d, "recovered": %d, '
        '"still_failing": %d, "newly_permanent": %d}',
        result.attempted, result.recovered, result.still_failing, result.newly_permanent,
    )
    return result


def _handle_retry_failure(
    db: Session,
    row: FailedBackfillQueue,
    exc: Exception,
    result: RetryPassResult,
) -> None:
    was_permanent = row.is_permanent
    record_backfill_failure(db, row.asset_id, exc)
    if row.is_permanent and not was_permanent:
        result.newly_permanent += 1
    else:
        result.still_failing += 1


# ── Query helpers ─────────────────────────────────────────────────────────────

def get_queue_summary(db: Session) -> dict:
    """Return counts for KPI panel / diagnostics page."""
    from sqlalchemy import func

    rows = db.execute(
        select(
            FailedBackfillQueue.failure_type,
            FailedBackfillQueue.is_permanent,
            func.count(FailedBackfillQueue.id).label("cnt"),
        ).group_by(
            FailedBackfillQueue.failure_type,
            FailedBackfillQueue.is_permanent,
        )
    ).all()

    summary: dict = {
        "total_pending": 0,
        "total_permanent": 0,
        "by_failure_type": {},
    }
    for failure_type, is_permanent, cnt in rows:
        if is_permanent:
            summary["total_permanent"] += cnt
        else:
            summary["total_pending"] += cnt
        summary["by_failure_type"][failure_type] = (
            summary["by_failure_type"].get(failure_type, 0) + cnt
        )
    return summary
