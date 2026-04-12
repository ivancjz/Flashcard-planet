from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.app.api.deps import get_database
from backend.app.schemas.price import (
    AssetHistoryResponse,
    AssetPriceResponse,
    PricePredictionResponse,
    TopMoverResponse,
    TopValueResponse,
)
from backend.app.services.price_service import (
    get_asset_history_by_external_id,
    get_asset_history_by_name,
    get_asset_prices_by_name,
    get_top_movers,
    get_top_value_assets,
    predict_assets_by_name,
)

router = APIRouter(prefix="/prices", tags=["prices"])


def _resolve_lookup_name(*, name: str | None, q: str | None) -> str:
    asset_name = (name or q or "").strip()
    if len(asset_name) < 2:
        raise HTTPException(status_code=422, detail="Either 'name' or 'q' must be provided.")
    return asset_name


@router.get("/search", response_model=list[AssetPriceResponse])
def search_prices(
    name: str | None = Query(None, min_length=2, description="Asset name to query"),
    q: str | None = Query(None, min_length=2, description="Dashboard lookup alias"),
    db: Session = Depends(get_database),
) -> list[AssetPriceResponse]:
    asset_name = _resolve_lookup_name(name=name, q=q)
    results = get_asset_prices_by_name(db, asset_name)
    if not results:
        raise HTTPException(status_code=404, detail=f"No prices found for asset name '{asset_name}'.")
    return results


@router.get("/topmovers", response_model=list[TopMoverResponse])
def top_movers(
    limit: int = Query(10, ge=1, le=25),
    db: Session = Depends(get_database),
) -> list[TopMoverResponse]:
    return get_top_movers(db, limit=limit)


@router.get("/topvalue", response_model=list[TopValueResponse])
def top_value(
    limit: int = Query(10, ge=1, le=25),
    db: Session = Depends(get_database),
) -> list[TopValueResponse]:
    return get_top_value_assets(db, limit=limit)


@router.get("/predict", response_model=list[PricePredictionResponse])
def predict_prices(
    name: str = Query(..., min_length=2, description="Asset name to predict"),
    db: Session = Depends(get_database),
) -> list[PricePredictionResponse]:
    results = predict_assets_by_name(db, name)
    if not results:
        raise HTTPException(status_code=404, detail=f"No prices found for asset name '{name}'.")
    return results


@router.get("/history", response_model=AssetHistoryResponse)
def history_prices(
    name: str = Query(..., min_length=2, description="Asset name to inspect"),
    limit: int = Query(5, ge=1, le=25),
    db: Session = Depends(get_database),
) -> AssetHistoryResponse:
    result = get_asset_history_by_name(db, name, limit=limit)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No prices found for asset name '{name}'.")
    return result


@router.get("/history/{external_id}", response_model=AssetHistoryResponse)
def history_prices_by_external_id(
    external_id: str,
    limit: int = Query(5, ge=1, le=25),
    db: Session = Depends(get_database),
) -> AssetHistoryResponse:
    result = get_asset_history_by_external_id(db, external_id, limit=limit)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No prices found for asset external_id '{external_id}'.")
    return result
