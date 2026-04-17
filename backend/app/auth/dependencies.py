from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.deps import get_database
from backend.app.auth.session import get_session_user_id
from backend.app.core.config import get_settings
from backend.app.models.user import User


def get_current_user(
    request: Request,
    db: Session = Depends(get_database),
) -> User | None:
    """Returns the session user or None (no exception raised)."""
    try:
        user_id_str = get_session_user_id(request)
    except AssertionError:
        return None
    if not user_id_str:
        return None
    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        return None
    return db.scalars(select(User).where(User.id == user_id)).first()


def require_user(user: User | None = Depends(get_current_user)) -> User:
    """Requires an authenticated session; raises 401 if not logged in."""
    if user is None:
        raise HTTPException(status_code=401, detail="Login required.")
    return user


def require_admin(user: User = Depends(require_user)) -> User:
    """Requires session user's email to be in ADMIN_EMAILS; returns 404 if not."""
    settings = get_settings()
    email = (user.email or "").lower()
    if email not in settings.admin_email_set:
        raise HTTPException(status_code=404)
    return user
