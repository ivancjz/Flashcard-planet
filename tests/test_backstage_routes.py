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

    @patch("backend.app.backstage.routes.get_settings")
    def test_admin_gaps_returns_403_when_admin_key_is_missing_or_invalid(self, get_settings_mock):
        get_settings_mock.return_value.admin_api_key = "secret-key"

        response = self.client.get("/admin/gaps")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "Forbidden")

    @patch("backend.app.backstage.routes.get_gap_report")
    @patch("backend.app.backstage.routes.get_settings")
    def test_admin_gaps_returns_gap_report_payload(self, get_settings_mock, get_gap_report_mock):
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
