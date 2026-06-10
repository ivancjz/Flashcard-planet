from __future__ import annotations

import logging
from datetime import datetime
from typing import Literal, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_user, get_database
from backend.app.core.config import get_settings
from backend.app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/account", tags=["account"])


class DigestPreferencesResponse(BaseModel):
    digest_frequency: str
    last_digest_sent_at: Optional[datetime]


class DigestPreferencesPatch(BaseModel):
    digest_frequency: Literal["daily", "weekly", "off"]


@router.get("/digest-preferences", response_model=DigestPreferencesResponse)
def get_digest_preferences(
    current_user: User = Depends(get_current_user),
) -> DigestPreferencesResponse:
    return DigestPreferencesResponse(
        digest_frequency=current_user.digest_frequency,
        last_digest_sent_at=current_user.last_digest_sent_at,
    )


@router.patch("/digest-preferences", response_model=DigestPreferencesResponse)
def update_digest_preferences(
    body: DigestPreferencesPatch,
    db: Session = Depends(get_database),
    current_user: User = Depends(get_current_user),
) -> DigestPreferencesResponse:
    current_user.digest_frequency = body.digest_frequency
    db.commit()
    return DigestPreferencesResponse(
        digest_frequency=current_user.digest_frequency,
        last_digest_sent_at=current_user.last_digest_sent_at,
    )


_VARIANT_ROUTING: dict[str, tuple[str, str]] = {
    # (config_attr, tier)
    "plus":         ("lemonsqueezy_variant_id_standard",      "plus"),
    "standard":     ("lemonsqueezy_variant_id_standard",      "plus"),
    "founders":     ("lemonsqueezy_variant_id_founders",       "plus"),
    "plus_founders": ("lemonsqueezy_variant_id_founders",      "plus"),
    "pro":          ("lemonsqueezy_variant_id_pro_standard",   "pro"),
    "pro_founders": ("lemonsqueezy_variant_id_pro_founders",   "pro"),
}


@router.get("/checkout-url")
def get_checkout_url(
    variant: str = Query(default="plus", description="plus | founders | pro | pro_founders"),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Return a LemonSqueezy checkout URL pre-filled with the user's email."""
    settings = get_settings()
    if not settings.lemonsqueezy_api_key:
        raise HTTPException(status_code=503, detail="Payment provider not configured")

    routing = _VARIANT_ROUTING.get(variant)
    if routing is None:
        raise HTTPException(status_code=400, detail=f"Unknown variant: {variant}")
    config_attr, _tier = routing
    variant_id: str = getattr(settings, config_attr, "")
    if not variant_id:
        raise HTTPException(status_code=503, detail="Variant not configured")

    payload = {
        "data": {
            "type": "checkouts",
            "attributes": {
                "checkout_data": {
                    "email": current_user.email,
                    "custom": {"user_id": str(current_user.id)},
                },
            },
            "relationships": {
                "store": {"data": {"type": "stores", "id": settings.lemonsqueezy_store_id}},
                "variant": {"data": {"type": "variants", "id": variant_id}},
            },
        }
    }

    try:
        resp = httpx.post(
            "https://api.lemonsqueezy.com/v1/checkouts",
            json=payload,
            headers={
                "Authorization": f"Bearer {settings.lemonsqueezy_api_key}",
                "Accept": "application/vnd.api+json",
                "Content-Type": "application/vnd.api+json",
            },
            timeout=10.0,
        )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail="Payment provider unreachable") from exc

    if resp.status_code not in (200, 201):
        logger.error(
            "lemonsqueezy_checkout_failed status=%s body=%s", resp.status_code, resp.text[:300]
        )
        raise HTTPException(status_code=502, detail="Could not create checkout session")

    checkout_url: str = resp.json()["data"]["attributes"]["url"]
    return {"checkout_url": checkout_url}
