from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable, Literal, cast

from sqlalchemy.orm import Session

from backend.app.db.session import SessionLocal
from backend.app.models.daily_market_report import DailyMarketReport
from backend.app.services.daily_report_commentary import (
    PROMPT_VERSION,
    CommentaryGenerationResult,
    generate_daily_report_commentary,
)
from backend.app.services.daily_report_evidence import (
    build_daily_report_evidence_bundle,
    evaluate_evidence_sufficiency,
    evidence_hash,
)
from backend.app.services.daily_report_intelligence_repository import (
    claim_generation_attempt,
    get_latest_published_report,
    persist_insufficient_evidence,
    record_generation_failure,
    record_generation_success,
)
from backend.app.services.llm_provider import (
    MetadataLLMProvider,
    get_llm_provider_for_task,
)


SessionFactory = Callable[[], AbstractContextManager[Session]]
ProviderFactory = Callable[[], MetadataLLMProvider]


@dataclass(frozen=True)
class DailyReportIntelligenceRunResult:
    status: Literal["published", "insufficient_evidence", "noop", "failed"]
    records_written: int
    report_id: str | None = None
    report_date: str | None = None
    evidence_hash: str | None = None
    prompt_version: str = PROMPT_VERSION
    attempt_count: int = 0
    error_code: str | None = None
    reason: str | None = None


def _default_provider_factory() -> MetadataLLMProvider:
    return cast(
        MetadataLLMProvider,
        get_llm_provider_for_task("daily_report_commentary"),
    )


def _normalized_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _failed_generation(error_code: str) -> CommentaryGenerationResult:
    return CommentaryGenerationResult(
        commentary=None,
        provider=None,
        model=None,
        error_code=error_code,
    )


def run_latest_daily_report_intelligence(
    *,
    session_factory: SessionFactory = SessionLocal,
    provider_factory: ProviderFactory = _default_provider_factory,
    now: datetime | None = None,
) -> DailyReportIntelligenceRunResult:
    now = _normalized_utc(now)

    with session_factory() as preparation_db:
        report = get_latest_published_report(preparation_db)
        if report is None:
            return DailyReportIntelligenceRunResult(
                status="noop",
                records_written=0,
                reason="no_report",
            )

        bundle = build_daily_report_evidence_bundle(report)
        digest = evidence_hash(bundle)
        sufficiency = evaluate_evidence_sufficiency(report, bundle)
        report_id = report.id
        report_id_text = str(report.id)
        report_date_text = report.report_date.isoformat()

        if not sufficiency.sufficient:
            written = persist_insufficient_evidence(
                preparation_db,
                report_id,
                digest,
                PROMPT_VERSION,
                now=now,
            )
            if written:
                return DailyReportIntelligenceRunResult(
                    status="insufficient_evidence",
                    records_written=1,
                    report_id=report_id_text,
                    report_date=report_date_text,
                    evidence_hash=digest,
                    reason=sufficiency.reason,
                )
            return DailyReportIntelligenceRunResult(
                status="noop",
                records_written=0,
                report_id=report_id_text,
                report_date=report_date_text,
                evidence_hash=digest,
                reason="insufficient_evidence",
            )

        decision = claim_generation_attempt(
            preparation_db,
            report_id,
            digest,
            PROMPT_VERSION,
            now=now,
        )
        claim = decision.claim
        if claim is None:
            return DailyReportIntelligenceRunResult(
                status="noop",
                records_written=0,
                report_id=report_id_text,
                report_date=report_date_text,
                evidence_hash=digest,
                reason=decision.reason,
            )

    try:
        provider = provider_factory()
    except Exception:  # noqa: BLE001
        generation = _failed_generation("internal_error")
    else:
        generation = generate_daily_report_commentary(bundle, provider)

    with session_factory() as persistence_db:
        current_report = persistence_db.get(DailyMarketReport, claim.report_id)
        if current_report is None or current_report.status != "published":
            written = record_generation_failure(
                persistence_db,
                claim,
                "stale_evidence",
                now=now,
            )
            if not written:
                return DailyReportIntelligenceRunResult(
                    status="noop",
                    records_written=0,
                    report_id=report_id_text,
                    report_date=report_date_text,
                    evidence_hash=digest,
                    attempt_count=claim.attempt_count,
                    reason="superseded_attempt",
                )
            return DailyReportIntelligenceRunResult(
                status="failed",
                records_written=1,
                report_id=report_id_text,
                report_date=report_date_text,
                evidence_hash=digest,
                attempt_count=claim.attempt_count,
                error_code="stale_evidence",
            )

        current_bundle = build_daily_report_evidence_bundle(current_report)
        if evidence_hash(current_bundle) != digest:
            written = record_generation_failure(
                persistence_db,
                claim,
                "stale_evidence",
                now=now,
            )
            if not written:
                return DailyReportIntelligenceRunResult(
                    status="noop",
                    records_written=0,
                    report_id=report_id_text,
                    report_date=report_date_text,
                    evidence_hash=digest,
                    attempt_count=claim.attempt_count,
                    reason="superseded_attempt",
                )
            return DailyReportIntelligenceRunResult(
                status="failed",
                records_written=1,
                report_id=report_id_text,
                report_date=report_date_text,
                evidence_hash=digest,
                attempt_count=claim.attempt_count,
                error_code="stale_evidence",
            )

        if generation.commentary is None:
            error_code = generation.error_code or "internal_error"
            written = record_generation_failure(
                persistence_db,
                claim,
                error_code,
                now=now,
            )
            if not written:
                return DailyReportIntelligenceRunResult(
                    status="noop",
                    records_written=0,
                    report_id=report_id_text,
                    report_date=report_date_text,
                    evidence_hash=digest,
                    attempt_count=claim.attempt_count,
                    reason="superseded_attempt",
                )
            return DailyReportIntelligenceRunResult(
                status="failed",
                records_written=1,
                report_id=report_id_text,
                report_date=report_date_text,
                evidence_hash=digest,
                attempt_count=claim.attempt_count,
                error_code=error_code,
            )

        written = record_generation_success(
            persistence_db,
            claim,
            generation,
            now=now,
        )
        if not written:
            return DailyReportIntelligenceRunResult(
                status="noop",
                records_written=0,
                report_id=report_id_text,
                report_date=report_date_text,
                evidence_hash=digest,
                attempt_count=claim.attempt_count,
                reason="superseded_attempt",
            )
        return DailyReportIntelligenceRunResult(
            status="published",
            records_written=1,
            report_id=report_id_text,
            report_date=report_date_text,
            evidence_hash=digest,
            attempt_count=claim.attempt_count,
        )
