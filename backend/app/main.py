import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import uvicorn

from backend.app.api.router import api_router
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
    if not scheduler.running:
        prepare_scheduler_for_startup(scheduler)
        scheduler.start()
    yield
    if scheduler.running:
        scheduler.shutdown(wait=False)


app = FastAPI(title=settings.project_name, lifespan=lifespan)
app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).resolve().parent / "static"),
    name="static",
)
app.include_router(site_router)
app.include_router(api_router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "project": settings.project_name}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=port, reload=False)
