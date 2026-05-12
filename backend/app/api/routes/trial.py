from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.api.deps import get_database, get_current_user
from backend.app.models.user import User

TRIAL_DURATION_DAYS = 14
_ACTIVE_STATUSES = {"active", "trialing", "past_due", "cancelled"}

router = APIRouter(prefix="/trial", tags=["trial"])


def _start_trial_for_user(user: Any, *, now: datetime | None = None) -> bool:
    """Set user to trialing state. Returns True if trial was started, False if skipped.

    Idempotent: no-op if user is already on an active/trialing subscription.
    """
    if user.subscription_status in _ACTIVE_STATUSES:
        return False
    if now is None:
        now = datetime.now(timezone.utc)
    user.subscription_status = "trialing"
    user.access_tier = "pro"
    user.trial_started_at = now
    user.trial_ends_at = now + timedelta(days=TRIAL_DURATION_DAYS)
    return True


@router.post("/start")
def start_trial(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database),
) -> dict[str, str]:
    """Start a 14-day Pro trial for a free-tier user. No-op if already active."""
    started = _start_trial_for_user(current_user)
    if started:
        db.commit()
        try:
            from backend.app.email.resend_client import send_trial_started_email
            send_trial_started_email(
                current_user.email,
                current_user.trial_ends_at.strftime("%B %d, %Y"),
            )
        except Exception:
            import logging
            logging.getLogger(__name__).warning(
                "trial_welcome_email_failed user_id=%s", current_user.id
            )
        return {"status": "started", "trial_ends_at": current_user.trial_ends_at.isoformat()}
    return {"status": "already_active", "subscription_status": current_user.subscription_status}
