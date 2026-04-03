import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.app.api.router import api_router
from backend.app.core.config import get_settings
from backend.app.db.init_db import init_db
from backend.app.scheduler import build_scheduler
from backend.app.site import router as site_router

logging.basicConfig(level=logging.INFO)

settings = get_settings()
app = FastAPI(title=settings.project_name)
app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).resolve().parent / "static"),
    name="static",
)
app.include_router(site_router)
app.include_router(api_router)

scheduler = build_scheduler()


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    if not scheduler.running:
        scheduler.start()


@app.on_event("shutdown")
def on_shutdown() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
