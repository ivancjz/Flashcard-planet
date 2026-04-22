from __future__ import annotations

from pathlib import Path
from unittest import TestCase

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.site import SPAStaticFiles, _is_browser_route

_DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"


class IsBrowserRouteTests(TestCase):
    """Unit-test the path classifier without touching HTTP at all."""

    def test_bare_slug_is_browser_route(self):
        self.assertTrue(_is_browser_route("market"))

    def test_nested_slug_is_browser_route(self):
        self.assertTrue(_is_browser_route("market/some-uuid-1234"))

    def test_empty_path_is_browser_route(self):
        self.assertTrue(_is_browser_route(""))

    def test_alerts_is_browser_route(self):
        self.assertTrue(_is_browser_route("alerts"))

    # --- paths that must NOT fall back ---

    def test_api_prefix_excluded(self):
        self.assertFalse(_is_browser_route("api/v1/web/stats"))

    def test_api_typo_excluded(self):
        self.assertFalse(_is_browser_route("api/v1/typo"))

    def test_static_prefix_excluded(self):
        self.assertFalse(_is_browser_route("static/style.css"))

    def test_assets_prefix_excluded(self):
        self.assertFalse(_is_browser_route("assets/index-BVHFwmLy.js"))

    def test_js_extension_excluded(self):
        self.assertFalse(_is_browser_route("chunk-missing.js"))

    def test_css_extension_excluded(self):
        self.assertFalse(_is_browser_route("style-missing.css"))

    def test_svg_extension_excluded(self):
        self.assertFalse(_is_browser_route("missing.svg"))

    def test_png_extension_excluded(self):
        self.assertFalse(_is_browser_route("logo.png"))


class SPAStaticFilesHTTPTests(TestCase):
    """Integration-level checks via TestClient — requires a real dist/ build."""

    @classmethod
    def setUpClass(cls):
        if not _DIST.exists():
            raise unittest.SkipTest("frontend/dist not built — run npm run build first")

    def _make_client(self):
        app = FastAPI()
        app.mount("/", SPAStaticFiles(directory=str(_DIST), html=True), name="spa")
        return TestClient(app, raise_server_exceptions=False)

    def test_spa_route_returns_index_html(self):
        client = self._make_client()
        r = client.get("/market/some-uuid-1234")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/html", r.headers["content-type"])
        self.assertIn("<!doctype html>", r.text.lower())

    def test_root_returns_index_html(self):
        client = self._make_client()
        r = client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/html", r.headers["content-type"])

    def test_existing_asset_served_directly(self):
        js_files = list((_DIST / "assets").glob("*.js"))
        if not js_files:
            self.skipTest("no JS bundle in dist/assets")
        client = self._make_client()
        r = client.get(f"/assets/{js_files[0].name}")
        self.assertEqual(r.status_code, 200)
        self.assertIn("javascript", r.headers["content-type"])

    def test_favicon_served_directly(self):
        client = self._make_client()
        r = client.get("/favicon.svg")
        self.assertEqual(r.status_code, 200)
        self.assertIn("image/svg", r.headers["content-type"])

    # --- the cases the reviewer flagged ---

    def test_missing_js_chunk_returns_404_not_html(self):
        """A missing JS chunk must be a real 404, not index.html (parse error)."""
        client = self._make_client()
        r = client.get("/assets/nonexistent-chunk-abc123.js")
        self.assertEqual(r.status_code, 404)

    def test_typo_api_path_returns_404_not_html(self):
        """A typo'd API path must stay 404 JSON, not silently return index.html."""
        client = self._make_client()
        r = client.get("/api/v1/nonexistent-endpoint")
        self.assertEqual(r.status_code, 404)

    def test_missing_css_returns_404_not_html(self):
        client = self._make_client()
        r = client.get("/assets/nonexistent.css")
        self.assertEqual(r.status_code, 404)


import unittest  # noqa: E402 — needed for SkipTest reference above
