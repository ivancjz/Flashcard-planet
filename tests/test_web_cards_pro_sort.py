from __future__ import annotations

from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.deps import get_database
from backend.app.api.routes.web import router as web_router


def _make_client() -> TestClient:
    """Fresh TestClient with a mock DB that returns 0 rows for any query."""
    db = MagicMock()
    count_mock = MagicMock()
    count_mock.scalar.return_value = 0
    data_mock = MagicMock()
    data_mock.fetchall.return_value = []
    db.execute.side_effect = [count_mock, data_mock]

    app = FastAPI()
    app.include_router(web_router)

    def _gen():
        yield db

    app.dependency_overrides[get_database] = _gen
    return TestClient(app)


def test_sort_volume_works_for_all_users():
    # TEMP: gate removed; volume sort allowed for all tiers.
    # Restore original assertions when Pro gate is re-enabled.
    client = _make_client()
    resp = client.get("/api/v1/web/cards?sort=volume", headers={"X-Dev-Tier": "free"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["tier"] == "free"
    assert data["requested_sort"] == "volume"
    assert data["effective_sort"] == "volume"


def test_sort_recent_works_for_all_users():
    # TEMP: gate removed; recent sort allowed for all tiers.
    # Restore original assertions when Pro gate is re-enabled.
    client = _make_client()
    resp = client.get("/api/v1/web/cards?sort=recent", headers={"X-Dev-Tier": "free"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["tier"] == "free"
    assert data["requested_sort"] == "recent"
    assert data["effective_sort"] == "recent"


def test_pro_user_sort_volume_returns_volume_order():
    client = _make_client()
    resp = client.get("/api/v1/web/cards?sort=volume", headers={"X-Dev-Tier": "pro"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["tier"] == "pro"
    assert data["requested_sort"] == "volume"
    assert data["effective_sort"] == "volume"


def test_pro_user_sort_recent_returns_recent_order():
    client = _make_client()
    resp = client.get("/api/v1/web/cards?sort=recent", headers={"X-Dev-Tier": "pro"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["tier"] == "pro"
    assert data["requested_sort"] == "recent"
    assert data["effective_sort"] == "recent"


def test_change_and_price_work_for_all_tiers():
    for tier_header in ("free", "pro"):
        for sort_val in ("change", "price"):
            client = _make_client()
            resp = client.get(
                f"/api/v1/web/cards?sort={sort_val}",
                headers={"X-Dev-Tier": tier_header},
            )
            assert resp.status_code == 200, f"tier={tier_header}, sort={sort_val}"
            data = resp.json()
            assert data["effective_sort"] == sort_val, f"tier={tier_header}, sort={sort_val}"
            assert data["tier"] == tier_header, f"tier={tier_header}, sort={sort_val}"
