"""Auth routes.

Login is handled by magic_link.py and google_oauth.py.

Web routes (no prefix, mounted at /):
  GET /auth/logout  — clear session

API routes (prefix /api/v1/auth):
  GET /me  — current user JSON (Bearer token or session)
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from backend.app.api.deps import get_current_user
from backend.app.core.permissions import resolve_tier
from backend.app.models.user import User

web_router = APIRouter(tags=["auth"])
api_router = APIRouter(prefix="/auth", tags=["auth"])


# ── Web routes ─────────────────────────────────────────────────────────────────

@web_router.get("/auth/logout")
def auth_logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/", status_code=302)


# ── API routes ────────────────────────────────────────────────────────────────

class UserResponse(BaseModel):
    user_id: uuid.UUID
    email: str | None
    discord_user_id: str | None
    username: str | None
    tier: str  # 'free' | 'pro' — resolved via DEV_PRO_EMAILS + access_tier


@api_router.get("/me", response_model=UserResponse)
def auth_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse(
        user_id=current_user.id,
        email=current_user.email,
        discord_user_id=current_user.discord_user_id,
        username=current_user.username,
        tier=resolve_tier(current_user.email, current_user.access_tier, current_user.subscription_tier, current_user.subscription_status),
    )
