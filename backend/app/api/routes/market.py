from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.app.api.deps import get_database
from backend.app.schemas.daily_market_report import DailyMarketReportResponse
from backend.app.schemas.market import MarketOverviewResponse
from backend.app.services.daily_market_report_service import (
    create_daily_market_report,
    get_daily_market_report_by_date,
    get_latest_daily_market_report,
)
from backend.app.services.market_overview_service import get_market_overview

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/overview", response_model=MarketOverviewResponse)
def market_overview(db: Session = Depends(get_database)) -> MarketOverviewResponse:
    return get_market_overview(db)


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
