import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware
import httpx
import uvicorn

from backend.app.api.router import api_router
from backend.app.auth.magic_link import router as magic_link_router
from backend.app.auth.google_oauth import router as google_oauth_router
from backend.app.api.routes.auth import web_router as discord_web_router
from backend.app.core.config import get_settings
from backend.app.db.init_db import init_db
from backend.app.scheduler import build_scheduler
from backend.app.backstage.scheduler import prepare_scheduler_for_startup
from backend.app.db.session import SessionLocal
from backend.app.services.scheduler_run_log_service import cleanup_stale_runs
from backend.app.site import SPAStaticFiles

logging.basicConfig(level=logging.INFO)

settings = get_settings()
scheduler = build_scheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    from backend.app.ingestion.game_data import register_default_clients
    register_default_clients(api_key=settings.pokemon_tcg_api_key)
    if not scheduler.running:
        with SessionLocal() as _db:
            cleanup_stale_runs(_db)
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
app.include_router(magic_link_router)
app.include_router(google_oauth_router)
app.include_router(discord_web_router)
app.include_router(api_router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "project": settings.project_name}


_AGENT_HTML = Path(__file__).resolve().parent / "static" / "agent.html"


@app.get("/agent")
async def agent():
    return FileResponse(str(_AGENT_HTML))


class AgentChatRequest(BaseModel):
    messages: list


@app.post("/api/agent/chat")
async def agent_chat(req: AgentChatRequest):
    async with httpx.AsyncClient() as client:
        res = await client.post(
            "https://integrate.api.nvidia.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {os.environ['NVIDIA_API_KEY']}",
                "Content-Type": "application/json",
            },
            json={
                "model": "moonshotai/kimi-k2-instruct",
                "max_tokens": 4096,
                "temperature": 0.6,
                "top_p": 0.9,
                "messages": req.messages,
            },
            timeout=30,
        )
        return res.json()


# SPA: serve all of frontend/dist/ at /.
# SPAStaticFiles serves exact files (JS, CSS, favicon, icons) directly and
# falls back to index.html for any unmatched path (React Router handles it).
# Must be mounted LAST so API routes above are checked first.
if _DIST.exists():
    app.mount("/", SPAStaticFiles(directory=str(_DIST), html=True), name="spa")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=port, reload=False)
