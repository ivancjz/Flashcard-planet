from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.api.deps import get_database
from backend.app.schemas.alert import AlertItemResponse
from backend.app.services.alert_service import list_active_alerts

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("/{discord_user_id}", response_model=list[AlertItemResponse])
def get_alerts(
    discord_user_id: str,
    db: Session = Depends(get_database),
) -> list[AlertItemResponse]:
    return list_active_alerts(db, discord_user_id)
