from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Sequence
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.models.daily_market_report import DailyMarketReport
from backend.app.models.daily_report_intelligence import DailyReportIntelligence
from backend.app.services.daily_report_commentary import CommentaryGenerationResult


PENDING_STALE_AFTER = timedelta(minutes=15)
INSUFFICIENT_EVIDENCE_MESSAGE = "Insufficient evidence."


@dataclass(frozen=True)
class IntelligenceClaim:
    intelligence_id: UUID
    report_id: UUID
    evidence_hash: str
    prompt_version: str
    attempt_count: int


@dataclass(frozen=True)
class ClaimDecision:
    claim: IntelligenceClaim | None
    reason: str


def _utc_now(now: datetime) -> datetime:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return now.astimezone(UTC)


def _comparable_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _cache_key_query(
    report_id: UUID,
    evidence_hash: str,
    prompt_version: str,
):
    return select(DailyReportIntelligence).where(
        DailyReportIntelligence.report_id == report_id,
        DailyReportIntelligence.evidence_hash == evidence_hash,
        DailyReportIntelligence.prompt_version == prompt_version,
    )


def _load_cache_row(
    db: Session,
    report_id: UUID,
    evidence_hash: str,
    prompt_version: str,
    *,
    for_update: bool = False,
) -> DailyReportIntelligence | None:
    statement = _cache_key_query(report_id, evidence_hash, prompt_version)
    if for_update:
        statement = statement.with_for_update()
    return db.execute(statement).scalar_one_or_none()


def _claim_from_row(row: DailyReportIntelligence) -> IntelligenceClaim:
    return IntelligenceClaim(
        intelligence_id=row.id,
        report_id=row.report_id,
        evidence_hash=row.evidence_hash,
        prompt_version=row.prompt_version,
        attempt_count=row.attempt_count,
    )


def _claim_existing_attempt(
    db: Session,
    row: DailyReportIntelligence,
    *,
    now: datetime,
) -> ClaimDecision:
    if row.status == "published":
        return ClaimDecision(claim=None, reason="published")
    if row.status == "insufficient_evidence":
        return ClaimDecision(claim=None, reason="insufficient_evidence")
    if row.attempt_count >= 3:
        return ClaimDecision(claim=None, reason="attempts_exhausted")
    if (
        row.status == "pending"
        and _comparable_utc(row.updated_at) > now - PENDING_STALE_AFTER
    ):
        return ClaimDecision(claim=None, reason="recent_pending")

    row.status = "pending"
    row.attempt_count += 1
    row.error_code = None
    row.updated_at = now
    db.commit()
    return ClaimDecision(claim=_claim_from_row(row), reason="claimed")


def get_latest_published_report(db: Session) -> DailyMarketReport | None:
    return db.scalar(
        select(DailyMarketReport)
        .where(DailyMarketReport.status == "published")
        .order_by(
            DailyMarketReport.report_date.desc(),
            DailyMarketReport.generated_at.desc(),
        )
        .limit(1)
    )


