from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PortfolioLotCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: UUID
    quantity: int = Field(ge=1)
    unit_cost_usd: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    purchased_on: date


class PortfolioLotPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quantity: int | None = Field(default=None, ge=1)
    unit_cost_usd: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=12,
        decimal_places=2,
    )
    purchased_on: date | None = None

    @model_validator(mode="after")
    def require_supplied_non_null_field(self) -> PortfolioLotPatchRequest:
        if not self.model_fields_set:
            raise ValueError("at least one field must be supplied")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("supplied fields cannot be null")
        return self


class PortfolioLotResponse(BaseModel):
    id: UUID
    asset_id: UUID
    quantity: int
    unit_cost_usd: Decimal
    purchased_on: date
    created_at: datetime
    updated_at: datetime


class PortfolioPositionResponse(BaseModel):
    asset_id: UUID
    name: str
    set_name: str | None
    card_number: str | None
    game: str
    quantity: int
    average_unit_cost_usd: Decimal
    cost_basis_usd: Decimal
    latest_raw_price_usd: Decimal | None
    latest_price_at: datetime | None
    market_value_usd: Decimal | None
    unrealized_pnl_usd: Decimal | None
    unrealized_pnl_percent: Decimal | None
    valuation_status: Literal["priced", "unpriced"]
    lots: list[PortfolioLotResponse]


class PortfolioAllocationResponse(BaseModel):
    game: str
    market_value_usd: Decimal
    percentage: Decimal
    priced_position_count: int


class PortfolioSummaryResponse(BaseModel):
    total_cost_basis: Decimal
    priced_cost_basis: Decimal
    total_market_value: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_percent: Decimal | None
    position_count: int
    priced_position_count: int
    unpriced_position_count: int
    valuation_coverage_percent: Decimal
    position_limit: int | None


class PortfolioResponse(BaseModel):
    summary: PortfolioSummaryResponse
    allocations: list[PortfolioAllocationResponse]
    positions: list[PortfolioPositionResponse]
