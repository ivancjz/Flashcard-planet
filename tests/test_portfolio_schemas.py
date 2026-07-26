import json
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

from backend.app.schemas.portfolio import (
    PortfolioLotCreateRequest,
    PortfolioLotPatchRequest,
    PortfolioPositionResponse,
    PortfolioResponse,
)


ASSET_ID = UUID("11111111-1111-1111-1111-111111111111")
LOT_ID = UUID("22222222-2222-2222-2222-222222222222")


def test_valid_create_normalizes_uuid_date_and_decimal():
    request = PortfolioLotCreateRequest(
        asset_id=str(ASSET_ID),
        quantity=2,
        unit_cost_usd="12.34",
        purchased_on="2026-07-20",
    )

    assert request.asset_id == ASSET_ID
    assert request.quantity == 2
    assert request.unit_cost_usd == Decimal("12.34")
    assert request.purchased_on == date(2026, 7, 20)


@pytest.mark.parametrize("quantity", [0, -1])
def test_create_rejects_non_positive_quantity(quantity):
    with pytest.raises(ValidationError):
        PortfolioLotCreateRequest(
            asset_id=ASSET_ID,
            quantity=quantity,
            unit_cost_usd="12.34",
            purchased_on="2026-07-20",
        )


@pytest.mark.parametrize(
    "unit_cost_usd",
    ["-0.01", "12.345", "10000000000.00"],
)
def test_create_rejects_invalid_cost(unit_cost_usd):
    with pytest.raises(ValidationError):
        PortfolioLotCreateRequest(
            asset_id=ASSET_ID,
            quantity=1,
            unit_cost_usd=unit_cost_usd,
            purchased_on="2026-07-20",
        )


def test_create_accepts_zero_cost():
    request = PortfolioLotCreateRequest(
        asset_id=ASSET_ID,
        quantity=1,
        unit_cost_usd="0",
        purchased_on="2026-07-20",
    )

    assert request.unit_cost_usd == Decimal("0")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("asset_id", "not-a-uuid"),
        ("purchased_on", "not-a-date"),
    ],
)
def test_create_rejects_invalid_uuid_and_date(field, value):
    payload = {
        "asset_id": ASSET_ID,
        "quantity": 1,
        "unit_cost_usd": "12.34",
        "purchased_on": "2026-07-20",
    }
    payload[field] = value

    with pytest.raises(ValidationError):
        PortfolioLotCreateRequest(**payload)


def test_create_rejects_user_id():
    with pytest.raises(ValidationError):
        PortfolioLotCreateRequest(
            asset_id=ASSET_ID,
            quantity=1,
            unit_cost_usd="12.34",
            purchased_on="2026-07-20",
            user_id=UUID("33333333-3333-3333-3333-333333333333"),
        )


def test_empty_patch_is_rejected():
    with pytest.raises(ValidationError):
        PortfolioLotPatchRequest()


@pytest.mark.parametrize(
    ("payload", "field", "expected"),
    [
        ({"quantity": 3}, "quantity", 3),
        ({"unit_cost_usd": "45.67"}, "unit_cost_usd", Decimal("45.67")),
        ({"purchased_on": "2026-07-21"}, "purchased_on", date(2026, 7, 21)),
    ],
)
def test_patch_accepts_each_mutable_field_alone(payload, field, expected):
    request = PortfolioLotPatchRequest(**payload)

    assert getattr(request, field) == expected


@pytest.mark.parametrize("field", ["quantity", "unit_cost_usd", "purchased_on"])
def test_patch_rejects_explicit_null(field):
    with pytest.raises(ValidationError):
        PortfolioLotPatchRequest(**{field: None})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("asset_id", ASSET_ID),
        ("user_id", UUID("33333333-3333-3333-3333-333333333333")),
        ("unknown", "value"),
    ],
)
def test_patch_rejects_immutable_and_unknown_fields(field, value):
    with pytest.raises(ValidationError):
        PortfolioLotPatchRequest(**{field: value})


def test_position_rejects_invalid_valuation_status():
    with pytest.raises(ValidationError):
        PortfolioPositionResponse(
            asset_id=ASSET_ID,
            name="Charizard",
            set_name=None,
            card_number=None,
            game="pokemon",
            quantity=1,
            average_unit_cost_usd=Decimal("100.00"),
            cost_basis_usd=Decimal("100.00"),
            latest_raw_price_usd=None,
            latest_price_at=None,
            market_value_usd=None,
            unrealized_pnl_usd=None,
            unrealized_pnl_percent=None,
            valuation_status="stale",
            lots=[],
        )


