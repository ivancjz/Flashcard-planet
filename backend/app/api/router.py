from fastapi import APIRouter

from backend.app.backstage.routes import router as backstage_router
from backend.app.backstage.review_routes import router as review_router
from backend.app.api.routes.alerts import router as alerts_router
from backend.app.api.routes.auth import api_router as auth_api_router
from backend.app.api.routes.auth import web_router as auth_web_router
from backend.app.api.routes.health import router as health_router
from backend.app.api.routes.prices import router as prices_router
from backend.app.api.routes.signals import router as signals_router
from backend.app.api.routes.cards import router as cards_router
from backend.app.api.routes.watchlists import router as watchlists_router
from backend.app.api.routes.waitlist import router as waitlist_router
from backend.app.api.routes.account import router as account_router
from backend.app.api.routes.web import router as web_router
from backend.app.core.config import get_settings

settings = get_settings()

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(backstage_router)
api_router.include_router(auth_web_router)                               # /auth/login, /auth/callback, /auth/logout
api_router.include_router(auth_api_router, prefix=settings.api_prefix)  # /api/v1/auth/me
api_router.include_router(alerts_router, prefix=settings.api_prefix)
api_router.include_router(prices_router, prefix=settings.api_prefix)
api_router.include_router(signals_router, prefix=settings.api_prefix)
api_router.include_router(watchlists_router, prefix=settings.api_prefix)
api_router.include_router(cards_router, prefix=settings.api_prefix)
api_router.include_router(review_router, prefix=settings.api_prefix)
api_router.include_router(waitlist_router, prefix=settings.api_prefix)
api_router.include_router(account_router, prefix=settings.api_prefix)
api_router.include_router(web_router)
