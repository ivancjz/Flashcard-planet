from __future__ import annotations

from fastapi import Request

from backend.app.models.user import User


def login_user(request: Request, user: User) -> None:
    """Write user into session."""
    request.session["user_id"] = str(user.id)


def logout_user(request: Request) -> None:
    request.session.clear()


def get_session_user_id(request: Request) -> str | None:
    return request.session.get("user_id")
