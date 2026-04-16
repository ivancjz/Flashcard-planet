from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.app.api.deps import get_database
from backend.app.core.banner import UPGRADE_URL
from backend.app.schemas.watchlist import MessageResponse, WatchlistCreateRequest, WatchlistItemResponse
from backend.app.services.alert_service import is_tier_error
from backend.app.services.watchlist_service import (
    add_watchlist_item,
    list_watchlist_items,
    remove_watchlist_item,
)

router = APIRouter(prefix="/watchlists", tags=["watchlists"])


@router.post("", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
def create_watchlist_item(
    payload: WatchlistCreateRequest,
    db: Session = Depends(get_database),
) -> MessageResponse:
    try:
        result = add_watchlist_item(db, payload)
        db.commit()
    except ValueError as exc:
        db.rollback()
        msg = str(exc)
        if is_tier_error(msg):
            raise HTTPException(
                status_code=403,
                detail={"error": msg, "upgrade_url": UPGRADE_URL},
            )
        raise HTTPException(status_code=404, detail=msg)
    except Exception:
        db.rollback()
        raise

    if result.created_watchlist:
        prefix = f"Created a new watch for '{result.watchlist.asset.name}'."
    else:
        prefix = f"Reused your existing watch for '{result.watchlist.asset.name}'."

    if result.added_rule_labels:
        detail = " Added alert rules: " + ", ".join(result.added_rule_labels) + "."
    else:
        detail = " No new alert rules were added."

    return MessageResponse(
        message=prefix + detail,
        created_watchlist=result.created_watchlist,
        added_rule_labels=result.added_rule_labels,
    )


@router.get("/{discord_user_id}", response_model=list[WatchlistItemResponse])
def get_watchlist(
    discord_user_id: str,
    db: Session = Depends(get_database),
) -> list[WatchlistItemResponse]:
    return list_watchlist_items(db, discord_user_id)


@router.delete("", response_model=MessageResponse)
def delete_watchlist_item(
    discord_user_id: str = Query(...),
    asset_name: str = Query(...),
    db: Session = Depends(get_database),
) -> MessageResponse:
    removed = remove_watchlist_item(db, discord_user_id, asset_name)
    if not removed:
        raise HTTPException(status_code=404, detail="Watchlist entry not found.")
    db.commit()
    return MessageResponse(message=f"Stopped watching '{asset_name}'.")
