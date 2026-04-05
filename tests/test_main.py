from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.main import app


class MainAppTests(TestCase):
    @patch("backend.app.main.init_db")
    @patch("backend.app.main.scheduler.start")
    def test_healthz_returns_status_payload(self, start_mock, init_db_mock):
        with TestClient(app) as client:
            response = client.get("/healthz")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"status": "ok", "project": "Flashcard Planet"},
        )
        init_db_mock.assert_called_once()
        start_mock.assert_called_once()
