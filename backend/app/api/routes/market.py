from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.app.api.deps import get_database
from backend.app.schemas.catalyst import (
    CatalystLifecycle,
    CatalystListResponse,
    CatalystResponse,
)
from backend.app.schemas.daily_market_report import (
    DailyMarketReportListResponse,
    DailyMarketReportResponse,
)
from backend.app.schemas.market import MarketOverviewResponse
from backend.app.services.catalyst_service import get_catalyst, list_catalysts
from backend.app.services.daily_market_report_service import (
    create_daily_market_report,
    get_daily_market_report_by_date,
    get_latest_daily_market_report,
    list_daily_market_reports,
)
from backend.app.services.market_overview_service import get_market_overview

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/overview", response_model=MarketOverviewResponse)
def market_overview(db: Session = Depends(get_database)) -> MarketOverviewResponse:
    return get_market_overview(db)


@router.get("/catalysts", response_model=CatalystListResponse)
def catalyst_list(
    status: list[CatalystLifecycle] | None = Query(None),
    game: str | None = None,
    event_type: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_database),
) -> CatalystListResponse:
    normalized_event_type = (
        event_type.strip().upper() if event_type is not None else None
    )
    return list_catalysts(
        db,
        statuses=status,
        game=game,
        event_type=normalized_event_type,
        limit=limit,
        offset=offset,
    )


@router.get("/catalysts/{catalyst_id}", response_model=CatalystResponse)
def catalyst_detail(
    catalyst_id: UUID,
    db: Session = Depends(get_database),
) -> CatalystResponse:
    catalyst = get_catalyst(db, catalyst_id)
    if catalyst is None:
        raise HTTPException(status_code=404, detail="Catalyst not found.")
    return catalyst


@router.post("/daily-report/generate", response_model=DailyMarketReportResponse)
def generate_daily_market_report(
    report_date: date | None = Query(None, description="UTC report date to generate"),
    db: Session = Depends(get_database),
) -> DailyMarketReportResponse:
    return create_daily_market_report(db, report_date=report_date)


@router.get("/daily-report/latest", response_model=DailyMarketReportResponse)
def latest_daily_market_report(db: Session = Depends(get_database)) -> DailyMarketReportResponse:
    report = get_latest_daily_market_report(db)
    if report is None:
        raise HTTPException(status_code=404, detail="No daily market report found.")
    return report


@router.get("/daily-report", response_model=DailyMarketReportListResponse)
def daily_market_report_history(
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_database),
) -> DailyMarketReportListResponse:
    return list_daily_market_reports(db, limit=limit, offset=offset)


@router.get("/daily-report/{report_date}", response_model=DailyMarketReportResponse)
def dated_daily_market_report(
    report_date: date,
    db: Session = Depends(get_database),
) -> DailyMarketReportResponse:
    report = get_daily_market_report_by_date(db, report_date)
    if report is None:
        raise HTTPException(
            status_code=404,
            detail=f"No daily market report found for {report_date.isoformat()}.",
        )
    return report
