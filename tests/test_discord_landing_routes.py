# tests/test_discord_landing_routes.py
import json
import unittest
import uuid
from base64 import b64encode
from pathlib import Path
from unittest.mock import MagicMock, patch

import itsdangerous
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from backend.app.site import router as site_router

_SESSION_SECRET = "test-secret"


def _build_client() -> TestClient:
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key=_SESSION_SECRET, same_site="lax", https_only=False)
    app.mount(
        "/static",
        StaticFiles(directory=Path(__file__).resolve().parents[1] / "backend" / "app" / "static"),
        name="static",
    )
    app.include_router(site_router)
    return TestClient(app, raise_server_exceptions=True)


def _session_cookie(data: dict) -> str:
    """Return a signed session cookie value matching Starlette's SessionMiddleware encoding."""
    signer = itsdangerous.TimestampSigner(_SESSION_SECRET)
    payload = b64encode(json.dumps(data).encode()).decode()
    return signer.sign(payload).decode()


def _mock_user(*, access_tier: str = "free") -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.username = f"testuser_{uuid.uuid4().hex[:6]}"
    user.access_tier = access_tier
    return user


class TestExtractUtmParams(unittest.TestCase):
    def test_returns_present_params(self):
        from backend.app.site import extract_utm_params
        from starlette.requests import Request
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/welcome-from-discord",
            "query_string": b"utm_source=discord&utm_medium=slash_command&utm_campaign=card_discovery",
            "headers": [],
        }
        request = Request(scope)
        result = extract_utm_params(request)
        self.assertEqual(result["utm_source"], "discord")
        self.assertEqual(result["utm_medium"], "slash_command")
        self.assertEqual(result["utm_campaign"], "card_discovery")

    def test_omits_absent_params(self):
        from backend.app.site import extract_utm_params
        from starlette.requests import Request
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/welcome-from-discord",
            "query_string": b"utm_source=discord",
            "headers": [],
        }
        request = Request(scope)
        result = extract_utm_params(request)
        self.assertNotIn("utm_content", result)
        self.assertNotIn("ref", result)


class TestDiscordWelcomeRoute(unittest.TestCase):
    def setUp(self):
        self.client = _build_client()

    def test_unauthenticated_shows_welcome_page(self):
        response = self.client.get("/welcome-from-discord")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"discord", response.content.lower())

    def test_authenticated_redirects_to_dashboard(self):
        user = _mock_user()
        cookie = _session_cookie({"username": user.username, "user_id": str(user.id)})
        response = self.client.get(
            "/welcome-from-discord",
            cookies={"session": cookie},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/dashboard", response.headers["location"])

    def test_authenticated_with_ref_redirects_to_card(self):
        user = _mock_user()
        cookie = _session_cookie({"username": user.username, "user_id": str(user.id)})
        response = self.client.get(
            "/welcome-from-discord?ref=charizard-001",
            cookies={"session": cookie},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("charizard-001", response.headers["location"])


class TestDiscordUpgradeRoute(unittest.TestCase):
    def setUp(self):
        self.client = _build_client()

    def test_unauthenticated_redirects_to_login(self):
        response = self.client.get("/upgrade-from-discord", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/auth/login", response.headers["location"])

    def test_free_user_sees_upgrade_page(self):
        user = _mock_user(access_tier="free")
        cookie = _session_cookie({"username": user.username, "user_id": str(user.id)})
        with patch("backend.app.site.SessionLocal") as mock_sl:
            mock_db = MagicMock()
            mock_sl.return_value.__enter__ = lambda s: mock_db
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)
            mock_db.get.return_value = user
            response = self.client.get(
                "/upgrade-from-discord",
                cookies={"session": cookie},
                follow_redirects=False,
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"pro", response.content.lower())

    def test_pro_user_redirects_to_signals(self):
        user = _mock_user(access_tier="pro")
        cookie = _session_cookie({"username": user.username, "user_id": str(user.id)})
        with patch("backend.app.site.SessionLocal") as mock_sl:
            mock_db = MagicMock()
            mock_sl.return_value.__enter__ = lambda s: mock_db
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)
            mock_db.get.return_value = user
            response = self.client.get(
                "/upgrade-from-discord",
                cookies={"session": cookie},
                follow_redirects=False,
            )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/signals", response.headers["location"])


class TestSignalsExplainedRoute(unittest.TestCase):
    def setUp(self):
        self.client = _build_client()

    def test_public_page_returns_200(self):
        response = self.client.get("/signals/explained")
        self.assertEqual(response.status_code, 200)

    def test_page_contains_signals_content(self):
        response = self.client.get("/signals/explained")
        self.assertIn(b"signal", response.content.lower())
