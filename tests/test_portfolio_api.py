from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.deps import get_current_user, get_database, get_optional_user
from backend.app.api.router import api_router
from backend.app.api.routes.portfolio import router as portfolio_router
from backend.app.schemas.portfolio import PortfolioResponse, PortfolioSummaryResponse
from backend.app.services import portfolio_service
from backend.app.services.portfolio_service import (
    PortfolioAssetNotFoundError,
    PortfolioLotNotFoundError,
    PortfolioPositionLimitError,
)


VALID_PAYLOAD = {
    "asset_id": str(uuid4()),
    "quantity": 2,
    "unit_cost_usd": "125.00",
    "purchased_on": "2026-07-01",
}


def _empty_portfolio() -> PortfolioResponse:
    return PortfolioResponse(
        summary=PortfolioSummaryResponse(
            total_cost_basis=Decimal("0.00"),
            priced_cost_basis=Decimal("0.00"),
            total_market_value=Decimal("0.00"),
            unrealized_pnl=Decimal("0.00"),
            unrealized_pnl_percent=None,
            position_count=0,
            priced_position_count=0,
            unpriced_position_count=0,
            valuation_coverage_percent=Decimal("0.00"),
            position_limit=10,
        ),
        allocations=[],
        positions=[],
    )


def _lot():
    now = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
    return SimpleNamespace(
        id=uuid4(),
        asset_id=uuid4(),
        quantity=2,
        unit_cost_usd=Decimal("125.00"),
        purchased_on=date(2026, 7, 1),
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def db():
    return MagicMock()


@pytest.fixture
def user():
    return SimpleNamespace(id=uuid4(), email="portfolio@example.com")


@pytest.fixture
def service(monkeypatch):
    mocked = SimpleNamespace(
        get_portfolio=MagicMock(return_value=_empty_portfolio()),
        create_portfolio_lot=MagicMock(return_value=_lot()),
        update_portfolio_lot=MagicMock(return_value=_lot()),
        delete_portfolio_lot=MagicMock(return_value=None),
    )
    monkeypatch.setattr(portfolio_service, "get_portfolio", mocked.get_portfolio)
    monkeypatch.setattr(
        portfolio_service,
        "create_portfolio_lot",
        mocked.create_portfolio_lot,
    )
    monkeypatch.setattr(
        portfolio_service,
        "update_portfolio_lot",
        mocked.update_portfolio_lot,
    )
    monkeypatch.setattr(
        portfolio_service,
        "delete_portfolio_lot",
        mocked.delete_portfolio_lot,
    )
    return mocked


@pytest.fixture
def client(db, user, service):
    app = FastAPI()
    app.include_router(portfolio_router, prefix="/api/v1")
    app.dependency_overrides[get_database] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def test_get_portfolio_uses_current_user_without_transaction_control(
    client,
    db,
    user,
    service,
):
    response = client.get("/api/v1/portfolio")

    assert response.status_code == 200
    service.get_portfolio.assert_called_once_with(db, user)
    db.commit.assert_not_called()
    db.rollback.assert_not_called()


@pytest.mark.parametrize(
    ("method", "path", "json"),
    [
        ("GET", "/api/v1/portfolio", None),
        ("POST", "/api/v1/portfolio/lots", VALID_PAYLOAD),
        ("PATCH", f"/api/v1/portfolio/lots/{uuid4()}", {"quantity": 3}),
        ("DELETE", f"/api/v1/portfolio/lots/{uuid4()}", None),
    ],
)
def test_all_routes_require_authentication(method, path, json, db, service):
    app = FastAPI()
    app.include_router(portfolio_router, prefix="/api/v1")
    app.dependency_overrides[get_database] = lambda: db
    app.dependency_overrides[get_optional_user] = lambda: None
    unauthenticated_client = TestClient(app)

    response = unauthenticated_client.request(method, path, json=json)

    assert response.status_code == 401


def test_post_lot_returns_201_and_commits(client, db, user, service):
    response = client.post("/api/v1/portfolio/lots", json=VALID_PAYLOAD)

    assert response.status_code == 201
    payload = service.create_portfolio_lot.call_args.args[2]
    assert service.create_portfolio_lot.call_args.args[:2] == (db, user)
    assert str(payload.asset_id) == VALID_PAYLOAD["asset_id"]
    assert payload.unit_cost_usd == Decimal("125.00")
    db.commit.assert_called_once_with()
    db.rollback.assert_not_called()


def test_patch_lot_returns_200_and_commits(client, db, user, service):
    lot_id = uuid4()

    response = client.patch(
        f"/api/v1/portfolio/lots/{lot_id}",
        json={"quantity": 3},
    )

    assert response.status_code == 200
    call = service.update_portfolio_lot.call_args
    assert call.args[:3] == (db, user, lot_id)
    assert call.args[3].quantity == 3
    db.commit.assert_called_once_with()
    db.rollback.assert_not_called()


def test_delete_lot_returns_empty_204_and_commits(client, db, user, service):
    lot_id = uuid4()

    response = client.delete(f"/api/v1/portfolio/lots/{lot_id}")

    assert response.status_code == 204
    assert response.content == b""
    service.delete_portfolio_lot.assert_called_once_with(db, user, lot_id)
    db.commit.assert_called_once_with()
    db.rollback.assert_not_called()


def test_free_limit_maps_to_structured_403(client, db, service):
    service.create_portfolio_lot.side_effect = PortfolioPositionLimitError(
        position_limit=10,
        position_count=10,
    )

    response = client.post("/api/v1/portfolio/lots", json=VALID_PAYLOAD)

    assert response.status_code == 403
    assert response.json()["detail"] == {
        "code": "portfolio_position_limit_reached",
        "message": "Free accounts can hold up to 10 portfolio positions.",
        "position_limit": 10,
        "position_count": 10,
        "upgrade_url": "/pricing",
    }
    db.rollback.assert_called_once_with()
    db.commit.assert_not_called()


def test_missing_asset_maps_to_404_and_rolls_back(client, db, service):
    service.create_portfolio_lot.side_effect = PortfolioAssetNotFoundError()

    response = client.post("/api/v1/portfolio/lots", json=VALID_PAYLOAD)

    assert response.status_code == 404
    assert response.json()["detail"] == "Portfolio resource not found."
    db.rollback.assert_called_once_with()
    db.commit.assert_not_called()


@pytest.mark.parametrize("method", ["PATCH", "DELETE"])
def test_missing_or_foreign_lot_maps_to_404_and_rolls_back(
    method,
    client,
    db,
    service,
):
    lot_id = uuid4()
    target = (
        service.update_portfolio_lot
        if method == "PATCH"
        else service.delete_portfolio_lot
    )
    target.side_effect = PortfolioLotNotFoundError()

    response = client.request(
        method,
        f"/api/v1/portfolio/lots/{lot_id}",
        json={"quantity": 3} if method == "PATCH" else None,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Portfolio resource not found."
    db.rollback.assert_called_once_with()
    db.commit.assert_not_called()


@pytest.mark.parametrize(
    ("method", "path", "json"),
    [
        ("POST", "/api/v1/portfolio/lots", VALID_PAYLOAD),
        ("PATCH", f"/api/v1/portfolio/lots/{uuid4()}", {"quantity": 3}),
        ("DELETE", f"/api/v1/portfolio/lots/{uuid4()}", None),
    ],
)
def test_unexpected_mutation_error_rolls_back_and_propagates(
    method,
    path,
    json,
    client,
    db,
    service,
):
    target = {
        "POST": service.create_portfolio_lot,
        "PATCH": service.update_portfolio_lot,
        "DELETE": service.delete_portfolio_lot,
    }[method]
    target.side_effect = RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        client.request(method, path, json=json)

    db.rollback.assert_called_once_with()
    db.commit.assert_not_called()


@pytest.mark.parametrize(
    ("path", "json"),
    [
        ("/api/v1/portfolio/lots/not-a-uuid", {"quantity": 3}),
        (f"/api/v1/portfolio/lots/{uuid4()}", {}),
        (f"/api/v1/portfolio/lots/{uuid4()}", {"quantity": 0}),
        (f"/api/v1/portfolio/lots/{uuid4()}", {"purchased_on": "not-a-date"}),
    ],
)
def test_patch_validation_errors_return_422(client, service, path, json):
    response = client.patch(path, json=json)

    assert response.status_code == 422
    service.update_portfolio_lot.assert_not_called()


@pytest.mark.parametrize(
    "payload",
    [
        {**VALID_PAYLOAD, "user_id": str(uuid4())},
        {**VALID_PAYLOAD, "quantity": 0},
        {**VALID_PAYLOAD, "unit_cost_usd": "-0.01"},
        {**VALID_PAYLOAD, "purchased_on": "not-a-date"},
    ],
)
def test_post_validation_and_user_injection_return_422(client, service, payload):
    response = client.post("/api/v1/portfolio/lots", json=payload)

    assert response.status_code == 422
    service.create_portfolio_lot.assert_not_called()


def test_application_router_registers_all_portfolio_routes():
    portfolio_routes: dict[str, set[str]] = {}
    for route in api_router.routes:
        if route.path.startswith("/api/v1/portfolio"):
            portfolio_routes.setdefault(route.path, set()).update(
                route.methods or set()
            )

    assert portfolio_routes == {
        "/api/v1/portfolio": {"GET"},
        "/api/v1/portfolio/lots": {"POST"},
        "/api/v1/portfolio/lots/{lot_id}": {"DELETE", "PATCH"},
    }
