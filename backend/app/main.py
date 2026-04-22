import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
import uvicorn

from backend.app.api.router import api_router
from backend.app.auth.magic_link import router as magic_link_router
from backend.app.auth.google_oauth import router as google_oauth_router
from backend.app.api.routes.auth import web_router as discord_web_router
from backend.app.core.config import get_settings
from backend.app.db.init_db import init_db
from backend.app.scheduler import build_scheduler
from backend.app.backstage.scheduler import prepare_scheduler_for_startup
from backend.app.site import router as site_router

logging.basicConfig(level=logging.INFO)

settings = get_settings()
scheduler = build_scheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    from backend.app.ingestion.game_data import register_default_clients
    register_default_clients(api_key=settings.pokemon_tcg_api_key)
    if not scheduler.running:
        prepare_scheduler_for_startup(scheduler)
        scheduler.start()
    yield
    if scheduler.running:
        scheduler.shutdown(wait=False)


_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

app = FastAPI(title=settings.project_name, lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, same_site="lax", https_only=False)
app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).resolve().parent / "static"),
    name="static",
)
if (_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(_DIST / "assets")), name="spa-assets")
app.include_router(magic_link_router)
app.include_router(google_oauth_router)
app.include_router(discord_web_router)
app.include_router(api_router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "project": settings.project_name}


app.include_router(site_router)  # SPA catch-all must be last


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=port, reload=False)
