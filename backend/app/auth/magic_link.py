from __future__ import annotations

from datetime import datetime, UTC
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.templating import Jinja2Templates

from backend.app.auth.session import login_user
from backend.app.core.config import get_settings
from backend.app.db.session import get_db
from backend.app.models.user import User

router = APIRouter(tags=["auth"])

# templates/ is at the project root, 4 levels above this file's package
_TEMPLATES_DIR = Path(__file__).resolve().parents[3] / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

_TOKEN_MAX_AGE = 60 * 15  # 15 minutes


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().magic_link_secret, salt="magic-link")


def generate_magic_token(email: str) -> str:
    return _serializer().dumps(email)


def verify_magic_token(token: str, max_age: int = _TOKEN_MAX_AGE) -> str:
    """Return email from token or raise HTTPException(400)."""
    if max_age <= 0:
        raise HTTPException(status_code=400, detail="Link expired. Request a new one.")
    try:
        return _serializer().loads(token, max_age=max_age)
    except SignatureExpired:
        raise HTTPException(status_code=400, detail="Link expired. Request a new one.")
    except BadSignature:
        raise HTTPException(status_code=400, detail="Invalid link.")


def _get_or_create_user_by_email(db: Session, email: str) -> User:
    user = db.scalars(select(User).where(User.email == email)).first()
    if not user:
        user = User(email=email, access_tier="free")
        db.add(user)
    user.last_login_at = datetime.now(UTC).replace(tzinfo=None)
    db.commit()
    db.refresh(user)
    return user


@router.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse("auth/login.html", {"request": request})


@router.post("/auth/magic-link/request")
async def request_magic_link(
    request: Request,
    email: str = Form(...),
):
    from backend.app.email.resend_client import send_magic_link_email

    email = email.strip().lower()
    settings = get_settings()
    token = generate_magic_token(email)
    magic_url = f"{settings.app_url}/auth/magic-link/verify?token={token}"
    send_magic_link_email(to_email=email, magic_url=magic_url)
    return templates.TemplateResponse(
        "auth/magic_link_sent.html",
        {"request": request, "email": email},
    )


@router.get("/auth/magic-link/verify")
def verify_magic_link(
    request: Request,
    token: str,
    db: Session = Depends(get_db),
):
    email = verify_magic_token(token)
    user = _get_or_create_user_by_email(db, email)
    login_user(request, user)
    return RedirectResponse(url="/dashboard", status_code=302)
