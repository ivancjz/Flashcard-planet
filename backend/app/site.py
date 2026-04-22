from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse

router = APIRouter(include_in_schema=False)

_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


@router.get("/{full_path:path}")
async def serve_spa(full_path: str):
    index = _DIST / "index.html"
    if not index.exists():
        return JSONResponse(
            {"error": "Frontend not built. Run: cd frontend && npm run build"},
            status_code=503,
        )
    return FileResponse(index)
