from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from backend.app.api.deps import get_database
from backend.app.api.router import api_router
from backend.app.api.routes.market import router as market_router
from backend.app.schemas.catalyst import CatalystListResponse, CatalystResponse


CATALYST_ID = UUID("33333333-3333-3333-3333-333333333333")


@pytest.fixture
def catalyst_response() -> CatalystResponse:
    return CatalystResponse(
        id=CATALYST_ID,
        event_date=datetime(2026, 7, 22, 12, 0, tzinfo=UTC),
        active_until=datetime(2026, 8, 5, 12, 0, tzinfo=UTC),
        event_type="REPRINT",
        description="A verified reprint was announced.",
        source_url="https://example.com/reprint",
        affected_games=["pokemon"],
        affected_asset_ids=["asset-1"],
        affected_set_ids=["set-1"],
        expected_window_days=14,
        impact_score=85,
        impact_label="high",
        confidence_score=Decimal("82.50"),
        confidence_label="high",
        status="active",
        verified_at=datetime(2026, 7, 22, 11, 0, tzinfo=UTC),
    )


@pytest.fixture
def catalyst_list_response(
    catalyst_response: CatalystResponse,
) -> CatalystListResponse:
    return CatalystListResponse(
        catalysts=[catalyst_response],
        total=1,
        limit=20,
        offset=0,
        as_of=datetime(2026, 7, 22, 12, 30, tzinfo=UTC),
    )


def _client(db=object()) -> tuple[FastAPI, TestClient, object]:
    app = FastAPI()
    app.include_router(market_router, prefix="/api/v1")
    app.dependency_overrides[get_database] = lambda: db
    return app, TestClient(app), db


def test_list_catalysts_serializes_typed_response_and_uses_defaults(
    mocker,
    catalyst_list_response: CatalystListResponse,
):
    app, client, db = _client()
    service = mocker.patch(
        "backend.app.api.routes.market.list_catalysts",
        return_value=catalyst_list_response,
    )

    response = client.get("/api/v1/market/catalysts")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["limit"] == 20
    assert payload["offset"] == 0
    assert payload["as_of"] == "2026-07-22T12:30:00Z"
    assert payload["catalysts"][0]["id"] == str(CATALYST_ID)
    assert payload["catalysts"][0]["active_until"] == "2026-08-05T12:00:00Z"
    assert payload["catalysts"][0]["impact_label"] == "high"
    assert payload["catalysts"][0]["confidence_label"] == "high"
    assert "verified_by" not in payload["catalysts"][0]
    service.assert_called_once_with(
        db,
        statuses=None,
        game=None,
        event_type=None,
        limit=20,
        offset=0,
    )
    app.dependency_overrides.clear()


def test_list_catalysts_passes_repeated_statuses_and_normalized_event_type(
    mocker,
    catalyst_list_response: CatalystListResponse,
):
    app, client, db = _client()
    service = mocker.patch(
        "backend.app.api.routes.market.list_catalysts",
        return_value=catalyst_list_response,
    )

    response = client.get(
        "/api/v1/market/catalysts"
        "?status=active&status=upcoming&game=pokemon"
        "&event_type=reprint&limit=3&offset=0"
    )

    assert response.status_code == 200
    service.assert_called_once_with(
        db,
        statuses=["active", "upcoming"],
        game="pokemon",
        event_type="REPRINT",
        limit=3,
        offset=0,
    )
    app.dependency_overrides.clear()


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "offset=-1"])
def test_list_catalysts_rejects_invalid_pagination_before_calling_service(
    mocker,
    query: str,
):
    app, client, _db = _client()
    service = mocker.patch(
        "backend.app.api.routes.market.list_catalysts",
    )

    response = client.get(f"/api/v1/market/catalysts?{query}")

    assert response.status_code == 422
    service.assert_not_called()
    app.dependency_overrides.clear()


def test_list_catalysts_rejects_invalid_status_before_calling_service(mocker):
    app, client, _db = _client()
    service = mocker.patch(
        "backend.app.api.routes.market.list_catalysts",
    )

    response = client.get("/api/v1/market/catalysts?status=unknown")

    assert response.status_code == 422
    service.assert_not_called()
    app.dependency_overrides.clear()


def test_get_catalyst_passes_uuid_and_serializes_typed_response(
    mocker,
    catalyst_response: CatalystResponse,
):
    app, client, db = _client()
    service = mocker.patch(
        "backend.app.api.routes.market.get_catalyst",
        return_value=catalyst_response,
    )

    response = client.get(f"/api/v1/market/catalysts/{CATALYST_ID}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(CATALYST_ID)
    assert payload["active_until"] == "2026-08-05T12:00:00Z"
    assert payload["impact_label"] == "high"
    assert payload["confidence_label"] == "high"
    assert "verified_by" not in payload
    service.assert_called_once_with(db, CATALYST_ID)
    app.dependency_overrides.clear()


def test_get_catalyst_returns_exact_404_when_missing(mocker):
    app, client, db = _client()
    service = mocker.patch(
        "backend.app.api.routes.market.get_catalyst",
        return_value=None,
    )

    response = client.get(f"/api/v1/market/catalysts/{CATALYST_ID}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Catalyst not found."
    service.assert_called_once_with(db, CATALYST_ID)
    app.dependency_overrides.clear()


def test_get_catalyst_rejects_malformed_uuid_before_calling_service(mocker):
    app, client, _db = _client()
    service = mocker.patch(
        "backend.app.api.routes.market.get_catalyst",
    )

    response = client.get("/api/v1/market/catalysts/not-a-uuid")

    assert response.status_code == 422
    service.assert_not_called()
    app.dependency_overrides.clear()


def test_api_router_registers_ordered_read_only_catalyst_routes():
    catalyst_routes = {
        route.path: route
        for route in api_router.routes
        if isinstance(route, APIRoute)
        and route.path.startswith("/api/v1/market/catalysts")
    }

    assert set(catalyst_routes) == {
        "/api/v1/market/catalysts",
        "/api/v1/market/catalysts/{catalyst_id}",
    }
    assert catalyst_routes["/api/v1/market/catalysts"].methods == {"GET"}
    assert catalyst_routes["/api/v1/market/catalysts/{catalyst_id}"].methods == {
        "GET"
    }
    paths = [route.path for route in api_router.routes]
    assert paths.index("/api/v1/market/catalysts") < paths.index(
        "/api/v1/market/catalysts/{catalyst_id}"
    )


def test_list_catalysts_does_not_expose_as_of_query_parameter():
    app, _client_instance, _db = _client()
    schema = app.openapi()
    path = "/api/v1/market/catalysts"

    assert path in schema["paths"]
    parameter_names = {
        parameter["name"]
        for parameter in schema["paths"][path]["get"]["parameters"]
    }
    assert parameter_names == {"status", "game", "event_type", "limit", "offset"}
    app.dependency_overrides.clear()
