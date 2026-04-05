from fastapi import APIRouter

from backend.app.backstage.routes import router as backstage_router
from backend.app.api.routes.alerts import router as alerts_router
from backend.app.api.routes.health import router as health_router
from backend.app.api.routes.prices import router as prices_router
from backend.app.api.routes.watchlists import router as watchlists_router
from backend.app.core.config import get_settings

settings = get_settings()

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(backstage_router)
api_router.include_router(alerts_router, prefix=settings.api_prefix)
api_router.include_router(prices_router, prefix=settings.api_prefix)
api_router.include_router(watchlists_router, prefix=settings.api_prefix)
