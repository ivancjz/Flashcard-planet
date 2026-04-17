from unittest import TestCase
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.deps import get_database
from backend.app.backstage.routes import router as backstage_router
from backend.app.models.enums import AccessTier


def _fake_db():
    yield None


class BackstageRoutesTests(TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(backstage_router)
        app.dependency_overrides[get_database] = _fake_db
        self.app = app
        self.client = TestClient(app)

    def tearDown(self):
        self.app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # No key header → 401
    # ------------------------------------------------------------------

    @patch("backend.app.backstage.routes.get_settings")
    def test_missing_key_header_returns_401(self, get_settings_mock):
        get_settings_mock.return_value.admin_api_key = "secret-key"

        response = self.client.get("/admin/gaps")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Missing X-Admin-Key header.")
        self.assertIn("WWW-Authenticate", response.headers)

    # ------------------------------------------------------------------
    # Wrong key → 403
    # ------------------------------------------------------------------

    @patch("backend.app.backstage.routes.get_settings")
    def test_wrong_key_returns_403(self, get_settings_mock):
        get_settings_mock.return_value.admin_api_key = "secret-key"

        response = self.client.get("/admin/gaps", headers={"X-Admin-Key": "wrong-key"})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "Forbidden")

    # ------------------------------------------------------------------
    # Unconfigured key (empty string) → 403 regardless of what is sent
    # ------------------------------------------------------------------

    @patch("backend.app.backstage.routes.get_settings")
    def test_unconfigured_admin_key_returns_403(self, get_settings_mock):
        get_settings_mock.return_value.admin_api_key = ""

        response = self.client.get("/admin/gaps", headers={"X-Admin-Key": "any-key"})

        self.assertEqual(response.status_code, 403)
        self.assertIn("not configured", response.json()["detail"])

    @patch("backend.app.backstage.routes.get_settings")
    def test_unconfigured_admin_key_with_no_header_returns_401(self, get_settings_mock):
        # No API key configured, no X-Admin-Key header, no session → 401 (no credentials)
        get_settings_mock.return_value.admin_api_key = ""
        get_settings_mock.return_value.admin_email_set = frozenset()

        response = self.client.get("/admin/gaps")

        self.assertEqual(response.status_code, 401)

    # ------------------------------------------------------------------
    # Correct key → 200 with gap report payload
    # ------------------------------------------------------------------

    @patch("backend.app.backstage.gap_detector.get_gap_report")
    @patch("backend.app.backstage.routes.get_settings")
    def test_correct_key_returns_gap_report_payload(self, get_settings_mock, get_gap_report_mock):
        get_settings_mock.return_value.admin_api_key = "secret-key"
        get_gap_report_mock.return_value = {
            "total_assets": 10,
            "covered_assets": 7,
            "gap_count": 3,
            "priority_queue": [],
        }

        response = self.client.get("/admin/gaps", headers={"X-Admin-Key": "secret-key"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["gap_count"], 3)
        self.assertEqual(response.json()["covered_assets"], 7)

    # ------------------------------------------------------------------
    # Timing-safe: correct key passes, near-miss does not
    # ------------------------------------------------------------------

    @patch("backend.app.backstage.gap_detector.get_gap_report")
    @patch("backend.app.backstage.routes.get_settings")
    def test_near_miss_key_returns_403(self, get_settings_mock, get_gap_report_mock):
        get_settings_mock.return_value.admin_api_key = "secret-key"
        get_gap_report_mock.return_value = {}

        response = self.client.get("/admin/gaps", headers={"X-Admin-Key": "secret-ke"})

        self.assertEqual(response.status_code, 403)

    # Session email whitelist tests (auth v2)

    @patch("backend.app.backstage.routes.get_settings")
    def test_session_admin_email_grants_access(self, get_settings_mock):
        """A session user whose email is in ADMIN_EMAILS can access admin routes."""
        get_settings_mock.return_value.admin_api_key = ""  # API key disabled
        get_settings_mock.return_value.admin_email_set = frozenset({"admin@example.com"})

        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from starlette.middleware.sessions import SessionMiddleware
        from backend.app.api.deps import get_database
        from backend.app.auth import dependencies as auth_deps

        app2 = FastAPI()
        app2.add_middleware(SessionMiddleware, secret_key="test-secret")
        app2.include_router(backstage_router)

        def _fake_db():
            yield None

        app2.dependency_overrides[get_database] = _fake_db

        fake_user = MagicMock()
        fake_user.email = "admin@example.com"
        app2.dependency_overrides[auth_deps.get_current_user] = lambda: fake_user

        with patch("backend.app.backstage.gap_detector.get_gap_report", return_value=[]):
            client2 = TestClient(app2, raise_server_exceptions=False)
            resp = client2.get("/admin/gaps")
            self.assertEqual(resp.status_code, 200)

    @patch("backend.app.backstage.routes.get_settings")
    def test_non_admin_session_returns_404(self, get_settings_mock):
        """A session user NOT in ADMIN_EMAILS gets 404 (not 403, to hide backend existence)."""
        get_settings_mock.return_value.admin_api_key = ""
        get_settings_mock.return_value.admin_email_set = frozenset({"admin@example.com"})

        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from starlette.middleware.sessions import SessionMiddleware
        from backend.app.api.deps import get_database
        from backend.app.auth import dependencies as auth_deps

        app3 = FastAPI()
        app3.add_middleware(SessionMiddleware, secret_key="test-secret")
        app3.include_router(backstage_router)

        def _fake_db():
            yield None

        app3.dependency_overrides[get_database] = _fake_db

        fake_user = MagicMock()
        fake_user.email = "hacker@example.com"
        app3.dependency_overrides[auth_deps.get_current_user] = lambda: fake_user

        client3 = TestClient(app3, raise_server_exceptions=False)
        resp = client3.get("/admin/gaps")
        self.assertEqual(resp.status_code, 404)


class AdminSetUserTierTests(TestCase):
    """Tests for PATCH /admin/users/{discord_user_id}/tier."""

    def _make_client(self, fake_db_fn=None):
        app = FastAPI()
        app.include_router(backstage_router)
        app.dependency_overrides[get_database] = fake_db_fn or _fake_db
        client = TestClient(app)
        return app, client

    # ------------------------------------------------------------------
    # Auth guard (re-uses require_admin_key — one smoke test is enough)
    # ------------------------------------------------------------------

    @patch("backend.app.backstage.routes.get_settings")
    def test_missing_key_returns_401(self, get_settings_mock):
        get_settings_mock.return_value.admin_api_key = "secret-key"
        _, client = self._make_client()

        response = client.patch("/admin/users/123/tier?tier=pro")

        self.assertEqual(response.status_code, 401)

    # ------------------------------------------------------------------
    # User not found → 404
    # ------------------------------------------------------------------

    @patch("backend.app.backstage.routes.get_settings")
    def test_unknown_user_returns_404(self, get_settings_mock):
        get_settings_mock.return_value.admin_api_key = "secret-key"

        db_mock = MagicMock()
        db_mock.scalars.return_value.first.return_value = None

        def _db_with_mock():
            yield db_mock

        _, client = self._make_client(_db_with_mock)

        response = client.patch(
            "/admin/users/nonexistent/tier?tier=pro",
            headers={"X-Admin-Key": "secret-key"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "User not found.")

    # ------------------------------------------------------------------
    # Valid user → tier updated, response reflects new tier
    # ------------------------------------------------------------------

    @patch("backend.app.backstage.routes.set_user_tier")
    @patch("backend.app.backstage.routes.get_settings")
    def test_valid_user_returns_ok(self, get_settings_mock, set_user_tier_mock):
        get_settings_mock.return_value.admin_api_key = "secret-key"

        fake_user = MagicMock()
        fake_user.access_tier = "pro"

        def _side_effect(db, user, tier):
            user.access_tier = tier.value

        set_user_tier_mock.side_effect = _side_effect

        db_mock = MagicMock()
        db_mock.scalars.return_value.first.return_value = fake_user

        def _db_with_mock():
            yield db_mock

        _, client = self._make_client(_db_with_mock)

        response = client.patch(
            "/admin/users/999/tier?tier=pro",
            headers={"X-Admin-Key": "secret-key"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["discord_user_id"], "999")
        self.assertEqual(body["tier"], "pro")

    # ------------------------------------------------------------------
    # set_user_tier is called exactly once with the right arguments
    # ------------------------------------------------------------------

    @patch("backend.app.backstage.routes.set_user_tier")
    @patch("backend.app.backstage.routes.get_settings")
    def test_set_user_tier_called_with_correct_args(self, get_settings_mock, set_user_tier_mock):
        get_settings_mock.return_value.admin_api_key = "secret-key"

        fake_user = MagicMock()
        fake_user.access_tier = "free"
        set_user_tier_mock.side_effect = lambda db, user, tier: setattr(user, "access_tier", tier.value)

        db_mock = MagicMock()
        db_mock.scalars.return_value.first.return_value = fake_user

        def _db_with_mock():
            yield db_mock

        _, client = self._make_client(_db_with_mock)

        client.patch(
            "/admin/users/777/tier?tier=pro",
            headers={"X-Admin-Key": "secret-key"},
        )

        set_user_tier_mock.assert_called_once()
        _, call_user, call_tier = set_user_tier_mock.call_args.args
        self.assertIs(call_user, fake_user)
        self.assertEqual(call_tier, AccessTier.PRO)

    # ------------------------------------------------------------------
    # Invalid tier value → 422 (FastAPI validation)
    # ------------------------------------------------------------------

    @patch("backend.app.backstage.routes.get_settings")
    def test_invalid_tier_value_returns_422(self, get_settings_mock):
        get_settings_mock.return_value.admin_api_key = "secret-key"
        _, client = self._make_client()

        response = client.patch(
            "/admin/users/123/tier?tier=diamond",
            headers={"X-Admin-Key": "secret-key"},
        )

        self.assertEqual(response.status_code, 422)
