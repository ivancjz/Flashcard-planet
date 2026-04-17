import unittest
from unittest.mock import patch, MagicMock


class MainAuthRoutesTests(unittest.TestCase):

    def _get_client(self):
        # Patch init_db and scheduler to avoid DB connections in tests
        with patch("backend.app.db.init_db.init_db"):
            with patch("backend.app.main.build_scheduler") as mock_sched:
                sched = MagicMock()
                sched.running = False
                mock_sched.return_value = sched
                from fastapi.testclient import TestClient
                from backend.app.main import app
                return TestClient(app, raise_server_exceptions=False)

    def test_login_page_returns_200(self):
        """GET /login must return 200 (the magic link login page)."""
        client = self._get_client()
        resp = client.get("/login", follow_redirects=False)
        self.assertEqual(resp.status_code, 200)

    def test_magic_link_request_route_exists(self):
        """POST /auth/magic-link/request must exist (422 = route found, bad body)."""
        client = self._get_client()
        resp = client.post("/auth/magic-link/request")
        self.assertNotEqual(resp.status_code, 404)

    def test_google_login_route_exists(self):
        """GET /auth/google/login must exist (503 when unconfigured is fine)."""
        client = self._get_client()
        resp = client.get("/auth/google/login", follow_redirects=False)
        self.assertNotEqual(resp.status_code, 404)

    def test_link_discord_route_exists(self):
        """GET /account/link-discord must exist (401 when not logged in is fine)."""
        client = self._get_client()
        resp = client.get("/account/link-discord", follow_redirects=False)
        self.assertNotEqual(resp.status_code, 404)
