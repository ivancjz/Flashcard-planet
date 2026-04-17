from __future__ import annotations

import uuid
from decimal import Decimal
from unittest import TestCase
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.deps import get_database
from backend.app.api.routes.cards import router as cards_router


def _fake_db():
    yield None


class CardsEnrichedEndpointTests(TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(cards_router, prefix="/api/v1")
        app.dependency_overrides[get_database] = _fake_db
        self.client = TestClient(app)
        self.app = app

    def tearDown(self):
        self.app.dependency_overrides.clear()

    def test_returns_enriched_data_for_known_card(self):
        from backend.app.core.response_types import CardDetailResponse, ProGateConfig

        asset_id = uuid.uuid4()
        fake_response = CardDetailResponse(
            card_name="Charizard Base Set",
            external_id="base1-4",
            current_price=Decimal("150.00"),
            price_history=[],
            sample_size=47,
            match_confidence_avg=Decimal("0.85"),
            data_age="Updated 3 hours ago",
            source_breakdown={"eBay": 70, "TCG": 30},
            access_tier="free",
            pro_gate_config=ProGateConfig(
                is_locked=True,
                feature_name="Extended Price History (180 days)",
                upgrade_reason="See long-term price patterns",
                urgency="medium",
            ),
        )

        with patch("backend.app.api.routes.cards._resolve_asset_id", return_value=asset_id), \
             patch("backend.app.api.routes.cards._get_access_tier", return_value="free"), \
             patch("backend.app.api.routes.cards.DataService.get_card_detail", return_value=fake_response):
            response = self.client.get("/api/v1/cards/base1-4/enriched?discord_user_id=123")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["card_name"], "Charizard Base Set")
        self.assertEqual(data["sample_size"], 47)
        self.assertTrue(data["pro_gate"]["is_locked"])
        self.assertEqual(data["pro_gate"]["urgency"], "medium")

    def test_returns_404_for_unknown_card(self):
        with patch("backend.app.api.routes.cards._resolve_asset_id", return_value=None):
            response = self.client.get("/api/v1/cards/unknown-card/enriched?discord_user_id=123")

        self.assertEqual(response.status_code, 404)

    def test_pro_user_gets_no_pro_gate(self):
        from backend.app.core.response_types import CardDetailResponse

        fake_response = CardDetailResponse(
            card_name="Test Card",
            external_id="test-1",
            current_price=Decimal("10.00"),
            price_history=[],
            sample_size=10,
            match_confidence_avg=None,
            data_age="Updated 1 hour ago",
            source_breakdown={},
            access_tier="pro",
            pro_gate_config=None,
        )

        with patch("backend.app.api.routes.cards._resolve_asset_id", return_value=uuid.uuid4()), \
             patch("backend.app.api.routes.cards._get_access_tier", return_value="pro"), \
             patch("backend.app.api.routes.cards.DataService.get_card_detail", return_value=fake_response):
            response = self.client.get("/api/v1/cards/test-1/enriched?discord_user_id=456")

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["pro_gate"])
