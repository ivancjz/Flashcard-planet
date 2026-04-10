"""Discord OAuth2 authentication routes.

Web flow:
  GET /auth/login      → redirect to Discord
  GET /auth/callback   → exchange code, upsert User, set session, redirect
  GET /auth/logout     → clear session, redirect to /

API:
  GET /api/v1/auth/me   → current user JSON (requires Bearer token or session)
  POST /api/v1/auth/token → exchange Discord code for JWT (for API/bot clients)
"""
from __future__ import annotations

import uuid
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.api.deps import get_database, get_current_user
from backend.app.core.config import get_settings
from backend.app.core.security import create_access_token
from backend.app.models.user import User
from backend.app.services.watchlist_service import get_or_create_user

DISCORD_AUTH_URL = "https://discord.com/oauth2/authorize"
DISCORD_TOKEN_URL = "https://discord.com/api/oauth2/token"
DISCORD_API_ME_URL = "https://discord.com/api/v10/users/@me"

web_router = APIRouter(tags=["auth"])       # mounted at / (no prefix) — for redirect flows
api_router = APIRouter(prefix="/auth", tags=["auth"])  # mounted under /api/v1


# ── Helpers ───────────────────────────────────────────────────────────────────

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
        response = client.post(
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
        response.raise_for_status()
        return response.json()


def _get_discord_user(access_token: str) -> dict:
    with httpx.Client(timeout=10.0) as client:
        response = client.get(
            DISCORD_API_ME_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        response.raise_for_status()
        return response.json()


def _upsert_user(db: Session, discord_data: dict) -> User:
    user = get_or_create_user(db, discord_data["id"])
    user.username = discord_data.get("username") or user.username
    user.global_name = discord_data.get("global_name") or user.global_name
    user.discriminator = discord_data.get("discriminator") or user.discriminator
    db.commit()
    return user


def _resolve_redirect_uri(request: Request) -> str:
    """Use configured URI if set; otherwise auto-derive from the current request."""
    settings = get_settings()
    if settings.discord_redirect_uri:
        return settings.discord_redirect_uri
    base = str(request.base_url).rstrip("/")
    return f"{base}/auth/callback"


# ── Web routes (session-based) ────────────────────────────────────────────────

@web_router.get("/auth/login")
def auth_login(request: Request) -> RedirectResponse:
    settings = get_settings()
    if not settings.discord_client_id:
        raise HTTPException(status_code=503, detail="Discord OAuth2 is not configured.")
    redirect_uri = _resolve_redirect_uri(request)
    return RedirectResponse(_discord_oauth_url(redirect_uri), status_code=302)


@web_router.get("/auth/callback")
def auth_callback(
    request: Request,
    code: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_database),
) -> RedirectResponse:
    if error or not code:
        return RedirectResponse("/?auth_error=1", status_code=302)

    try:
        redirect_uri = _resolve_redirect_uri(request)
        token_data = _exchange_code(code, redirect_uri)
        discord_data = _get_discord_user(token_data["access_token"])
        user = _upsert_user(db, discord_data)
    except Exception:
        return RedirectResponse("/?auth_error=1", status_code=302)

    jwt_token = create_access_token(user.id)
    request.session["user_id"] = str(user.id)
    request.session["discord_user_id"] = user.discord_user_id
    request.session["username"] = user.global_name or user.username or "User"
    request.session["jwt"] = jwt_token
    return RedirectResponse("/dashboard", status_code=302)


@web_router.get("/auth/logout")
def auth_logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/", status_code=302)


# ── API routes (JWT-based) ────────────────────────────────────────────────────

class UserResponse(BaseModel):
    user_id: uuid.UUID
    discord_user_id: str
    username: str | None
    global_name: str | None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


@api_router.get("/me", response_model=UserResponse)
def auth_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse(
        user_id=current_user.id,
        discord_user_id=current_user.discord_user_id,
        username=current_user.username,
        global_name=current_user.global_name,
    )


@api_router.post("/token", response_model=TokenResponse)
def auth_token(
    request: Request,
    code: str,
    db: Session = Depends(get_database),
) -> TokenResponse:
    """Exchange a Discord OAuth2 code for a JWT access token."""
    settings = get_settings()
    if not settings.discord_client_id:
        raise HTTPException(status_code=503, detail="Discord OAuth2 is not configured.")
    try:
        redirect_uri = _resolve_redirect_uri(request)
        token_data = _exchange_code(code, redirect_uri)
        discord_data = _get_discord_user(token_data["access_token"])
        user = _upsert_user(db, discord_data)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=400, detail=f"Discord OAuth2 failed: {exc}") from exc

    jwt_token = create_access_token(user.id)
    return TokenResponse(
        access_token=jwt_token,
        user=UserResponse(
            user_id=user.id,
            discord_user_id=user.discord_user_id,
            username=user.username,
            global_name=user.global_name,
        ),
    )
