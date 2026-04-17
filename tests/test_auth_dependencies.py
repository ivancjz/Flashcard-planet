import unittest
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware


class AuthDependenciesTests(unittest.TestCase):

    def _make_app(self):
        app = FastAPI()
        app.add_middleware(SessionMiddleware, secret_key="test-secret")
        return app

    def test_require_user_returns_401_when_no_session(self):
        from backend.app.auth.dependencies import require_user, get_current_user
        app = self._make_app()

        @app.get("/protected")
        def protected(u=__import__('fastapi').Depends(require_user)):
            return {"ok": True}

        # Override get_current_user to return None (no user in session)
        app.dependency_overrides[get_current_user] = lambda: None
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/protected")
        self.assertEqual(resp.status_code, 401)

    def test_require_admin_returns_404_for_non_admin(self):
        from backend.app.auth.dependencies import require_admin, get_current_user
        app = self._make_app()

        @app.get("/backstage")
        def backstage(u=__import__('fastapi').Depends(require_admin)):
            return {"ok": True}

        fake_user = MagicMock()
        fake_user.email = "nobody@example.com"
        app.dependency_overrides[get_current_user] = lambda: fake_user

        with patch("backend.app.auth.dependencies.get_settings") as mock_settings:
            mock_settings.return_value.admin_email_set = frozenset({"admin@example.com"})
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/backstage")
            self.assertEqual(resp.status_code, 404)

    def test_require_admin_passes_for_admin_email(self):
        from backend.app.auth.dependencies import require_admin, get_current_user
        app = self._make_app()

        @app.get("/backstage")
        def backstage(u=__import__('fastapi').Depends(require_admin)):
            return {"ok": True}

        fake_user = MagicMock()
        fake_user.email = "admin@example.com"
        app.dependency_overrides[get_current_user] = lambda: fake_user

        with patch("backend.app.auth.dependencies.get_settings") as mock_settings:
            mock_settings.return_value.admin_email_set = frozenset({"admin@example.com"})
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/backstage")
            self.assertEqual(resp.status_code, 200)
