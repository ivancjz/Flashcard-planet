from __future__ import annotations

from datetime import UTC, date, datetime

from pydantic import TypeAdapter
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models.daily_market_report import DailyMarketReport
from backend.app.schemas.catalyst import CatalystResponse
from backend.app.schemas.daily_market_report import (
    DailyMarketReportListResponse,
    DailyMarketReportResponse,
)
from backend.app.schemas.market import MarketOverviewResponse
from backend.app.services.catalyst_service import select_daily_report_catalysts
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


def _response_from_row(row: DailyMarketReport) -> DailyMarketReportResponse:
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
    return _response_from_row(row) if row is not None else None


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
    return DailyMarketReportListResponse(
        reports=[_response_from_row(row) for row in rows],
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
    return _response_from_row(row) if row is not None else None
