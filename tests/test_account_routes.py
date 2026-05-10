from __future__ import annotations

from unittest.mock import MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.routes.account import router as account_router
from backend.app.api.deps import get_database, get_current_user, get_optional_user


def _make_app(user, db):
    app = FastAPI()
    app.include_router(account_router, prefix="/api/v1")
    app.dependency_overrides[get_database] = lambda: (yield db)
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


class TestDigestPreferences:
    def _user(self, digest_frequency="daily", last_digest_sent_at=None):
        u = MagicMock()
        u.digest_frequency = digest_frequency
        u.last_digest_sent_at = last_digest_sent_at
        return u

    def test_get_preferences_returns_current_frequency(self):
        user = self._user(digest_frequency="weekly")
        db = MagicMock()
        client = _make_app(user, db)
        resp = client.get("/api/v1/account/digest-preferences")
        assert resp.status_code == 200
        assert resp.json()["digest_frequency"] == "weekly"

    def test_patch_preferences_updates_frequency(self):
        user = self._user()
        db = MagicMock()
        client = _make_app(user, db)
        resp = client.patch(
            "/api/v1/account/digest-preferences",
            json={"digest_frequency": "off"},
        )
        assert resp.status_code == 200
        assert user.digest_frequency == "off"
        db.commit.assert_called_once()

    def test_patch_invalid_frequency_returns_422(self):
        user = self._user()
        db = MagicMock()
        client = _make_app(user, db)
        resp = client.patch(
            "/api/v1/account/digest-preferences",
            json={"digest_frequency": "hourly"},
        )
        assert resp.status_code == 422

    def test_unauthenticated_get_returns_401(self):
        app = FastAPI()
        app.include_router(account_router, prefix="/api/v1")
        app.dependency_overrides[get_optional_user] = lambda: None
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/account/digest-preferences")
        assert resp.status_code in (401, 403)
