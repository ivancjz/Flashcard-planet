from __future__ import annotations

from datetime import UTC, date, datetime
import json
from typing import Sequence

from pydantic import TypeAdapter
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models.daily_market_report import DailyMarketReport
from backend.app.models.daily_report_intelligence import DailyReportIntelligence
from backend.app.schemas.catalyst import CatalystResponse
from backend.app.schemas.daily_market_report import (
    DailyMarketReportListResponse,
    DailyMarketReportResponse,
)
from backend.app.schemas.daily_report_intelligence import (
    DailyReportEvidenceCatalogItemResponse,
    DailyReportIntelligenceObservationResponse,
    DailyReportIntelligenceResponse,
)
from backend.app.schemas.market import MarketOverviewResponse
from backend.app.services.catalyst_service import select_daily_report_catalysts
from backend.app.services.daily_report_commentary import (
    PROMPT_VERSION,
    CommentaryValidationError,
    parse_and_validate_commentary,
)
from backend.app.services.daily_report_evidence import (
    build_daily_report_evidence_bundle,
    evidence_hash,
)
from backend.app.services.daily_report_intelligence_repository import (
    INSUFFICIENT_EVIDENCE_MESSAGE,
    load_intelligence_candidates,
)
from backend.app.services.market_overview_service import get_market_overview


_CATALYST_SNAPSHOT_ADAPTER = TypeAdapter(list[CatalystResponse])


def _default_report_date(now: datetime | None) -> date:
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return current.astimezone(UTC).date()


def _report_title(report_date: date) -> str:
    return f"Flashcard Planet Daily - {report_date.isoformat()}"


def _serialize_overview(overview: MarketOverviewResponse) -> dict:
    return overview.model_dump(mode="json")


def _public_intelligence(
    row: DailyMarketReport,
    candidates: Sequence[DailyReportIntelligence],
) -> DailyReportIntelligenceResponse:
    if row.status != "published" or not candidates:
        return DailyReportIntelligenceResponse()

    bundle = build_daily_report_evidence_bundle(row)
    current_hash = evidence_hash(bundle)
    candidate = next(
        (
            item
            for item in candidates
            if item.report_id == row.id
            and item.evidence_hash == current_hash
            and item.prompt_version == PROMPT_VERSION
        ),
        None,
    )
    if candidate is None:
        return DailyReportIntelligenceResponse()
    if candidate.status == "insufficient_evidence":
        return DailyReportIntelligenceResponse(
            status="insufficient_evidence",
            commentary=INSUFFICIENT_EVIDENCE_MESSAGE,
        )
    if candidate.status != "published" or candidate.generated_at is None:
        return DailyReportIntelligenceResponse()

    references = candidate.evidence_refs_json
    observation_texts = candidate.key_observations_json
    if not isinstance(references, dict) or not isinstance(
        observation_texts,
        list,
    ):
        return DailyReportIntelligenceResponse()
    observation_references = references.get("key_observations")
    if (
        not isinstance(observation_references, list)
        or len(observation_texts) != len(observation_references)
    ):
        return DailyReportIntelligenceResponse()

    payload = {
        "headline": candidate.headline,
        "headline_evidence_refs": references.get("headline"),
        "commentary": candidate.commentary,
        "commentary_evidence_refs": references.get("commentary"),
        "key_observations": [
            {"text": text, "evidence_refs": evidence_refs}
            for text, evidence_refs in zip(
                observation_texts,
                observation_references,
                strict=True,
            )
        ],
        "risk_summary": candidate.risk_summary,
        "risk_evidence_refs": references.get("risk_summary"),
    }
    try:
        validated = parse_and_validate_commentary(
            json.dumps(payload),
            bundle,
        )
    except (CommentaryValidationError, TypeError, ValueError):
        return DailyReportIntelligenceResponse()

    ordered_references: list[str] = []
    seen_references: set[str] = set()
    reference_groups = [
        validated.headline_evidence_refs,
        validated.commentary_evidence_refs,
        *[
            observation.evidence_refs
            for observation in validated.key_observations
        ],
        validated.risk_evidence_refs,
    ]
    for reference_group in reference_groups:
        for reference in reference_group:
            if reference not in seen_references:
                seen_references.add(reference)
                ordered_references.append(reference)

    referenced_ids = set(ordered_references)
    evidence_catalog = [
        DailyReportEvidenceCatalogItemResponse(
            id=record.id,
            kind=record.kind,
            label=record.label,
            source_record_id=record.source_record_id,
            target_anchor=record.target_anchor,
        )
        for record in bundle.records
        if record.id in referenced_ids
    ]
    return DailyReportIntelligenceResponse(
        status="published",
        headline=validated.headline,
        headline_evidence_refs=list(validated.headline_evidence_refs),
        commentary=validated.commentary,
        commentary_evidence_refs=list(validated.commentary_evidence_refs),
        risk_summary=validated.risk_summary,
        risk_evidence_refs=list(validated.risk_evidence_refs),
        key_observations=[
            DailyReportIntelligenceObservationResponse(
                text=observation.text,
                evidence_refs=list(observation.evidence_refs),
            )
            for observation in validated.key_observations
        ],
        evidence_refs=ordered_references,
        evidence_catalog=evidence_catalog,
        generated_at=candidate.generated_at,
    )


