from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.app.api.deps import get_database
from backend.app.schemas.price import AssetPriceResponse, TopMoverResponse
from backend.app.services.price_service import get_asset_prices_by_name, get_top_movers

router = APIRouter(prefix="/prices", tags=["prices"])


@router.get("/search", response_model=list[AssetPriceResponse])
def search_prices(
    name: str = Query(..., min_length=2, description="Asset name to query"),
    db: Session = Depends(get_database),
) -> list[AssetPriceResponse]:
    results = get_asset_prices_by_name(db, name)
    if not results:
        raise HTTPException(status_code=404, detail=f"No prices found for asset name '{name}'.")
    return results


@router.get("/topmovers", response_model=list[TopMoverResponse])
def top_movers(
    limit: int = Query(10, ge=1, le=25),
    db: Session = Depends(get_database),
) -> list[TopMoverResponse]:
    return get_top_movers(db, limit=limit)
