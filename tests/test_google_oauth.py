import unittest
from unittest.mock import patch, MagicMock, AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from backend.app.auth.google_oauth import router


def _make_app():
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test-secret")
    app.include_router(router)
    return app


class GoogleOAuthTests(unittest.TestCase):

    def test_google_login_returns_503_when_unconfigured(self):
        with patch("backend.app.auth.google_oauth.get_settings") as mock_settings:
            mock_settings.return_value.google_client_id = ""
            mock_settings.return_value.google_client_secret = ""
            mock_settings.return_value.app_url = "http://localhost:8000"
            client = TestClient(_make_app(), raise_server_exceptions=False)
            resp = client.get("/auth/google/login", follow_redirects=False)
            self.assertEqual(resp.status_code, 503)

    def test_google_login_redirects_when_configured(self):
        with patch("backend.app.auth.google_oauth.get_settings") as mock_settings:
            mock_settings.return_value.google_client_id = "fake-client-id"
            mock_settings.return_value.google_client_secret = "fake-secret"
            mock_settings.return_value.app_url = "http://localhost:8000"
            with patch("backend.app.auth.google_oauth._oauth_client") as mock_oauth:
                mock_client = MagicMock()
                mock_client.authorize_redirect = AsyncMock(
                    return_value=__import__('fastapi').responses.RedirectResponse(
                        "https://accounts.google.com/o/oauth2/auth?...", status_code=302
                    )
                )
                mock_oauth.return_value = mock_client
                client = TestClient(_make_app(), raise_server_exceptions=False)
                resp = client.get("/auth/google/login", follow_redirects=False)
                self.assertIn(resp.status_code, (302, 307))
