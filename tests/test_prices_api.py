from datetime import UTC, datetime
from decimal import Decimal
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.deps import get_database
from backend.app.api.routes.prices import router as prices_router
from backend.app.schemas.price import AssetHistoryResponse, AssetPriceResponse, PriceHistoryPointResponse


def _build_price_response(*, name: str = "Charizard", external_id: str = "ext-charizard") -> AssetPriceResponse:
    return AssetPriceResponse(
        asset_id=uuid4(),
        asset_class="TCG",
        category="Pokemon",
        name=name,
        set_name="Base Set",
        external_id=external_id,
        card_number="4",
        year=1999,
        variant="Holo",
        grade_company=None,
        grade_score=None,
        latest_price=Decimal("120.00"),
        currency="USD",
        source="pokemon_tcg_api",
        captured_at=datetime(2026, 4, 13, 10, 0, tzinfo=UTC),
        previous_price=Decimal("115.00"),
        absolute_change=Decimal("5.00"),
        percent_change=Decimal("4.35"),
        image_url=None,
    )


def _build_history_response(*, name: str = "Charizard") -> AssetHistoryResponse:
    return AssetHistoryResponse(
        asset_id=uuid4(),
        name=name,
        category="Pokemon",
        set_name="Base Set",
        current_price=Decimal("120.00"),
        currency="USD",
        points_returned=1,
        history=[
            PriceHistoryPointResponse(
                timestamp=datetime(2026, 4, 13, 10, 0, tzinfo=UTC),
                captured_at=datetime(2026, 4, 13, 10, 0, tzinfo=UTC),
                price=Decimal("120.00"),
                currency="USD",
                source="pokemon_tcg_api",
                point_type="derived",
                event_type="derived",
                is_real_data=True,
            )
        ],
        image_url=None,
    )


class PriceApiRoutesTests(TestCase):
    def setUp(self):
        self.db = object()
        app = FastAPI()
        app.include_router(prices_router, prefix="/api/v1")
        app.dependency_overrides[get_database] = lambda: self.db
        self.app = app
        self.client = TestClient(app)

    def tearDown(self):
        self.app.dependency_overrides.clear()

    def test_search_route_accepts_q_alias_for_dashboard_lookup(self):
        fake_results = [_build_price_response()]

        with patch("backend.app.api.routes.prices.get_asset_prices_by_name", return_value=fake_results) as mock_search:
            response = self.client.get("/api/v1/prices/search", params={"q": "Charizard"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["name"], "Charizard")
        mock_search.assert_called_once_with(self.db, "Charizard")

    def test_history_route_accepts_external_id_path_for_dashboard_lookup(self):
        fake_history = _build_history_response()

        with patch(
            "backend.app.api.routes.prices.get_asset_history_by_external_id",
            return_value=fake_history,
            create=True,
        ) as mock_history:
            response = self.client.get("/api/v1/prices/history/ext-charizard")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "Charizard")
        mock_history.assert_called_once_with(self.db, "ext-charizard", limit=5)
