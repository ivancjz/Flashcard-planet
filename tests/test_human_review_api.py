from __future__ import annotations

import uuid
from pathlib import Path
from unittest import TestCase

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

from backend.app.api.deps import get_database
from backend.app.models.human_review import HumanReviewQueue
from backend.app.site import router as site_router


def _fake_db():
    yield None


class HumanReviewModelTests(TestCase):
    def test_human_review_queue_has_resolution_type(self):
        row = HumanReviewQueue(
            raw_listing_id=uuid.uuid4(),
            raw_title="Charizard VMAX PSA 10",
        )

        self.assertTrue(hasattr(row, "resolution_type"))
        self.assertIsNone(row.resolution_type)


class ReviewRoutesTests(TestCase):
    def test_review_routes_importable(self):
        from backend.app.backstage.review_routes import router

        self.assertIsNotNone(router)

    def test_review_router_exposes_all_five_endpoints(self):
        from backend.app.backstage.review_routes import router

        route_map = {
            route.path: set(route.methods or set()) - {"HEAD", "OPTIONS"}
            for route in router.routes
        }

        self.assertIn("/admin/review", route_map)
        self.assertEqual(route_map["/admin/review"], {"GET"})
        self.assertIn("/admin/review/assets/search", route_map)
        self.assertEqual(route_map["/admin/review/assets/search"], {"GET"})
        self.assertIn("/admin/review/{review_id}/accept", route_map)
        self.assertEqual(route_map["/admin/review/{review_id}/accept"], {"POST"})
        self.assertIn("/admin/review/{review_id}/override", route_map)
        self.assertEqual(route_map["/admin/review/{review_id}/override"], {"POST"})
        self.assertIn("/admin/review/{review_id}/dismiss", route_map)
        self.assertEqual(route_map["/admin/review/{review_id}/dismiss"], {"POST"})

    def test_api_router_registers_review_routes_under_api_prefix(self):
        from backend.app.api.router import api_router

        paths = [route.path for route in api_router.routes]

        self.assertIn("/api/v1/admin/review", paths)
        self.assertIn("/api/v1/admin/review/assets/search", paths)
        self.assertIn("/api/v1/admin/review/{review_id}/accept", paths)
        self.assertIn("/api/v1/admin/review/{review_id}/override", paths)
        self.assertIn("/api/v1/admin/review/{review_id}/dismiss", paths)


class BackstageReviewPageTests(TestCase):
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

    def test_backstage_review_route_exists(self):
        paths = [route.path for route in site_router.routes]

        self.assertIn("/backstage/review", paths)

    def test_backstage_review_page_renders_shell(self):
        response = self.client.get("/backstage/review")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Human Review Queue", response.text)
        self.assertIn("Enter admin key", response.text)
        self.assertIn("/api/v1/admin/review", response.text)
        self.assertIn("assets/search", response.text)
        self.assertIn("resolveDismiss", response.text)
