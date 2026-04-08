from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.api.deps import get_database
from backend.app.schemas.alert import AlertHistoryItemResponse, AlertItemResponse
from backend.app.services.alert_service import list_active_alerts, list_alert_history

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("/{discord_user_id}", response_model=list[AlertItemResponse])
def get_alerts(
    discord_user_id: str,
    db: Session = Depends(get_database),
) -> list[AlertItemResponse]:
    return list_active_alerts(db, discord_user_id)


@router.get("/{discord_user_id}/history", response_model=list[AlertHistoryItemResponse])
def get_alert_history(
    discord_user_id: str,
    limit: int = Query(20, ge=1, le=100),
    asset_name: str | None = Query(None, description="Filter by asset name (partial match)"),
    db: Session = Depends(get_database),
) -> list[AlertHistoryItemResponse]:
    return list_alert_history(db, discord_user_id, limit=limit, asset_name=asset_name)
