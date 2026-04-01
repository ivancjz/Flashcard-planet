import logging

from fastapi import FastAPI

from backend.app.api.router import api_router
from backend.app.core.config import get_settings
from backend.app.scheduler import build_scheduler

logging.basicConfig(level=logging.INFO)

settings = get_settings()
app = FastAPI(title=settings.project_name)
app.include_router(api_router)

scheduler = build_scheduler()


@app.on_event("startup")
def on_startup() -> None:
    if not scheduler.running:
        scheduler.start()


@app.on_event("shutdown")
def on_shutdown() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
