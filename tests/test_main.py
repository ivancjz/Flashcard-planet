from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.main import app


class MainAppTests(TestCase):
    @patch("backend.app.main.init_db")
    @patch("backend.app.main.scheduler")
    def test_healthz_returns_status_payload(self, mock_scheduler, mock_init_db):
        mock_scheduler.running = False
        with TestClient(app) as client:
            response = client.get("/healthz")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"status": "ok", "project": "Flashcard Planet"},
        )
        mock_init_db.assert_called_once()
        mock_scheduler.start.assert_called_once()

    @patch("backend.app.main.init_db")
    @patch("backend.app.main.scheduler")
    def test_lifespan_shuts_down_running_scheduler(self, mock_scheduler, mock_init_db):
        mock_scheduler.running = True
        with TestClient(app):
            pass
        mock_scheduler.shutdown.assert_called_once_with(wait=False)

    @patch("backend.app.main.init_db")
    @patch("backend.app.main.scheduler")
    def test_lifespan_does_not_start_already_running_scheduler(self, mock_scheduler, mock_init_db):
        mock_scheduler.running = True
        with TestClient(app):
            pass
        mock_scheduler.start.assert_not_called()
