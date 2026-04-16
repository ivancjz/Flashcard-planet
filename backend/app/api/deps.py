from __future__ import annotations

import uuid
from collections.abc import Generator

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.permissions import Feature, can, get_capabilities
from backend.app.core.security import decode_access_token
from backend.app.db.session import get_db
from backend.app.models.user import User

_bearer = HTTPBearer(auto_error=False)


def get_database() -> Generator[Session, None, None]:
    yield from get_db()


def _user_from_token(token: str, db: Session) -> User | None:
    user_id_str = decode_access_token(token)
    if not user_id_str:
        return None
    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        return None
    return db.scalars(select(User).where(User.id == user_id)).first()


def get_optional_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_database),
) -> User | None:
    """Returns the current user from a JWT bearer token or session cookie, or None."""
    # 1. Bearer token (API clients)
    if credentials and credentials.credentials:
        return _user_from_token(credentials.credentials, db)
    # 2. Session cookie (web UI)
    jwt = request.session.get("jwt")
    if jwt:
        return _user_from_token(jwt, db)
    return None


def get_current_user(user: User | None = Depends(get_optional_user)) -> User:
    """Requires authentication — raises 401 if not logged in."""
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    return user


def require_tier(feature: Feature):
    """FastAPI dependency factory that enforces a feature gate."""
    def _dep(user: User = Depends(get_current_user)) -> User:
        if not can(user.access_tier, feature):
            raise HTTPException(status_code=403, detail="Pro subscription required.")
        return user
    return _dep


def get_user_capabilities(
    user: User | None = Depends(get_optional_user),
) -> frozenset[Feature]:
    """Returns the frozenset of Features for the current user (or empty if unauthenticated)."""
    if user is None:
        return frozenset()
    return get_capabilities(user.access_tier)
