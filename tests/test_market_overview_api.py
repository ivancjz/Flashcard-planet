from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.deps import get_database
from backend.app.api.router import api_router
from backend.app.api.routes.market import router as market_router
from backend.app.schemas.market import (
    MarketIndexResponse,
    MarketOverviewResponse,
    MarketTopMoverResponse,
)


def _fake_overview() -> MarketOverviewResponse:
    return MarketOverviewResponse(
        generated_at=datetime(2026, 7, 21, 10, 0, 0),
        market_sentiment="bullish",
        confidence_label="medium",
        indexes=[
            MarketIndexResponse(
                game="pokemon",
                label="Pokemon Market",
                change_pct=Decimal("12.34"),
                direction="up",
                observed_assets=4,
                current_assets=6,
                confidence_label="medium",
            )
        ],
        top_movers=[
            MarketTopMoverResponse(
                asset_id="11111111-1111-1111-1111-111111111111",
                name="Charizard",
                game="pokemon",
                set_name="Base Set",
                latest_price=Decimal("120.00"),
                previous_price=Decimal("100.00"),
                percent_change=Decimal("20.00"),
                absolute_change=Decimal("20.00"),
                direction="up",
            )
        ],
        signal_summary=[],
        commentary="Market is bullish based on 4 raw price series.",
        evidence=["market_segment=raw", "active price source: sample_seed"],
    )


def test_market_overview_route_returns_dashboard_payload():
    db = object()
    app = FastAPI()
    app.include_router(market_router, prefix="/api/v1")
    app.dependency_overrides[get_database] = lambda: db
    client = TestClient(app)

    with patch("backend.app.api.routes.market.get_market_overview", return_value=_fake_overview()) as mock_service:
        response = client.get("/api/v1/market/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["market_sentiment"] == "bullish"
    assert payload["indexes"][0]["label"] == "Pokemon Market"
    assert payload["top_movers"][0]["direction"] == "up"
    mock_service.assert_called_once_with(db)


def test_api_router_registers_market_overview_under_api_prefix():
    paths = [route.path for route in api_router.routes]

    assert "/api/v1/market/overview" in paths
