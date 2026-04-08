from unittest import TestCase
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.deps import get_database
from backend.app.backstage.routes import router as backstage_router


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
    def test_unconfigured_admin_key_with_no_header_returns_403(self, get_settings_mock):
        get_settings_mock.return_value.admin_api_key = ""

        response = self.client.get("/admin/gaps")

        self.assertEqual(response.status_code, 403)

    # ------------------------------------------------------------------
    # Correct key → 200 with gap report payload
    # ------------------------------------------------------------------

    @patch("backend.app.backstage.routes.get_gap_report")
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

    @patch("backend.app.backstage.routes.get_gap_report")
    @patch("backend.app.backstage.routes.get_settings")
    def test_near_miss_key_returns_403(self, get_settings_mock, get_gap_report_mock):
        get_settings_mock.return_value.admin_api_key = "secret-key"
        get_gap_report_mock.return_value = {}

        response = self.client.get("/admin/gaps", headers={"X-Admin-Key": "secret-ke"})

        self.assertEqual(response.status_code, 403)
