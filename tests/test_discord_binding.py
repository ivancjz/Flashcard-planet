import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

import backend.app.api.routes.auth as auth_mod


def _make_app():
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test-secret")
    app.include_router(auth_mod.web_router)
    app.include_router(auth_mod.api_router, prefix="/api/v1")
    return app


class DiscordBindingTests(unittest.TestCase):

    def test_discord_login_route_removed(self):
        """Old /auth/login (Discord) must be gone."""
        client = TestClient(_make_app(), raise_server_exceptions=False)
        resp = client.get("/auth/login", follow_redirects=False)
        self.assertEqual(resp.status_code, 404)

    def test_link_discord_route_requires_login(self):
        """/account/link-discord must 401 when not logged in."""
        client = TestClient(_make_app(), raise_server_exceptions=False)
        resp = client.get("/account/link-discord", follow_redirects=False)
        self.assertEqual(resp.status_code, 401)

    def test_auth_me_endpoint_still_exists(self):
        """GET /api/v1/auth/me must still work (bot uses it)."""
        client = TestClient(_make_app(), raise_server_exceptions=False)
        resp = client.get("/api/v1/auth/me")
        # 401 is expected (no auth provided) but route must exist (not 404)
        self.assertNotEqual(resp.status_code, 404)

    def test_auth_logout_still_works(self):
        """GET /auth/logout must still exist."""
        client = TestClient(_make_app(), raise_server_exceptions=False)
        resp = client.get("/auth/logout", follow_redirects=False)
        self.assertIn(resp.status_code, (302, 307))
