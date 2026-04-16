from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from backend.app.models.enums import AccessTier
from backend.app.models.user import User


def set_user_tier(db: Session, user: User, tier: AccessTier) -> User:
    """Set the user's access tier and record when the change occurred.

    This is the single entry point for all tier changes. Future billing
    webhook handlers should call this function — no other code writes
    access_tier directly.
    """
    user.access_tier = tier.value
    user.tier_changed_at = datetime.now(UTC)
    db.add(user)
    db.flush()
    return user
