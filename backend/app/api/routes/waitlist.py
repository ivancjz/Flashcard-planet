from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.api.deps import get_database
from backend.app.email.resend_client import send_waitlist_confirmation_email
from backend.app.models.pro_waitlist import ProWaitlist

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/waitlist", tags=["waitlist"])


class WaitlistRequest(BaseModel):
    email: EmailStr
    source_page: str = "landing"
    locale: str = "en"


class WaitlistResponse(BaseModel):
    status: str  # "joined" | "already_joined"


@router.post("", response_model=WaitlistResponse)
def join_waitlist(
    body: WaitlistRequest,
    request: Request,
    db: Session = Depends(get_database),
) -> WaitlistResponse:
    ip_country = request.headers.get("CF-IPCountry")  # Cloudflare header (Railway passes it through)

    normalised_email = body.email.lower().strip()

    entry = ProWaitlist(
        email=normalised_email,
        source_page=body.source_page[:64],
        locale=body.locale[:16],
        ip_country=ip_country[:4] if ip_country else None,
    )
    try:
        db.add(entry)
        db.commit()
    except IntegrityError:
        db.rollback()
        return WaitlistResponse(status="already_joined")

    try:
        send_waitlist_confirmation_email(normalised_email)
    except Exception:
        logger.warning("waitlist_confirmation_email_failed email=%s", body.email)

    return WaitlistResponse(status="joined")
