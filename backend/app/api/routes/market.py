from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.api.deps import get_database
from backend.app.schemas.market import MarketOverviewResponse
from backend.app.services.market_overview_service import get_market_overview

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/overview", response_model=MarketOverviewResponse)
def market_overview(db: Session = Depends(get_database)) -> MarketOverviewResponse:
    return get_market_overview(db)