def test_portfolio_response_serializes_decimals_as_strings_and_preserves_nulls():
    response = PortfolioResponse(
        summary={
            "total_cost_basis": Decimal("150.50"),
            "priced_cost_basis": Decimal("100.00"),
            "total_market_value": Decimal("125.25"),
            "unrealized_pnl": Decimal("25.25"),
            "unrealized_pnl_percent": Decimal("25.25"),
            "position_count": 2,
            "priced_position_count": 1,
            "unpriced_position_count": 1,
            "valuation_coverage_percent": Decimal("66.45"),
            "position_limit": None,
        },
        allocations=[
            {
                "game": "pokemon",
                "market_value_usd": Decimal("125.25"),
                "percentage": Decimal("100.00"),
                "priced_position_count": 1,
            }
        ],
        positions=[
            {
                "asset_id": ASSET_ID,
                "name": "Charizard",
                "set_name": "Base Set",
                "card_number": "4/102",
                "game": "pokemon",
                "quantity": 1,
                "average_unit_cost_usd": Decimal("100.00"),
                "cost_basis_usd": Decimal("100.00"),
                "latest_raw_price_usd": Decimal("125.25"),
                "latest_price_at": datetime(2026, 7, 26, 1, 2, 3),
                "market_value_usd": Decimal("125.25"),
                "unrealized_pnl_usd": Decimal("25.25"),
                "unrealized_pnl_percent": Decimal("25.25"),
                "valuation_status": "priced",
                "lots": [
                    {
                        "id": LOT_ID,
                        "asset_id": ASSET_ID,
                        "quantity": 1,
                        "unit_cost_usd": Decimal("100.00"),
                        "purchased_on": date(2026, 7, 20),
                        "created_at": datetime(2026, 7, 20, 1, 2, 3),
                        "updated_at": datetime(2026, 7, 21, 1, 2, 3),
                    }
                ],
            },
            {
                "asset_id": UUID("44444444-4444-4444-4444-444444444444"),
                "name": "Unpriced Card",
                "set_name": None,
                "card_number": None,
                "game": "yugioh",
                "quantity": 2,
                "average_unit_cost_usd": Decimal("25.25"),
                "cost_basis_usd": Decimal("50.50"),
                "latest_raw_price_usd": None,
                "latest_price_at": None,
                "market_value_usd": None,
                "unrealized_pnl_usd": None,
                "unrealized_pnl_percent": None,
                "valuation_status": "unpriced",
                "lots": [],
            },
        ],
    )

    payload = json.loads(response.model_dump_json())

    assert payload["summary"] == {
        "total_cost_basis": "150.50",
        "priced_cost_basis": "100.00",
        "total_market_value": "125.25",
        "unrealized_pnl": "25.25",
        "unrealized_pnl_percent": "25.25",
        "position_count": 2,
        "priced_position_count": 1,
        "unpriced_position_count": 1,
        "valuation_coverage_percent": "66.45",
        "position_limit": None,
    }
    assert payload["allocations"][0]["market_value_usd"] == "125.25"
    assert payload["allocations"][0]["percentage"] == "100.00"
    assert payload["positions"][0]["average_unit_cost_usd"] == "100.00"
    assert payload["positions"][0]["cost_basis_usd"] == "100.00"
    assert payload["positions"][0]["latest_raw_price_usd"] == "125.25"
    assert payload["positions"][0]["market_value_usd"] == "125.25"
    assert payload["positions"][0]["unrealized_pnl_usd"] == "25.25"
    assert payload["positions"][0]["unrealized_pnl_percent"] == "25.25"
    assert payload["positions"][0]["lots"][0]["unit_cost_usd"] == "100.00"
    assert payload["positions"][1]["set_name"] is None
    assert payload["positions"][1]["card_number"] is None
    assert payload["positions"][1]["latest_raw_price_usd"] is None
    assert payload["positions"][1]["latest_price_at"] is None
    assert payload["positions"][1]["market_value_usd"] is None
    assert payload["positions"][1]["unrealized_pnl_usd"] is None
    assert payload["positions"][1]["unrealized_pnl_percent"] is None
