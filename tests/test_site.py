from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

from backend.app.api.deps import get_database
from backend.app.site import router as site_router


def _fake_db():
    yield None


class SiteRoutesTests(TestCase):
    def setUp(self):
        app = FastAPI()
        app.mount(
            "/static",
            StaticFiles(directory=Path(__file__).resolve().parents[1] / "backend" / "app" / "static"),
            name="static",
        )
        app.include_router(site_router)
        app.dependency_overrides[get_database] = _fake_db
        self.app = app
        self.client = TestClient(app)

    def tearDown(self):
        self.app.dependency_overrides.clear()

    def test_landing_page_exposes_public_positioning(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Flashcard Planet", response.text)
        self.assertIn("data-and-signal product", response.text)
        self.assertIn("/dashboard", response.text)
        self.assertIn("/method", response.text)

    def test_dashboard_page_includes_live_modules(self):
        response = self.client.get("/dashboard")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Price lookup", response.text)
        self.assertIn("Loading live data...", response.text)
        self.assertIn("Current provider snapshot", response.text)
        self.assertIn("High-Activity v2 vs baseline", response.text)
        self.assertIn("data-dashboard-snapshot-url=\"/dashboard/snapshot\"", response.text)

    def test_static_site_js_uses_current_price_lookup_routes_only(self):
        response = self.client.get("/static/site.js")

        self.assertEqual(response.status_code, 200)
        self.assertIn("search?q=", response.text)
        self.assertIn("/history/${encodeURIComponent(items[0].external_id)}", response.text)
        self.assertNotIn("search?name=", response.text)
        self.assertNotIn("/history?name=", response.text)

    def test_method_page_keeps_scope_aligned_with_current_stage(self):
        response = self.client.get("/method")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Build the data layer first", response.text)
        self.assertIn("No marketplace", response.text)
        self.assertIn("watchlists and alerts", response.text.lower())

    def test_dashboard_snapshot_route_returns_public_demo_payload(self):
        fake_snapshot = {
            "generated_at": "2026-04-03T10:00:00Z",
            "product_stage": {
                "headline": "Data layer + signal layer MVP",
                "summary": "Signals first.",
                "focus_areas": ["price history ingestion"],
            },
            "provider_snapshot": {
                "active_source": "pokemon_tcg_api",
                "provider_label": "Pokemon TCG API",
                "configured_provider_count": 1,
                "tracked_assets": 129,
                "real_history_assets": 129,
                "recent_real_rows_24h": 6042,
                "assets_changed_24h": 110,
                "row_change_pct_24h": "2.02%",
                "row_change_pct_7d": "1.86%",
            },
            "signal_snapshot": {
                "watchlists": 4,
                "active_alerts": 7,
                "diagnostics_label": "pool comparison + provider health",
                "current_note": "Still testing pool design.",
            },
            "top_value": [],
            "top_movers": [],
            "pools": [],
            "high_activity_v2_vs_baseline": {
                "headline": "High-Activity v2",
                "summary": "Tighter than the premium slice.",
                "bullets": ["Coverage healthy."],
            },
            "lookup_examples": ["Umbreon"],
        }

        with patch("backend.app.site.build_dashboard_snapshot", return_value=fake_snapshot):
            response = self.client.get("/dashboard/snapshot")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["provider_snapshot"]["provider_label"], "Pokemon TCG API")
        self.assertEqual(response.json()["signal_snapshot"]["active_alerts"], 7)
        self.assertEqual(response.json()["lookup_examples"], ["Umbreon"])