def _response_from_row(
    row: DailyMarketReport,
    intelligence_candidates: Sequence[DailyReportIntelligence] = (),
) -> DailyMarketReportResponse:
    overview = MarketOverviewResponse.model_validate(row.overview_json)
    catalyst_snapshot = (
        [] if row.catalysts_json is None else row.catalysts_json
    )
    catalysts = _CATALYST_SNAPSHOT_ADAPTER.validate_python(catalyst_snapshot)
    return DailyMarketReportResponse(
        id=row.id,
        report_date=row.report_date,
        generated_at=row.generated_at,
        status=row.status,
        title=row.title,
        market_sentiment=row.market_sentiment,
        confidence_label=row.confidence_label,
        summary=row.summary,
        overview=overview,
        evidence=[str(item) for item in (row.evidence_json or [])],
        catalysts=catalysts,
        intelligence=_public_intelligence(row, intelligence_candidates),
    )


def create_daily_market_report(
    db: Session,
    *,
    report_date: date | None = None,
    now: datetime | None = None,
) -> DailyMarketReportResponse:
    effective_now = now or datetime.now(UTC)
    effective_report_date = report_date or _default_report_date(effective_now)
    overview = get_market_overview(db)
    overview_payload = _serialize_overview(overview)
    catalysts = select_daily_report_catalysts(db, as_of=effective_now)
    catalysts_payload = [
        catalyst.model_dump(mode="json")
        for catalyst in catalysts
    ]

    row = db.scalar(
        select(DailyMarketReport).where(DailyMarketReport.report_date == effective_report_date)
    )
    if row is None:
        row = DailyMarketReport(report_date=effective_report_date)
        db.add(row)

    row.generated_at = effective_now
    row.status = "published"
    row.title = _report_title(effective_report_date)
    row.market_sentiment = overview.market_sentiment
    row.confidence_label = overview.confidence_label
    row.summary = overview.commentary
    row.overview_json = overview_payload
    row.evidence_json = list(overview.evidence)
    row.catalysts_json = catalysts_payload

    db.commit()
    db.refresh(row)
    return _response_from_row(row)


def get_latest_daily_market_report(db: Session) -> DailyMarketReportResponse | None:
    row = db.scalar(
        select(DailyMarketReport)
        .order_by(DailyMarketReport.report_date.desc(), DailyMarketReport.generated_at.desc())
        .limit(1)
    )
    if row is None:
        return None
    candidates = load_intelligence_candidates(db, [row.id])
    return _response_from_row(row, candidates.get(row.id, ()))


def list_daily_market_reports(
    db: Session,
    *,
    limit: int = 30,
    offset: int = 0,
) -> DailyMarketReportListResponse:
    total = db.scalar(select(func.count(DailyMarketReport.id))) or 0
    rows = db.scalars(
        select(DailyMarketReport)
        .order_by(DailyMarketReport.report_date.desc(), DailyMarketReport.generated_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    candidates = load_intelligence_candidates(db, [row.id for row in rows])
    return DailyMarketReportListResponse(
        reports=[
            _response_from_row(row, candidates.get(row.id, ()))
            for row in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


def get_daily_market_report_by_date(
    db: Session,
    report_date: date,
) -> DailyMarketReportResponse | None:
    row = db.scalar(
        select(DailyMarketReport).where(DailyMarketReport.report_date == report_date)
    )
    if row is None:
        return None
    candidates = load_intelligence_candidates(db, [row.id])
    return _response_from_row(row, candidates.get(row.id, ()))
