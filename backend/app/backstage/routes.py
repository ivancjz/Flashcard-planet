import logging
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from backend.app.api.deps import get_database
from backend.app.backstage.gap_detector import get_gap_report
from backend.app.core.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


def require_admin_key(x_admin_key: str | None = Header(default=None, alias="X-Admin-Key")) -> None:
    """Enforce admin API key authentication for protected routes.

    Returns:
        401 — X-Admin-Key header is absent (no credentials provided).
        403 — X-Admin-Key header is present but incorrect.

    If ADMIN_API_KEY is not configured (empty string) the endpoint is
    inaccessible to everyone. A warning is logged at startup so the
    operator knows the route is locked.
    """
    expected_key = get_settings().admin_api_key

    if not expected_key:
        logger.warning(
            "ADMIN_API_KEY is not configured. "
            "All requests to admin endpoints will be rejected until it is set."
        )
        raise HTTPException(status_code=403, detail="Admin key not configured on this server.")

    if not x_admin_key:
        raise HTTPException(
            status_code=401,
            detail="Missing X-Admin-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if not secrets.compare_digest(x_admin_key, expected_key):
        raise HTTPException(status_code=403, detail="Forbidden")


@router.get("/gaps")
def admin_gaps(
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_database),
):
    return jsonable_encoder(get_gap_report(db))
