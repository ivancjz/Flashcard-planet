from __future__ import annotations

from datetime import datetime, UTC

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.config import Config

from backend.app.auth.session import login_user
from backend.app.core.config import get_settings
from backend.app.db.session import get_db
from backend.app.models.user import User

router = APIRouter(tags=["auth"])

_GOOGLE_CONF_URL = "https://accounts.google.com/.well-known/openid-configuration"


def _oauth_client():
    settings = get_settings()
    config = Config(environ={
        "GOOGLE_CLIENT_ID": settings.google_client_id,
        "GOOGLE_CLIENT_SECRET": settings.google_client_secret,
    })
    oauth = OAuth(config)
    oauth.register(
        name="google",
        server_metadata_url=_GOOGLE_CONF_URL,
        client_kwargs={"scope": "openid email profile"},
    )
    return oauth.google


@router.get("/auth/google/login")
async def google_login(request: Request):
    settings = get_settings()
    if not settings.google_client_id:
        raise HTTPException(status_code=503, detail="Google OAuth is not configured.")
    redirect_uri = f"{settings.app_url}/auth/google/callback"
    client = _oauth_client()
    return await client.authorize_redirect(request, redirect_uri)


@router.get("/auth/google/callback")
async def google_callback(request: Request, db: Session = Depends(get_db)):
    try:
        client = _oauth_client()
        token = await client.authorize_access_token(request)
    except Exception:
        return RedirectResponse("/login?error=google_failed", status_code=302)

    user_info = token.get("userinfo") or {}
    email = (user_info.get("email") or "").lower()
    google_id = user_info.get("sub", "")

    if not email:
        return RedirectResponse("/login?error=no_email", status_code=302)

    user = db.scalars(select(User).where(User.email == email)).first()
    if not user:
        user = User(email=email, google_id=google_id, access_tier="free")
        db.add(user)
    else:
        if not user.google_id:
            user.google_id = google_id

    user.last_login_at = datetime.now(UTC).replace(tzinfo=None)
    db.commit()
    db.refresh(user)

    login_user(request, user)
    return RedirectResponse("/dashboard", status_code=302)
