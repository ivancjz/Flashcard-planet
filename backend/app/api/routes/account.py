from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_user, get_database
from backend.app.models.user import User

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
