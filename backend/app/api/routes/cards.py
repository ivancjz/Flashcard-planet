from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.app.api.deps import get_database
from backend.app.core.data_service import DataService

router = APIRouter(prefix="/cards", tags=["cards"])


@router.get("/{external_id}/enriched")
def get_card_enriched(
    external_id: str,
    discord_user_id: str | None = Query(default=None),
    db: Session = Depends(get_database),
) -> dict:
    asset_id = DataService.resolve_asset_id(db, external_id)
    if asset_id is None:
        raise HTTPException(status_code=404, detail="Card not found")

    access_tier = DataService.get_access_tier_for_discord_user(db, discord_user_id)
    response = DataService.get_card_detail(db, asset_id, access_tier=access_tier, external_id=external_id)
    if response is None:
        raise HTTPException(status_code=404, detail="Card not found")

    gate = response.pro_gate_config.to_web_config() if response.pro_gate_config else None

    return {
        "card_name": response.card_name,
        "external_id": response.external_id,
        "current_price": str(response.current_price) if response.current_price else None,
        "sample_size": response.sample_size,
        "match_confidence_avg": str(response.match_confidence_avg) if response.match_confidence_avg else None,
        "data_age": response.data_age,
        "source_breakdown": response.source_breakdown,
        "access_tier": response.access_tier,
        "pro_gate": gate,
    }
