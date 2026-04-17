"""
tests/test_sources_history_routes.py

Route tests for Phase B2:
  - GET /cards/{external_id}/sources
  - GET /cards/{external_id}/history
"""
from __future__ import annotations

import unittest
import uuid
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

from backend.app.api.deps import get_database
from backend.app.site import router as site_router


def _fake_db():
    yield None


def _make_app() -> tuple[FastAPI, TestClient]:
    app = FastAPI()
    app.mount(
        "/static",
        StaticFiles(
            directory=Path(__file__).resolve().parents[1]
            / "backend"
            / "app"
            / "static"
        ),
        name="static",
    )
    app.include_router(site_router)
    app.dependency_overrides[get_database] = _fake_db
    return app, TestClient(app, raise_server_exceptions=False)


def _mock_asset(external_id: str = "xy1-001") -> MagicMock:
    asset = MagicMock()
    asset.id = uuid.uuid4()
    asset.name = "Charizard"
    asset.set_name = "Base Set"
    asset.card_number = "4"
    asset.external_id = external_id
    asset.category = "Pokemon"
    return asset


# ─────────────────────────────────────────────────────────────────────────────
# /cards/{external_id}/sources
# ─────────────────────────────────────────────────────────────────────────────

class TestCardSourcesRoute(unittest.TestCase):
    def setUp(self):
        self.app, self.client = _make_app()

    def tearDown(self):
        self.app.dependency_overrides.clear()

    def _mock_credibility(self, *, has_breakdown: bool = False):
        from backend.app.services.card_credibility_service import CredibilityIndicators
        return CredibilityIndicators(
            sample_size=47,
            data_age_hours=3.0,
            source_breakdown={"ebay_sold": 0.72, "pokemon_tcg_api": 0.28} if has_breakdown else None,
            match_confidence=0.92 if has_breakdown else None,
            data_age_label="Updated 3h ago",
            sample_size_label="Based on 47 sales",
            confidence_status="green" if has_breakdown else "unknown",
        )

    def test_returns_404_for_unknown_card(self):
        with patch("backend.app.site.SessionLocal") as mock_sl:
            mock_db = MagicMock()
            mock_sl.return_value.__enter__ = lambda s: mock_db
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)
            mock_db.scalars.return_value.first.return_value = None

            response = self.client.get("/cards/does-not-exist/sources")

        self.assertEqual(response.status_code, 404)

    def test_returns_200_for_known_card(self):
        asset = _mock_asset()
        credibility = self._mock_credibility()

        with (
            patch("backend.app.site.SessionLocal") as mock_sl,
            patch(
                "backend.app.site.build_credibility_indicators",
                return_value=credibility,
            ),
        ):
            mock_db = MagicMock()
            mock_sl.return_value.__enter__ = lambda s: mock_db
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)
            mock_db.scalars.return_value.first.return_value = asset

            response = self.client.get("/cards/xy1-001/sources")

        self.assertEqual(response.status_code, 200)

    def test_free_user_sees_sample_size(self):
        asset = _mock_asset()
        credibility = self._mock_credibility()

        with (
            patch("backend.app.site.SessionLocal") as mock_sl,
            patch(
                "backend.app.site.build_credibility_indicators",
                return_value=credibility,
            ),
        ):
            mock_db = MagicMock()
            mock_sl.return_value.__enter__ = lambda s: mock_db
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)
            mock_db.scalars.return_value.first.return_value = asset

            response = self.client.get("/cards/xy1-001/sources")

        self.assertIn("Based on 47 sales", response.text)

    def test_free_user_sees_progate_overlay(self):
        asset = _mock_asset()
        credibility = self._mock_credibility()

        with (
            patch("backend.app.site.SessionLocal") as mock_sl,
            patch(
                "backend.app.site.build_credibility_indicators",
                return_value=credibility,
            ),
        ):
            mock_db = MagicMock()
            mock_sl.return_value.__enter__ = lambda s: mock_db
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)
            mock_db.scalars.return_value.first.return_value = asset

            response = self.client.get("/cards/xy1-001/sources")

        self.assertIn("progate__overlay", response.text)

    def test_page_contains_card_name(self):
        asset = _mock_asset()
        credibility = self._mock_credibility()

        with (
            patch("backend.app.site.SessionLocal") as mock_sl,
            patch(
                "backend.app.site.build_credibility_indicators",
                return_value=credibility,
            ),
        ):
            mock_db = MagicMock()
            mock_sl.return_value.__enter__ = lambda s: mock_db
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)
            mock_db.scalars.return_value.first.return_value = asset

            response = self.client.get("/cards/xy1-001/sources")

        self.assertIn("Charizard", response.text)


# ─────────────────────────────────────────────────────────────────────────────
# /cards/{external_id}/history
# ─────────────────────────────────────────────────────────────────────────────

class TestCardHistoryRoute(unittest.TestCase):
    def setUp(self):
        self.app, self.client = _make_app()

    def tearDown(self):
        self.app.dependency_overrides.clear()

    def _mock_vm(self):
        from backend.app.services.card_detail_service import CardDetailViewModel
        from decimal import Decimal

        vm = MagicMock()
        vm.name = "Charizard"
        vm.latest_price = Decimal("42.00")
        vm.currency = "USD"
        vm.price_history = []
        vm.history_truncated = False
        vm.image_url = None
        return vm

    def test_returns_404_for_unknown_card(self):
        with patch("backend.app.site.SessionLocal") as mock_sl:
            mock_db = MagicMock()
            mock_sl.return_value.__enter__ = lambda s: mock_db
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)
            mock_db.scalars.return_value.first.return_value = None

            response = self.client.get("/cards/does-not-exist/history")

        self.assertEqual(response.status_code, 404)

    def test_returns_200_for_known_card(self):
        asset = _mock_asset()
        vm = self._mock_vm()

        with (
            patch("backend.app.site.SessionLocal") as mock_sl,
            patch("backend.app.site.build_card_detail", return_value=vm),
        ):
            mock_db = MagicMock()
            mock_sl.return_value.__enter__ = lambda s: mock_db
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)
            mock_db.scalars.return_value.first.return_value = asset

            response = self.client.get("/cards/xy1-001/history")

        self.assertEqual(response.status_code, 200)

    def test_page_contains_card_name(self):
        asset = _mock_asset()
        vm = self._mock_vm()

        with (
            patch("backend.app.site.SessionLocal") as mock_sl,
            patch("backend.app.site.build_card_detail", return_value=vm),
        ):
            mock_db = MagicMock()
            mock_sl.return_value.__enter__ = lambda s: mock_db
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)
            mock_db.scalars.return_value.first.return_value = asset

            response = self.client.get("/cards/xy1-001/history")

        self.assertIn("Charizard", response.text)

    def test_page_contains_price_history_heading(self):
        asset = _mock_asset()
        vm = self._mock_vm()

        with (
            patch("backend.app.site.SessionLocal") as mock_sl,
            patch("backend.app.site.build_card_detail", return_value=vm),
        ):
            mock_db = MagicMock()
            mock_sl.return_value.__enter__ = lambda s: mock_db
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)
            mock_db.scalars.return_value.first.return_value = asset

            response = self.client.get("/cards/xy1-001/history")

        self.assertTrue(
            "Price history" in response.text or "价格历史" in response.text
        )
