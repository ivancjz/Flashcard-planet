from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/health", response_model=None)
def healthcheck(db: Session = Depends(get_db)) -> dict[str, str] | JSONResponse:
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "db": "unreachable"},
        )

    return {
        "status": "ok",
        "db": "ok",
        "checked_at": datetime.now(UTC).isoformat(),
    }