def persist_insufficient_evidence(
    db: Session,
    report_id: UUID,
    evidence_hash: str,
    prompt_version: str,
    *,
    now: datetime,
) -> bool:
    now = _utc_now(now)
    row = _load_cache_row(
        db,
        report_id,
        evidence_hash,
        prompt_version,
        for_update=True,
    )
    if row is not None and row.status in {"published", "insufficient_evidence"}:
        return False

    if row is None:
        row = DailyReportIntelligence(
            id=uuid4(),
            report_id=report_id,
            evidence_hash=evidence_hash,
            prompt_version=prompt_version,
            status="insufficient_evidence",
            attempt_count=0,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    else:
        row.status = "insufficient_evidence"
        row.updated_at = now

    row.headline = None
    row.commentary = INSUFFICIENT_EVIDENCE_MESSAGE
    row.risk_summary = None
    row.key_observations_json = []
    row.evidence_refs_json = {}
    row.provider = None
    row.model = None
    row.attempt_count = 0
    row.error_code = None
    row.generated_at = None

    try:
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        competing = _load_cache_row(
            db,
            report_id,
            evidence_hash,
            prompt_version,
            for_update=True,
        )
        if competing is None:
            raise
        return False


def claim_generation_attempt(
    db: Session,
    report_id: UUID,
    evidence_hash: str,
    prompt_version: str,
    *,
    now: datetime,
) -> ClaimDecision:
    now = _utc_now(now)
    row = _load_cache_row(
        db,
        report_id,
        evidence_hash,
        prompt_version,
        for_update=True,
    )
    if row is not None:
        return _claim_existing_attempt(db, row, now=now)

    row = DailyReportIntelligence(
        id=uuid4(),
        report_id=report_id,
        evidence_hash=evidence_hash,
        prompt_version=prompt_version,
        status="pending",
        attempt_count=1,
        key_observations_json=[],
        evidence_refs_json={},
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    try:
        db.commit()
        return ClaimDecision(claim=_claim_from_row(row), reason="claimed")
    except IntegrityError:
        db.rollback()
        competing = _load_cache_row(
            db,
            report_id,
            evidence_hash,
            prompt_version,
            for_update=True,
        )
        if competing is None:
            raise
        return _claim_existing_attempt(db, competing, now=now)


def _current_claim_row(
    db: Session,
    claim: IntelligenceClaim,
) -> DailyReportIntelligence | None:
    row = db.scalar(
        select(DailyReportIntelligence)
        .where(DailyReportIntelligence.id == claim.intelligence_id)
        .with_for_update()
    )
    if row is None:
        return None
    if (
        row.report_id != claim.report_id
        or row.evidence_hash != claim.evidence_hash
        or row.prompt_version != claim.prompt_version
        or row.status != "pending"
        or row.attempt_count != claim.attempt_count
    ):
        return None
    return row


def record_generation_success(
    db: Session,
    claim: IntelligenceClaim,
    result: CommentaryGenerationResult,
    *,
    now: datetime,
) -> bool:
    now = _utc_now(now)
    assert result.commentary is not None
    assert result.provider is not None
    assert result.model is not None

    row = _current_claim_row(db, claim)
    if row is None:
        return False

    commentary = result.commentary
    row.status = "published"
    row.headline = commentary.headline
    row.commentary = commentary.commentary
    row.risk_summary = commentary.risk_summary
    row.key_observations_json = [
        observation.text for observation in commentary.key_observations
    ]
    row.evidence_refs_json = {
        "headline": list(commentary.headline_evidence_refs),
        "commentary": list(commentary.commentary_evidence_refs),
        "key_observations": [
            list(observation.evidence_refs)
            for observation in commentary.key_observations
        ],
        "risk_summary": list(commentary.risk_evidence_refs),
    }
    row.provider = result.provider
    row.model = result.model
    row.error_code = None
    row.generated_at = now
    row.updated_at = now
    db.commit()
    return True


def record_generation_failure(
    db: Session,
    claim: IntelligenceClaim,
    error_code: str,
    *,
    now: datetime,
) -> bool:
    now = _utc_now(now)
    row = _current_claim_row(db, claim)
    if row is None:
        return False

    row.status = "failed"
    row.headline = None
    row.commentary = None
    row.risk_summary = None
    row.key_observations_json = []
    row.evidence_refs_json = {}
    row.provider = None
    row.model = None
    row.error_code = error_code
    row.generated_at = None
    row.updated_at = now
    db.commit()
    return True


def load_intelligence_candidates(
    db: Session,
    report_ids: Sequence[UUID],
) -> dict[UUID, list[DailyReportIntelligence]]:
    unique_report_ids = list(dict.fromkeys(report_ids))
    if not unique_report_ids:
        return {}

    candidates: dict[UUID, list[DailyReportIntelligence]] = {
        report_id: [] for report_id in unique_report_ids
    }
    rows = db.scalars(
        select(DailyReportIntelligence)
        .where(DailyReportIntelligence.report_id.in_(unique_report_ids))
        .order_by(
            DailyReportIntelligence.report_id,
            DailyReportIntelligence.updated_at.desc(),
        )
    ).all()
    for row in rows:
        candidates[row.report_id].append(row)
    return candidates
