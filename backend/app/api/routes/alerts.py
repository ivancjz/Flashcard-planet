from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.app.api.deps import get_database
from backend.app.schemas.alert import (
    AlertActionResponse,
    AlertCreateRequest,
    AlertHistoryItemResponse,
    AlertItemResponse,
)
from backend.app.services.alert_service import (
    create_alert,
    deactivate_alert,
    delete_alert,
    list_active_alerts,
    list_alert_history,
)

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.post("", response_model=AlertActionResponse, status_code=status.HTTP_201_CREATED)
def create_alert_route(
    payload: AlertCreateRequest,
    db: Session = Depends(get_database),
) -> AlertActionResponse:
    try:
        alert = create_alert(db, payload)
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise

    return AlertActionResponse(message=f"Created alert {alert.id}.")


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


@router.delete("/{alert_id}", response_model=AlertActionResponse)
def delete_alert_route(
    alert_id: UUID,
    db: Session = Depends(get_database),
) -> AlertActionResponse:
    try:
        removed = delete_alert(db, alert_id)
        if not removed:
            db.rollback()
            raise HTTPException(status_code=404, detail="Alert not found.")
        db.commit()
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise

    return AlertActionResponse(message=f"Deleted alert {alert_id}.")


@router.patch("/{alert_id}/deactivate", response_model=AlertActionResponse)
def deactivate_alert_route(
    alert_id: UUID,
    db: Session = Depends(get_database),
) -> AlertActionResponse:
    try:
        deactivated = deactivate_alert(db, alert_id)
        if not deactivated:
            db.rollback()
            raise HTTPException(status_code=404, detail="Alert not found.")
        db.commit()
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise

    return AlertActionResponse(message=f"Deactivated alert {alert_id}.")
