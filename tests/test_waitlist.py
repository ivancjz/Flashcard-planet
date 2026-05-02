from __future__ import annotations

from unittest import TestCase
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.deps import get_database
from backend.app.api.routes.waitlist import router as waitlist_router


def _fake_db():
    yield MagicMock()


def _make_app():
    app = FastAPI()
    app.include_router(waitlist_router, prefix="/api/v1")
    app.dependency_overrides[get_database] = _fake_db
    return app


class WaitlistJoinTests(TestCase):

    @patch("backend.app.api.routes.waitlist.send_waitlist_confirmation_email")
    def test_join_new_email_returns_joined(self, mock_send):
        app = _make_app()
        client = TestClient(app)
        resp = client.post("/api/v1/waitlist", json={"email": "new@example.com"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "joined")
        mock_send.assert_called_once_with("new@example.com")

    @patch("backend.app.api.routes.waitlist.send_waitlist_confirmation_email")
    def test_duplicate_email_returns_already_joined(self, mock_send):
        from sqlalchemy.exc import IntegrityError
        app = _make_app()

        real_db = MagicMock()
        real_db.add = MagicMock()
        real_db.commit = MagicMock(side_effect=IntegrityError("dup", {}, Exception()))
        real_db.rollback = MagicMock()

        def _dup_db():
            yield real_db

        app.dependency_overrides[get_database] = _dup_db
        client = TestClient(app)
        resp = client.post("/api/v1/waitlist", json={"email": "dup@example.com"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "already_joined")
        mock_send.assert_not_called()

    def test_invalid_email_returns_422(self):
        app = _make_app()
        client = TestClient(app)
        resp = client.post("/api/v1/waitlist", json={"email": "not-an-email"})
        self.assertEqual(resp.status_code, 422)

    @patch("backend.app.api.routes.waitlist.send_waitlist_confirmation_email",
           side_effect=Exception("smtp down"))
    def test_email_failure_does_not_fail_request(self, _mock_send):
        app = _make_app()
        client = TestClient(app)
        resp = client.post("/api/v1/waitlist", json={"email": "resilient@example.com"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "joined")
