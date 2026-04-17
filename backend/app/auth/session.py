from __future__ import annotations

from datetime import datetime, UTC

from fastapi import Request

from backend.app.models.user import User


def login_user(request: Request, user: User) -> None:
    """Write user into session and stamp last_login_at."""
    request.session["user_id"] = str(user.id)
    user.last_login_at = datetime.now(UTC).replace(tzinfo=None)


def logout_user(request: Request) -> None:
    request.session.clear()


def get_session_user_id(request: Request) -> str | None:
    return request.session.get("user_id")
