import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from backend.app.api.deps import get_database
from backend.app.backstage.gap_detector import get_gap_report
from backend.app.core.config import get_settings

router = APIRouter(prefix="/admin", tags=["admin"])


def require_admin_key(x_admin_key: str | None = Header(default=None, alias="X-Admin-Key")) -> None:
    expected_key = get_settings().admin_api_key
    if not x_admin_key or not secrets.compare_digest(x_admin_key, expected_key):
        raise HTTPException(status_code=403, detail="Forbidden")


@router.get("/gaps")
def admin_gaps(
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_database),
):
    return jsonable_encoder(get_gap_report(db))
