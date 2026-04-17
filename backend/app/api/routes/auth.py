"""Auth routes.

Discord OAuth2 is used only for account *binding* (linking an existing
session user's Discord identity). Login is handled by magic_link.py and
google_oauth.py.

Web routes (no prefix, mounted at /):
  GET /auth/logout                    — clear session
  GET /account/link-discord           — start Discord binding (requires login)
  GET /account/link-discord/callback  — finish binding

API routes (prefix /api/v1/auth):
  GET  /me    — current user JSON (Bearer token or session)
  POST /token — exchange Discord code for JWT (bot clients)
"""
from __future__ import annotations

import uuid
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.deps import get_database, get_current_user
from backend.app.auth.dependencies import require_user
from backend.app.core.config import get_settings
from backend.app.core.security import create_access_token
from backend.app.models.user import User

DISCORD_AUTH_URL = "https://discord.com/oauth2/authorize"
DISCORD_TOKEN_URL = "https://discord.com/api/oauth2/token"
DISCORD_API_ME_URL = "https://discord.com/api/v10/users/@me"

web_router = APIRouter(tags=["auth"])
api_router = APIRouter(prefix="/auth", tags=["auth"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _discord_bind_redirect_uri(request: Request) -> str:
    settings = get_settings()
    if settings.discord_redirect_uri:
        return settings.discord_redirect_uri
    base = str(request.base_url).rstrip("/")
    return f"{base}/account/link-discord/callback"


def _discord_oauth_url(redirect_uri: str) -> str:
    settings = get_settings()
    params = {
        "client_id": settings.discord_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "identify",
    }
    return f"{DISCORD_AUTH_URL}?{urlencode(params)}"


def _exchange_code(code: str, redirect_uri: str) -> dict:
    settings = get_settings()
    with httpx.Client(timeout=10.0) as client:
        resp = client.post(
            DISCORD_TOKEN_URL,
            data={
                "client_id": settings.discord_client_id,
                "client_secret": settings.discord_client_secret,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        return resp.json()


def _get_discord_user(access_token: str) -> dict:
    with httpx.Client(timeout=10.0) as client:
        resp = client.get(
            DISCORD_API_ME_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.json()


# ── Web routes ─────────────────────────────────────────────────────────────────

@web_router.get("/auth/logout")
def auth_logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/", status_code=302)


@web_router.get("/account/link-discord")
def link_discord_start(
    request: Request,
    current_user: User = Depends(require_user),
) -> RedirectResponse:
    """Redirect logged-in user to Discord OAuth to get their Discord ID."""
    settings = get_settings()
    if not settings.discord_client_id:
        raise HTTPException(status_code=503, detail="Discord OAuth is not configured.")
    redirect_uri = _discord_bind_redirect_uri(request)
    return RedirectResponse(_discord_oauth_url(redirect_uri), status_code=302)


@web_router.get("/account/link-discord/callback")
def link_discord_callback(
    request: Request,
    code: str | None = None,
    error: str | None = None,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_database),
) -> RedirectResponse:
    """Receive Discord OAuth callback; update current user's discord_user_id."""
    if error or not code:
        return RedirectResponse("/account?discord_error=1", status_code=302)
    try:
        redirect_uri = _discord_bind_redirect_uri(request)
        token_data = _exchange_code(code, redirect_uri)
        discord_data = _get_discord_user(token_data["access_token"])
    except Exception:
        return RedirectResponse("/account?discord_error=1", status_code=302)

    current_user.discord_user_id = discord_data["id"]
    current_user.username = discord_data.get("username") or current_user.username
    db.commit()
    return RedirectResponse("/account?discord_linked=1", status_code=302)


# ── API routes (JWT — bot clients) ────────────────────────────────────────────

class UserResponse(BaseModel):
    user_id: uuid.UUID
    email: str | None
    discord_user_id: str | None
    username: str | None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


@api_router.get("/me", response_model=UserResponse)
def auth_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse(
        user_id=current_user.id,
        email=current_user.email,
        discord_user_id=current_user.discord_user_id,
        username=current_user.username,
    )


@api_router.post("/token", response_model=TokenResponse)
def auth_token(
    request: Request,
    code: str,
    db: Session = Depends(get_database),
) -> TokenResponse:
    """Exchange a Discord OAuth2 code for a JWT token (bot / API clients)."""
    settings = get_settings()
    if not settings.discord_client_id:
        raise HTTPException(status_code=503, detail="Discord OAuth2 is not configured.")
    try:
        redirect_uri = _discord_bind_redirect_uri(request)
        token_data = _exchange_code(code, redirect_uri)
        discord_data = _get_discord_user(token_data["access_token"])
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=400, detail=f"Discord OAuth2 failed: {exc}") from exc

    user = db.scalars(
        select(User).where(User.discord_user_id == discord_data["id"])
    ).first()
    if not user:
        raise HTTPException(status_code=404, detail="No account linked to this Discord user.")

    jwt_token = create_access_token(user.id)
    return TokenResponse(
        access_token=jwt_token,
        user=UserResponse(
            user_id=user.id,
            email=user.email,
            discord_user_id=user.discord_user_id,
            username=user.username,
        ),
    )
