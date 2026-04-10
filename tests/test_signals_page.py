"""Tests for /signals page rendering."""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

from backend.app.models.user import User
from backend.app.site import router as site_router


def test_user_has_access_tier_field():
    """User model must have access_tier with default 'free'."""
    u = User(discord_user_id="123456789")
    assert u.access_tier == "free"


def test_user_access_tier_can_be_pro():
    u = User(discord_user_id="999999999", access_tier="pro")
    assert u.access_tier == "pro"


def test_signals_route_exists():
    from backend.app.site import router

    paths = [r.path for r in router.routes]
    assert "/signals" in paths


class _DummySessionContext:
    def __enter__(self):
        return object()

    def __exit__(self, exc_type, exc, tb):
        return False


def _build_client() -> TestClient:
    app = FastAPI()
    app.mount(
        "/static",
        StaticFiles(directory=Path(__file__).resolve().parents[1] / "backend" / "app" / "static"),
        name="static",
    )
    app.include_router(site_router)
    return TestClient(app)


def test_signals_page_renders_localized_intro_and_filters():
    client = _build_client()

    with (
        patch("backend.app.site.SessionLocal", return_value=_DummySessionContext()),
        patch("backend.app.site.get_daily_snapshot_signals", return_value=[]),
    ):
        response = client.get("/signals")

    assert response.status_code == 200
    assert "市场信号" in response.text
    assert "Daily snapshots and live signal layer" in response.text
    assert "/signals?label=BREAKOUT" in response.text
    assert "No daily snapshot available yet" in response.text


def load_tests(loader: unittest.TestLoader, tests: unittest.TestSuite, pattern: str | None) -> unittest.TestSuite:
    suite = unittest.TestSuite()
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            suite.addTest(unittest.FunctionTestCase(value))
    return suite
