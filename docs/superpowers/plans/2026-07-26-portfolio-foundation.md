# Portfolio Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let authenticated users record raw-card purchase lots, see grouped cost basis and evidence-safe current value, and manage those lots from a responsive Portfolio workspace.

**Architecture:** A new `portfolio_lots` table stores immutable asset identity plus editable quantity, USD unit cost, and purchase date. A user-scoped service owns CRUD, the Free-tier distinct-position limit, bounded-query aggregation, and latest active-source raw valuation; thin FastAPI routes own transactions and HTTP mapping. A focused React API module and page render summary, allocation, grouped positions, and accessible add/edit/delete workflows without adding AI, provider, scheduler, or historical snapshot dependencies.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, PostgreSQL/SQLite tests, Pytest, React 19, TypeScript 6, Vite, Vitest, Testing Library, Lucide React, existing Flashcard Planet CSS tokens.

---

## Approved Contract

The source of product truth is
`docs/superpowers/specs/2026-07-26-portfolio-foundation-design.md`.
Implementation must preserve these invariants:

- Every purchase is an independent lot; positions group lots by `asset_id`.
- Valuation uses only the latest USD observation whose
  `market_segment == "raw"` and whose source is selected by
  `get_active_price_source_filter(db)`.
- Missing prices stay missing. Purchase cost is never substituted for market
  value.
- Free users may own 10 distinct positions. Plus and Pro users are unlimited.
- Another lot for an existing asset is allowed even when a Free user is at the
  limit.
- A lot owned by another user is indistinguishable from a missing lot.
- Every API route derives ownership from `get_current_user`; no request accepts
  a user ID.
- No AI call, Groq call, scheduled job, portfolio snapshot, grade valuation,
  currency conversion, sale, or recommendation is part of this PR.

## File Map

### Backend persistence and contracts

- Create `migrations/versions/0044_add_portfolio_lots.py`: schema migration.
- Create `backend/app/models/portfolio_lot.py`: persistence model only.
- Modify `backend/app/models/__init__.py`: register and export the model.
- Modify `backend/app/models/user.py`: add user-to-lots relationship.
- Modify `backend/app/models/asset.py`: add asset-to-lots relationship.
- Create `backend/app/schemas/portfolio.py`: request and response contracts.
- Modify `backend/app/core/permissions.py`: portfolio capability and hard limit.

### Backend behavior and delivery

- Create `backend/app/services/portfolio_service.py`: scoped CRUD, limit
  enforcement, grouping, valuation, and allocation.
- Create `backend/app/api/routes/portfolio.py`: authenticated HTTP surface and
  transaction/error boundaries.
- Modify `backend/app/api/router.py`: register the portfolio router.

### Backend tests

- Create `tests/test_portfolio_migration.py`: model and migration contract.
- Create `tests/test_portfolio_permissions.py`: tier capability and limit.
- Create `tests/test_portfolio_schemas.py`: Pydantic validation.
- Create `tests/test_portfolio_service.py`: CRUD, ownership, limit, valuation,
  coverage, allocation, and query bound.
- Create `tests/test_portfolio_api.py`: auth, status codes, payloads,
  transaction boundaries, and router registration.

### Frontend

- Create `frontend/src/types/portfolio.ts`: Portfolio API types.
- Create `frontend/src/api/portfolio.ts`: authenticated same-origin requests and
  structured API errors.
- Create `frontend/src/api/portfolio.test.ts`: request serialization and errors.
- Create `frontend/src/components/PortfolioSummary.tsx`: compact summary strip.
- Create `frontend/src/components/PortfolioAllocation.tsx`: allocation band and
  legend.
- Create `frontend/src/components/PortfolioPositionTable.tsx`: grouped rows,
  expansion, and lot actions.
- Create `frontend/src/components/PortfolioLotDialog.tsx`: card search and lot
  form.
- Create `frontend/src/components/PortfolioDeleteDialog.tsx`: destructive
  confirmation.
- Create `frontend/src/pages/PortfolioPage.tsx`: authentication, load, retry,
  mutation, and stale-request orchestration.
- Create `frontend/src/pages/PortfolioPage.test.tsx`: page behavior.
- Modify `frontend/src/main.tsx`: add `/portfolio`.
- Modify `frontend/src/components/NavBar.tsx`: add Portfolio primary navigation.
- Modify `frontend/src/components/__tests__/NavBar.test.tsx`: navigation
  regression.
- Modify `frontend/src/styles/theme.css`: stable responsive Portfolio layout.

### Product tracking

- Modify `docs/flashcard-planet-v2/CODEX_EXECUTION_PLAN.md`: record the completed
  Phase 6 foundation only after final verification.

---

### Task 1: Persist Portfolio Lots

**Files:**
- Create: `tests/test_portfolio_migration.py`
- Create: `migrations/versions/0044_add_portfolio_lots.py`
- Create: `backend/app/models/portfolio_lot.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/models/user.py`
- Modify: `backend/app/models/asset.py`

- [ ] **Step 1: Write the failing model and migration contract**

Create `tests/test_portfolio_migration.py` with tests that load revision `0044`
through `importlib`, replace `migration.op` with `MagicMock`, and assert:

```python
TABLE_NAME = "portfolio_lots"
EXPECTED_COLUMNS = [
    "id",
    "user_id",
    "asset_id",
    "quantity",
    "unit_cost_usd",
    "purchased_on",
    "created_at",
    "updated_at",
]

def test_model_exports_exact_columns():
    model = importlib.import_module(
        "backend.app.models.portfolio_lot"
    ).PortfolioLot
    models_package = importlib.import_module("backend.app.models")

    assert model.__tablename__ == TABLE_NAME
    assert list(model.__table__.columns.keys()) == EXPECTED_COLUMNS
    assert models_package.PortfolioLot is model
    assert "PortfolioLot" in models_package.__all__

def test_model_defines_constraints_indexes_and_foreign_keys():
    model = importlib.import_module(
        "backend.app.models.portfolio_lot"
    ).PortfolioLot
    table = model.__table__

    checks = {
        constraint.name: str(constraint.sqltext)
        for constraint in table.constraints
        if isinstance(constraint, sa.CheckConstraint)
    }
    assert checks == {
        "ck_portfolio_lots_quantity_positive": "quantity > 0",
        "ck_portfolio_lots_unit_cost_non_negative": "unit_cost_usd >= 0",
    }
    assert {
        index.name for index in table.indexes
    } == {
        "ix_portfolio_lots_user_asset",
        "ix_portfolio_lots_user_purchased_on",
    }

    user_fk = next(iter(table.c.user_id.foreign_keys))
    asset_fk = next(iter(table.c.asset_id.foreign_keys))
    assert user_fk.target_fullname == "users.id"
    assert user_fk.ondelete == "CASCADE"
    assert asset_fk.target_fullname == "assets.id"

def test_model_has_no_user_asset_unique_constraint():
    model = importlib.import_module(
        "backend.app.models.portfolio_lot"
    ).PortfolioLot
    assert not [
        constraint
        for constraint in model.__table__.constraints
        if isinstance(constraint, sa.UniqueConstraint)
    ]
```

Add this loader and separate upgrade, index, and downgrade tests using the
established migration isolation pattern:

```python
def _load_migration():
    path = (
        Path(__file__).parent.parent
        / "migrations"
        / "versions"
        / "0044_add_portfolio_lots.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0044", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    migration.op = MagicMock()
    return migration


def test_upgrade_creates_exact_columns_constraints_and_indexes():
    migration = _load_migration()
    migration.upgrade()
    table_args = migration.op.create_table.call_args.args
    columns = {
        item.name: item for item in table_args[1:] if isinstance(item, sa.Column)
    }
    assert table_args[0] == TABLE_NAME
    assert list(columns) == EXPECTED_COLUMNS
    assert columns["unit_cost_usd"].type.precision == 12
    assert columns["unit_cost_usd"].type.scale == 2
    index_calls = migration.op.create_index.call_args_list
    assert index_calls[0] == call(
        "ix_portfolio_lots_user_asset",
        TABLE_NAME,
        ["user_id", "asset_id"],
    )
    assert index_calls[1].args[:2] == (
        "ix_portfolio_lots_user_purchased_on",
        TABLE_NAME,
    )
    assert index_calls[1].args[2][0] == "user_id"
    assert str(index_calls[1].args[2][1]) == "purchased_on DESC"
```

Assert revision `0044` points to `0043`, exact column nullability and timestamp
time zones, both named check constraints, both foreign keys, and this downgrade
order:

```python
assert migration.op.method_calls == [
    call.drop_index(
        "ix_portfolio_lots_user_purchased_on",
        table_name=TABLE_NAME,
    ),
    call.drop_index(
        "ix_portfolio_lots_user_asset",
        table_name=TABLE_NAME,
    ),
    call.drop_table(TABLE_NAME),
]
```

- [ ] **Step 2: Run the contract and confirm the red state**

Run:

```powershell
python -m pytest tests/test_portfolio_migration.py -q
```

Expected: collection fails because `backend.app.models.portfolio_lot` and
revision `0044` do not exist.

- [ ] **Step 3: Add the model and relationships**

Create `backend/app/models/portfolio_lot.py`:

```python
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric, desc
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from backend.app.db.base import Base


class PortfolioLot(Base):
    __tablename__ = "portfolio_lots"
    __table_args__ = (
        CheckConstraint(
            "quantity > 0",
            name="ck_portfolio_lots_quantity_positive",
        ),
        CheckConstraint(
            "unit_cost_usd >= 0",
            name="ck_portfolio_lots_unit_cost_non_negative",
        ),
        Index("ix_portfolio_lots_user_asset", "user_id", "asset_id"),
        Index(
            "ix_portfolio_lots_user_purchased_on",
            "user_id",
            desc("purchased_on"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assets.id"),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )
    purchased_on: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped["User"] = relationship(back_populates="portfolio_lots")
    asset: Mapped["Asset"] = relationship(back_populates="portfolio_lots")
```

Import and export `PortfolioLot` from `backend/app/models/__init__.py`, and add:

```python
# backend/app/models/user.py
portfolio_lots: Mapped[list["PortfolioLot"]] = relationship(
    back_populates="user",
    cascade="all, delete-orphan",
)

# backend/app/models/asset.py
portfolio_lots: Mapped[list["PortfolioLot"]] = relationship(
    back_populates="asset",
    cascade="all, delete-orphan",
)
```

- [ ] **Step 4: Add revision 0044**

Create `migrations/versions/0044_add_portfolio_lots.py` with
`revision = "0044"` and `down_revision = "0043"`. The `upgrade()` body is:

```python
op.create_table(
    "portfolio_lots",
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column(
        "user_id",
        UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column(
        "asset_id",
        UUID(as_uuid=True),
        sa.ForeignKey("assets.id"),
        nullable=False,
    ),
    sa.Column("quantity", sa.Integer(), nullable=False),
    sa.Column("unit_cost_usd", sa.Numeric(12, 2), nullable=False),
    sa.Column("purchased_on", sa.Date(), nullable=False),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    ),
    sa.CheckConstraint(
        "quantity > 0",
        name="ck_portfolio_lots_quantity_positive",
    ),
    sa.CheckConstraint(
        "unit_cost_usd >= 0",
        name="ck_portfolio_lots_unit_cost_non_negative",
    ),
)
op.create_index(
    "ix_portfolio_lots_user_asset",
    "portfolio_lots",
    ["user_id", "asset_id"],
)
op.create_index(
    "ix_portfolio_lots_user_purchased_on",
    "portfolio_lots",
    ["user_id", sa.text("purchased_on DESC")],
)
```

`downgrade()` drops the purchase-date index, the asset index, and then the
table.

- [ ] **Step 5: Run the persistence tests**

Run:

```powershell
python -m pytest tests/test_portfolio_migration.py tests/test_init_db.py -q
```

Expected: all tests pass. If SQLAlchemy represents the descending index as an
expression instead of a named column, assert its compiled PostgreSQL text is
`purchased_on DESC`; do not weaken the index contract to ascending.

- [ ] **Step 6: Commit persistence**

```powershell
git add migrations/versions/0044_add_portfolio_lots.py backend/app/models tests/test_portfolio_migration.py
git commit -m "feat: add portfolio lot persistence"
```

---

### Task 2: Define Tier and API Contracts

**Files:**
- Create: `tests/test_portfolio_permissions.py`
- Create: `tests/test_portfolio_schemas.py`
- Modify: `backend/app/core/permissions.py`
- Create: `backend/app/schemas/portfolio.py`

- [ ] **Step 1: Write failing permission tests**

Create `tests/test_portfolio_permissions.py`:

```python
from backend.app.core.permissions import (
    Feature,
    Tier,
    can,
    portfolio_position_limit,
)


def test_free_has_ten_portfolio_positions():
    assert portfolio_position_limit(Tier.FREE) == 10
    assert not can(Tier.FREE, Feature.PORTFOLIO_UNLIMITED)


def test_plus_and_pro_have_unlimited_portfolio_positions():
    assert portfolio_position_limit(Tier.PLUS) is None
    assert portfolio_position_limit(Tier.PRO) is None
    assert can(Tier.PLUS, Feature.PORTFOLIO_UNLIMITED)
    assert can(Tier.PRO, Feature.PORTFOLIO_UNLIMITED)
```

- [ ] **Step 2: Write failing schema tests**

Create `tests/test_portfolio_schemas.py` and assert:

```python
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.app.schemas.portfolio import (
    PortfolioLotCreateRequest,
    PortfolioLotPatchRequest,
)


def test_create_request_accepts_valid_decimal_input():
    request = PortfolioLotCreateRequest(
        asset_id=uuid4(),
        quantity=2,
        unit_cost_usd="125.00",
        purchased_on="2026-07-01",
    )
    assert request.quantity == 2
    assert request.unit_cost_usd == Decimal("125.00")
    assert request.purchased_on == date(2026, 7, 1)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("quantity", 0),
        ("quantity", -1),
        ("unit_cost_usd", "-0.01"),
        ("unit_cost_usd", "10000000000.00"),
    ],
)
def test_create_request_rejects_invalid_numbers(field, value):
    payload = {
        "asset_id": uuid4(),
        "quantity": 1,
        "unit_cost_usd": "1.00",
        "purchased_on": "2026-07-01",
    }
    payload[field] = value
    with pytest.raises(ValidationError):
        PortfolioLotCreateRequest(**payload)


def test_patch_requires_at_least_one_field():
    with pytest.raises(ValidationError):
        PortfolioLotPatchRequest()


def test_patch_rejects_asset_identity():
    with pytest.raises(ValidationError):
        PortfolioLotPatchRequest(asset_id=uuid4())
```

Also verify that `quantity`, `unit_cost_usd`, and `purchased_on` are each valid
alone in a patch, while explicit `null` is rejected.

- [ ] **Step 3: Run the new contracts and confirm they fail**

Run:

```powershell
python -m pytest tests/test_portfolio_permissions.py tests/test_portfolio_schemas.py -q
```

Expected: imports fail because the feature, helper, and schemas do not exist.

- [ ] **Step 4: Add the portfolio capability**

In `backend/app/core/permissions.py` add:

```python
class Feature(str, Enum):
    PORTFOLIO_UNLIMITED = "portfolio_unlimited"


FEATURE_TIER_REQUIREMENTS[Feature.PORTFOLIO_UNLIMITED] = Tier.PLUS

FREE_PORTFOLIO_POSITION_LIMIT: int = 10


def portfolio_position_limit(access_tier: str) -> int | None:
    """Return the distinct portfolio-position cap. None means unlimited."""
    return (
        None
        if can(access_tier, Feature.PORTFOLIO_UNLIMITED)
        else FREE_PORTFOLIO_POSITION_LIMIT
    )
```

Do not tie this helper to watchlist limits.

- [ ] **Step 5: Add strict Pydantic contracts**

Create `backend/app/schemas/portfolio.py` with:

```python
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


Money = Decimal


class PortfolioLotCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: UUID
    quantity: int = Field(ge=1)
    unit_cost_usd: Money = Field(ge=0, max_digits=12, decimal_places=2)
    purchased_on: date


class PortfolioLotPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quantity: int | None = Field(default=None, ge=1)
    unit_cost_usd: Money | None = Field(
        default=None,
        ge=0,
        max_digits=12,
        decimal_places=2,
    )
    purchased_on: date | None = None

    @model_validator(mode="after")
    def require_change(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one field is required.")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Portfolio lot fields cannot be null.")
        return self


class PortfolioLotResponse(BaseModel):
    id: UUID
    asset_id: UUID
    quantity: int
    unit_cost_usd: Money
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
    average_unit_cost_usd: Money
    cost_basis_usd: Money
    latest_raw_price_usd: Money | None
    latest_price_at: datetime | None
    market_value_usd: Money | None
    unrealized_pnl_usd: Money | None
    unrealized_pnl_percent: Money | None
    valuation_status: Literal["priced", "unpriced"]
    lots: list[PortfolioLotResponse]


class PortfolioAllocationResponse(BaseModel):
    game: str
    market_value_usd: Money
    percentage: Money
    priced_position_count: int


class PortfolioSummaryResponse(BaseModel):
    total_cost_basis: Money
    priced_cost_basis: Money
    total_market_value: Money
    unrealized_pnl: Money
    unrealized_pnl_percent: Money | None
    position_count: int
    priced_position_count: int
    unpriced_position_count: int
    valuation_coverage_percent: Money
    position_limit: int | None


class PortfolioResponse(BaseModel):
    summary: PortfolioSummaryResponse
    allocations: list[PortfolioAllocationResponse]
    positions: list[PortfolioPositionResponse]
```

Money fields intentionally serialize as JSON strings under Pydantic v2.

- [ ] **Step 6: Run contracts and the existing permission suite**

Run:

```powershell
python -m pytest tests/test_portfolio_permissions.py tests/test_portfolio_schemas.py tests/test_permissions.py -q
```

Expected: all tests pass and existing tiers remain unchanged.

- [ ] **Step 7: Commit contracts**

```powershell
git add backend/app/core/permissions.py backend/app/schemas/portfolio.py tests/test_portfolio_permissions.py tests/test_portfolio_schemas.py
git commit -m "feat: define portfolio access and contracts"
```

---

### Task 3: Implement User-Scoped Lot CRUD and Limit Enforcement

**Files:**
- Create: `tests/test_portfolio_service.py`
- Create: `backend/app/services/portfolio_service.py`

- [ ] **Step 1: Add service fixtures and failing CRUD tests**

In `tests/test_portfolio_service.py`, use `sqlite_db` and create committed
`User` and `Asset` rows through helpers:

```python
def make_user(db, *, tier="free", email="owner@example.com"):
    user = User(email=email, access_tier=tier)
    db.add(user)
    db.flush()
    return user


def make_asset(db, index=1, game="pokemon"):
    asset = Asset(
        name=f"Card {index}",
        set_name="Test Set",
        card_number=str(index),
        game=game,
        external_id=f"portfolio-card-{index}",
    )
    db.add(asset)
    db.flush()
    return asset
```

Write tests for:

```python
def test_create_update_and_delete_owned_lot(sqlite_db):
    user = make_user(sqlite_db)
    asset = make_asset(sqlite_db)
    created = create_portfolio_lot(
        sqlite_db,
        user,
        PortfolioLotCreateRequest(
            asset_id=asset.id,
            quantity=2,
            unit_cost_usd="125.00",
            purchased_on="2026-07-01",
        ),
    )
    assert created.quantity == 2

    updated = update_portfolio_lot(
        sqlite_db,
        user,
        created.id,
        PortfolioLotPatchRequest(quantity=3),
    )
    assert updated.quantity == 3
    delete_portfolio_lot(sqlite_db, user, created.id)
    assert sqlite_db.get(PortfolioLot, created.id) is None


def test_other_users_lot_is_not_observable(sqlite_db):
    owner = make_user(sqlite_db, email="owner@example.com")
    other = make_user(sqlite_db, email="other@example.com")
    asset = make_asset(sqlite_db)
    lot = PortfolioLot(
        user_id=owner.id,
        asset_id=asset.id,
        quantity=1,
        unit_cost_usd=Decimal("10.00"),
        purchased_on=date(2026, 7, 1),
    )
    sqlite_db.add(lot)
    sqlite_db.flush()

    with pytest.raises(PortfolioLotNotFoundError):
        update_portfolio_lot(
            sqlite_db,
            other,
            lot.id,
            PortfolioLotPatchRequest(quantity=2),
        )
    with pytest.raises(PortfolioLotNotFoundError):
        delete_portfolio_lot(sqlite_db, other, lot.id)
```

Also assert a missing asset raises `PortfolioAssetNotFoundError`.

- [ ] **Step 2: Add failing tier-limit tests**

Create ten assets and lots for a Free user, then assert:

```python
with pytest.raises(PortfolioPositionLimitError) as error:
    create_portfolio_lot(db, user, request_for_asset(eleventh_asset))
assert error.value.position_limit == 10
assert error.value.position_count == 10
```

Add separate tests proving:

- another lot for asset 1 succeeds at the Free limit;
- an active Plus subscription with legacy `access_tier="free"` is unlimited;
- a Pro user is unlimited;
- the user row lock query runs before the distinct-position count query.

For lock ordering, use a small recording `Session` test double and assert the
first user lookup statement has `_for_update_arg is not None`. The SQLite
integration tests remain the behavioral source of truth.

- [ ] **Step 3: Run focused service tests and confirm the red state**

Run:

```powershell
python -m pytest tests/test_portfolio_service.py -q
```

Expected: import fails because `portfolio_service` does not exist.

- [ ] **Step 4: Implement typed errors and CRUD**

Create `backend/app/services/portfolio_service.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.core.permissions import portfolio_position_limit, resolve_tier
from backend.app.models.asset import Asset
from backend.app.models.portfolio_lot import PortfolioLot
from backend.app.models.user import User
from backend.app.schemas.portfolio import (
    PortfolioLotCreateRequest,
    PortfolioLotPatchRequest,
)


class PortfolioAssetNotFoundError(ValueError):
    pass


class PortfolioLotNotFoundError(ValueError):
    pass


@dataclass(frozen=True)
class PortfolioPositionLimitError(ValueError):
    position_limit: int
    position_count: int


def _effective_tier(user: User) -> str:
    return resolve_tier(
        user.email,
        user.access_tier,
        user.subscription_tier,
        user.subscription_status,
    )


def _owned_lot(db: Session, user_id: UUID, lot_id: UUID) -> PortfolioLot:
    lot = db.scalar(
        select(PortfolioLot).where(
            PortfolioLot.id == lot_id,
            PortfolioLot.user_id == user_id,
        )
    )
    if lot is None:
        raise PortfolioLotNotFoundError
    return lot


def create_portfolio_lot(
    db: Session,
    current_user: User,
    payload: PortfolioLotCreateRequest,
) -> PortfolioLot:
    asset_exists = db.scalar(
        select(Asset.id).where(Asset.id == payload.asset_id)
    )
    if asset_exists is None:
        raise PortfolioAssetNotFoundError

    locked_user = db.scalar(
        select(User)
        .where(User.id == current_user.id)
        .with_for_update()
    )
    if locked_user is None:
        raise PortfolioLotNotFoundError

    already_owned = db.scalar(
        select(PortfolioLot.id)
        .where(
            PortfolioLot.user_id == locked_user.id,
            PortfolioLot.asset_id == payload.asset_id,
        )
        .limit(1)
    )
    limit = portfolio_position_limit(_effective_tier(locked_user))
    if already_owned is None and limit is not None:
        position_count = int(
            db.scalar(
                select(func.count(func.distinct(PortfolioLot.asset_id))).where(
                    PortfolioLot.user_id == locked_user.id
                )
            )
            or 0
        )
        if position_count >= limit:
            raise PortfolioPositionLimitError(limit, position_count)

    lot = PortfolioLot(
        user_id=locked_user.id,
        asset_id=payload.asset_id,
        quantity=payload.quantity,
        unit_cost_usd=payload.unit_cost_usd,
        purchased_on=payload.purchased_on,
    )
    db.add(lot)
    db.flush()
    db.refresh(lot)
    return lot


def update_portfolio_lot(
    db: Session,
    current_user: User,
    lot_id: UUID,
    payload: PortfolioLotPatchRequest,
) -> PortfolioLot:
    lot = _owned_lot(db, current_user.id, lot_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(lot, field, value)
    db.flush()
    db.refresh(lot)
    return lot


def delete_portfolio_lot(
    db: Session,
    current_user: User,
    lot_id: UUID,
) -> None:
    lot = _owned_lot(db, current_user.id, lot_id)
    db.delete(lot)
    db.flush()
```

The service never commits. Keep all lot queries scoped by
`PortfolioLot.user_id == current_user.id`.

- [ ] **Step 5: Run CRUD and limit tests**

Run:

```powershell
python -m pytest tests/test_portfolio_service.py -q
```

Expected: CRUD, isolation, distinct-position, same-asset, Plus, Pro, and lock
tests pass.

- [ ] **Step 6: Commit service mutations**

```powershell
git add backend/app/services/portfolio_service.py tests/test_portfolio_service.py
git commit -m "feat: manage user portfolio lots"
```

---

### Task 4: Build Bounded Raw Valuation and Allocation

**Files:**
- Modify: `tests/test_portfolio_service.py`
- Modify: `backend/app/services/portfolio_service.py`

- [ ] **Step 1: Add failing multi-lot valuation tests**

Extend `tests/test_portfolio_service.py` with a deterministic source fixture.
Patch `backend.app.core.price_sources.get_settings` so the primary source is
`pokemon_tcg_api`, and seed:

- asset A: two lots, quantities 2 and 1, costs 100 and 160;
- asset A: older raw price 170 and newer raw price 200;
- asset A: even newer graded price 500, which must be ignored;
- asset B: one lot with no raw price;
- asset C: zero-cost lot with a raw price of 0.00;
- asset D: a raw price from a non-active source, which must be ignored.

Assert the exact results:

```python
position_a = portfolio.positions[0]
assert position_a.quantity == 3
assert position_a.cost_basis_usd == Decimal("360.00")
assert position_a.average_unit_cost_usd == Decimal("120.00")
assert position_a.latest_raw_price_usd == Decimal("200.00")
assert position_a.market_value_usd == Decimal("600.00")
assert position_a.unrealized_pnl_usd == Decimal("240.00")
assert position_a.unrealized_pnl_percent == Decimal("66.67")
assert [lot.purchased_on for lot in position_a.lots] == [
    date(2026, 7, 10),
    date(2026, 7, 1),
]

position_b = next(
    position for position in portfolio.positions
    if position.asset_id == asset_b.id
)
assert position_b.valuation_status == "unpriced"
assert position_b.latest_raw_price_usd is None
assert position_b.market_value_usd is None
assert position_b.unrealized_pnl_usd is None

position_c = next(
    position for position in portfolio.positions
    if position.asset_id == asset_c.id
)
assert position_c.unrealized_pnl_percent is None
```

- [ ] **Step 2: Add failing summary and allocation tests**

Assert:

```python
assert portfolio.summary.total_cost_basis == Decimal("410.00")
assert portfolio.summary.priced_cost_basis == Decimal("360.00")
assert portfolio.summary.total_market_value == Decimal("600.00")
assert portfolio.summary.unrealized_pnl == Decimal("240.00")
assert portfolio.summary.unrealized_pnl_percent == Decimal("66.67")
assert portfolio.summary.position_count == 4
assert portfolio.summary.priced_position_count == 2
assert portfolio.summary.unpriced_position_count == 2
assert portfolio.summary.valuation_coverage_percent == Decimal("50.00")
```

Use at least two priced games and assert allocation rows are ordered by
`market_value_usd DESC, game ASC`, their percentages sum to `100.00`, and each
row contains the correct priced-position count.

Add empty-portfolio assertions: all monetary totals are `0.00`, counts are
zero, coverage is `0.00`, overall P&L percentage is `None`, allocations and
positions are empty, and `position_limit` reflects the effective tier.

- [ ] **Step 3: Add a bounded-query regression test**

Attach a SQLAlchemy `before_cursor_execute` listener around
`get_portfolio(sqlite_db, user)`. Build 12 positions, reset the counter after
fixture setup, and assert the read executes no more than four SQL statements:

1. load lots and assets;
2. detect the active price source;
3. load latest eligible prices;
4. optional lazy-free relationship bookkeeping.

The count must not increase with position count.

- [ ] **Step 4: Run valuation tests and confirm the red state**

Run:

```powershell
python -m pytest tests/test_portfolio_service.py -q
```

Expected: failures because `get_portfolio` and aggregation do not exist.

- [ ] **Step 5: Implement decimal-safe aggregation**

Add to `portfolio_service.py`:

```python
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import selectinload

from backend.app.core.price_sources import get_active_price_source_filter
from backend.app.models.price_history import PriceHistory
from backend.app.schemas.portfolio import (
    PortfolioAllocationResponse,
    PortfolioLotResponse,
    PortfolioPositionResponse,
    PortfolioResponse,
    PortfolioSummaryResponse,
)

MONEY_QUANTUM = Decimal("0.01")
PERCENT_QUANTUM = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _percent(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    if denominator == 0:
        return None
    return (
        numerator / denominator * Decimal("100")
    ).quantize(PERCENT_QUANTUM, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class _LatestPrice:
    price: Decimal
    captured_at: datetime
```

Implement `_latest_raw_prices(db, asset_ids)` with one window query:

```python
ranked = (
    select(
        PriceHistory.asset_id.label("asset_id"),
        PriceHistory.price.label("price"),
        PriceHistory.captured_at.label("captured_at"),
        func.row_number()
        .over(
            partition_by=PriceHistory.asset_id,
            order_by=(
                PriceHistory.captured_at.desc(),
                PriceHistory.id.desc(),
            ),
        )
        .label("row_number"),
    )
    .where(
        PriceHistory.asset_id.in_(asset_ids),
        PriceHistory.market_segment == "raw",
        PriceHistory.currency == "USD",
        get_active_price_source_filter(db),
    )
    .subquery()
)
rows = db.execute(
    select(ranked.c.asset_id, ranked.c.price, ranked.c.captured_at).where(
        ranked.c.row_number == 1
    )
).all()
return {
    row.asset_id: _LatestPrice(
        price=Decimal(row.price),
        captured_at=row.captured_at,
    )
    for row in rows
}
```

Return `{}` before calling the source helper when `asset_ids` is empty.

- [ ] **Step 6: Implement the Portfolio read model**

`get_portfolio(db, current_user)` must:

1. Load all user lots with `selectinload(PortfolioLot.asset)`.
2. Order the query by asset ID, purchase date descending, created time
   descending, and lot ID ascending so every lot group is deterministic.
3. Group in Python by `asset_id` and sort the completed positions by card
   identity for display.
4. Fetch latest eligible prices once for all asset IDs.
5. Build every position with the formulas in the approved contract.
6. Build the summary from priced and unpriced positions separately.
7. Build allocations from priced market value only.

Use:

```python
lots = db.scalars(
    select(PortfolioLot)
    .options(selectinload(PortfolioLot.asset))
    .where(PortfolioLot.user_id == current_user.id)
    .order_by(
        PortfolioLot.asset_id.asc(),
        PortfolioLot.purchased_on.desc(),
        PortfolioLot.created_at.desc(),
        PortfolioLot.id.asc(),
    )
).all()
```

After building positions, sort them by
`(position.name.casefold(), position.set_name or "", str(position.asset_id))`.
Sort allocations by
`(-allocation.market_value_usd, allocation.game.casefold())`. Calculate each
percentage from total priced market value, round to two decimals, then add the
`100.00 - sum(rounded_percentages)` residual to the first allocation row. This
keeps the deterministic rows at exactly `100.00` even for three equal groups.

For an unpriced position, all four current-value fields
(`latest_raw_price_usd`, `latest_price_at`, `market_value_usd`,
`unrealized_pnl_usd`) and its P&L percentage are `None`.

- [ ] **Step 7: Run service and price-source regressions**

Run:

```powershell
python -m pytest tests/test_portfolio_service.py tests/test_price_sources.py tests/test_market_segment.py -q
```

Expected: all tests pass. The query-bound test stays constant with 12
positions.

- [ ] **Step 8: Commit valuation**

```powershell
git add backend/app/services/portfolio_service.py tests/test_portfolio_service.py
git commit -m "feat: calculate raw portfolio valuation"
```

---

### Task 5: Expose the Authenticated Portfolio API

**Files:**
- Create: `tests/test_portfolio_api.py`
- Create: `backend/app/api/routes/portfolio.py`
- Modify: `backend/app/api/router.py`

- [ ] **Step 1: Write failing API tests**

Build a small FastAPI test app with the portfolio router and dependency
overrides for `get_database`, `get_current_user`, and `get_optional_user`.
Patch service functions at the route module boundary. Assert:

```python
def test_get_portfolio_uses_current_user(client, user, service):
    response = client.get("/api/v1/portfolio")
    assert response.status_code == 200
    service.get_portfolio.assert_called_once_with(db, user)


def test_post_lot_returns_201_and_commits(client, db, service):
    response = client.post(
        "/api/v1/portfolio/lots",
        json={
            "asset_id": str(uuid4()),
            "quantity": 2,
            "unit_cost_usd": "125.00",
            "purchased_on": "2026-07-01",
        },
    )
    assert response.status_code == 201
    db.commit.assert_called_once()


def test_patch_foreign_lot_maps_to_404(client, db, service):
    service.update_portfolio_lot.side_effect = PortfolioLotNotFoundError()
    response = client.patch(
        f"/api/v1/portfolio/lots/{uuid4()}",
        json={"quantity": 3},
    )
    assert response.status_code == 404
    db.rollback.assert_called_once()


def test_free_limit_maps_to_structured_403(client, db, service):
    service.create_portfolio_lot.side_effect = PortfolioPositionLimitError(
        position_limit=10,
        position_count=10,
    )
    response = client.post("/api/v1/portfolio/lots", json=valid_payload)
    assert response.status_code == 403
    assert response.json()["detail"] == {
        "code": "portfolio_position_limit_reached",
        "message": "Free accounts can hold up to 10 portfolio positions.",
        "position_limit": 10,
        "position_count": 10,
        "upgrade_url": "/pricing",
    }
```

Also assert:

- GET, POST, PATCH, and DELETE reject unauthenticated callers;
- POST rejects an injected `user_id` field with 422;
- missing asset maps to 404;
- invalid UUID, zero quantity, negative cost, invalid date, and empty patch map
  to 422;
- DELETE returns an empty HTTP 204 response;
- successful mutation commits once;
- mapped domain errors roll back once;
- unexpected exceptions roll back and propagate to the test client;
- the application router exposes all four routes.

- [ ] **Step 2: Run API tests and confirm the red state**

Run:

```powershell
python -m pytest tests/test_portfolio_api.py -q
```

Expected: import fails because the portfolio router does not exist.

- [ ] **Step 3: Add thin authenticated routes**

Create `backend/app/api/routes/portfolio.py`:

```python
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_user, get_database
from backend.app.models.user import User
from backend.app.schemas.portfolio import (
    PortfolioLotCreateRequest,
    PortfolioLotPatchRequest,
    PortfolioLotResponse,
    PortfolioResponse,
)
from backend.app.services import portfolio_service
from backend.app.services.portfolio_service import (
    PortfolioAssetNotFoundError,
    PortfolioLotNotFoundError,
    PortfolioPositionLimitError,
)

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


def _lot_response(lot) -> PortfolioLotResponse:
    return PortfolioLotResponse.model_validate(lot, from_attributes=True)


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Portfolio resource not found.")


@router.get("", response_model=PortfolioResponse)
def read_portfolio(
    db: Session = Depends(get_database),
    current_user: User = Depends(get_current_user),
) -> PortfolioResponse:
    return portfolio_service.get_portfolio(db, current_user)
```

POST and PATCH call the service, commit, and return `_lot_response`. DELETE
calls the service, commits, and returns `Response(status_code=204)`.

For mutations, catch:

```python
except PortfolioPositionLimitError as exc:
    db.rollback()
    raise HTTPException(
        status_code=403,
        detail={
            "code": "portfolio_position_limit_reached",
            "message": (
                f"Free accounts can hold up to "
                f"{exc.position_limit} portfolio positions."
            ),
            "position_limit": exc.position_limit,
            "position_count": exc.position_count,
            "upgrade_url": "/pricing",
        },
    ) from exc
except (PortfolioAssetNotFoundError, PortfolioLotNotFoundError) as exc:
    db.rollback()
    raise _not_found() from exc
except Exception:
    db.rollback()
    raise
```

GET does not commit or roll back.

- [ ] **Step 4: Register the router**

In `backend/app/api/router.py`, import `portfolio_router` and include it with
`prefix=settings.api_prefix`, immediately after account/watchlist routes.

- [ ] **Step 5: Run API and auth regressions**

Run:

```powershell
python -m pytest tests/test_portfolio_api.py tests/test_auth_dependencies.py tests/test_account_routes.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit API**

```powershell
git add backend/app/api/routes/portfolio.py backend/app/api/router.py tests/test_portfolio_api.py
git commit -m "feat: expose authenticated portfolio API"
```

---

### Task 6: Add the Frontend Portfolio Client

**Files:**
- Create: `frontend/src/types/portfolio.ts`
- Create: `frontend/src/api/portfolio.ts`
- Create: `frontend/src/api/portfolio.test.ts`

- [ ] **Step 1: Write failing client tests**

Create `frontend/src/api/portfolio.test.ts` and mock global `fetch`. Assert:

```typescript
await fetchPortfolio()
expect(fetchMock).toHaveBeenCalledWith('/api/v1/portfolio', {
  credentials: 'same-origin',
})

await createPortfolioLot({
  asset_id: 'asset-1',
  quantity: 2,
  unit_cost_usd: '125.00',
  purchased_on: '2026-07-01',
})
expect(fetchMock).toHaveBeenCalledWith('/api/v1/portfolio/lots', {
  method: 'POST',
  credentials: 'same-origin',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    asset_id: 'asset-1',
    quantity: 2,
    unit_cost_usd: '125.00',
    purchased_on: '2026-07-01',
  }),
})
```

Add exact PATCH and DELETE assertions:

```typescript
await updatePortfolioLot('lot/1', {
  quantity: 3,
  unit_cost_usd: '120.00',
})
expect(fetchMock).toHaveBeenCalledWith('/api/v1/portfolio/lots/lot%2F1', {
  method: 'PATCH',
  credentials: 'same-origin',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ quantity: 3, unit_cost_usd: '120.00' }),
})

await deletePortfolioLot('lot/1')
expect(fetchMock).toHaveBeenCalledWith('/api/v1/portfolio/lots/lot%2F1', {
  method: 'DELETE',
  credentials: 'same-origin',
})
```

Verify:

- DELETE accepts 204 without parsing JSON;
- a 401 throws `PortfolioApiError` with `status === 401`;
- the structured 403 detail is preserved on `.detail`;
- a non-JSON 500 still throws a stable `"Portfolio request failed."` message.

- [ ] **Step 2: Run the client test and confirm the red state**

Run:

```powershell
npm test -- --run src/api/portfolio.test.ts
```

Working directory: `frontend`

Expected: import fails because `api/portfolio.ts` does not exist.

- [ ] **Step 3: Define frontend types**

Create `frontend/src/types/portfolio.ts`:

```typescript
export interface PortfolioLot {
  id: string
  asset_id: string
  quantity: number
  unit_cost_usd: string
  purchased_on: string
  created_at: string
  updated_at: string
}

export interface PortfolioPosition {
  asset_id: string
  name: string
  set_name: string | null
  card_number: string | null
  game: string
  quantity: number
  average_unit_cost_usd: string
  cost_basis_usd: string
  latest_raw_price_usd: string | null
  latest_price_at: string | null
  market_value_usd: string | null
  unrealized_pnl_usd: string | null
  unrealized_pnl_percent: string | null
  valuation_status: 'priced' | 'unpriced'
  lots: PortfolioLot[]
}

export interface PortfolioAllocation {
  game: string
  market_value_usd: string
  percentage: string
  priced_position_count: number
}

export interface PortfolioSummary {
  total_cost_basis: string
  priced_cost_basis: string
  total_market_value: string
  unrealized_pnl: string
  unrealized_pnl_percent: string | null
  position_count: number
  priced_position_count: number
  unpriced_position_count: number
  valuation_coverage_percent: string
  position_limit: number | null
}

export interface Portfolio {
  summary: PortfolioSummary
  allocations: PortfolioAllocation[]
  positions: PortfolioPosition[]
}

export interface PortfolioLotInput {
  asset_id: string
  quantity: number
  unit_cost_usd: string
  purchased_on: string
}

export type PortfolioLotPatch = Partial<
  Pick<PortfolioLotInput, 'quantity' | 'unit_cost_usd' | 'purchased_on'>
>

export interface PortfolioApiErrorDetail {
  code?: string
  message?: string
  position_limit?: number
  position_count?: number
  upgrade_url?: string
}
```

- [ ] **Step 4: Implement one request helper**

Create `frontend/src/api/portfolio.ts` with a private `portfolioRequest` helper
that always sends `credentials: 'same-origin'`, parses success JSON unless
status is 204, and normalizes failures:

```typescript
export class PortfolioApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string | PortfolioApiErrorDetail | null,
  ) {
    super(
      typeof detail === 'string'
        ? detail
        : detail?.message ?? 'Portfolio request failed.',
    )
    this.name = 'PortfolioApiError'
  }
}

async function portfolioRequest<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(path, {
    ...init,
    credentials: 'same-origin',
  })
  if (!response.ok) {
    let detail: string | PortfolioApiErrorDetail | null = null
    try {
      const body = await response.json() as {
        detail?: string | PortfolioApiErrorDetail
      }
      detail = body.detail ?? null
    } catch {
      detail = null
    }
    throw new PortfolioApiError(response.status, detail)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}
```

Export `fetchPortfolio`, `createPortfolioLot`, `updatePortfolioLot`, and
`deletePortfolioLot` with the exact paths from the API contract.

- [ ] **Step 5: Run client tests and TypeScript build**

Run from `frontend`:

```powershell
npm test -- --run src/api/portfolio.test.ts
npm run build
```

Expected: client tests and build pass.

- [ ] **Step 6: Commit the client**

```powershell
git add frontend/src/types/portfolio.ts frontend/src/api/portfolio.ts frontend/src/api/portfolio.test.ts
git commit -m "feat: add portfolio frontend client"
```

---

### Task 7: Render Summary, Allocation, and Grouped Positions

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Create: `frontend/src/components/PortfolioSummary.tsx`
- Create: `frontend/src/components/PortfolioAllocation.tsx`
- Create: `frontend/src/components/PortfolioPositionTable.tsx`
- Create: `frontend/src/components/PortfolioReadView.test.tsx`

- [ ] **Step 1: Write failing read-view tests**

Create `frontend/src/components/PortfolioReadView.test.tsx`. Use fixed response
fixtures and assert:

- Summary renders Total cost, Current value, Unrealized P&L, and Valuation
  coverage.
- Positive P&L includes both `+$240.00` and text `Gain`.
- Negative P&L includes both `-$25.00` and text `Loss`.
- Partial coverage says `1 position is missing a raw market price`.
- Allocation segments have accessible labels such as
  `Pokemon: 75.00% of priced market value`.
- Position rows render `Unpriced` rather than `$0.00` when the price is absent.
- Clicking `Expand lots for Moonbreon` reveals lots in purchase-date-descending
  order.
- Each lot has `Edit lot purchased Jul 10, 2026` and
  `Delete lot purchased Jul 10, 2026` buttons.
- `onEditLot` and `onDeleteLot` receive the exact selected lot and position.

- [ ] **Step 2: Run the read-view test and confirm the red state**

Run from `frontend`:

```powershell
npm test -- --run src/components/PortfolioReadView.test.tsx
```

Expected: component imports fail.

- [ ] **Step 3: Add the repository icon dependency**

Run from `frontend`:

```powershell
npm install lucide-react
```

Expected: `lucide-react` is recorded in `package.json` and
`package-lock.json`. Import only the icons used by Portfolio:
`ChevronDown`, `ChevronRight`, `Pencil`, `Trash2`, `Plus`, and `X`.

- [ ] **Step 4: Implement shared display rules**

In each component, keep formatting local and deterministic:

```typescript
const usd = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 2,
})

function money(value: string): string {
  return usd.format(Number(value))
}
```

`PortfolioSummary` receives only `summary`. Derive:

```typescript
const pnl = Number(summary.unrealized_pnl)
const pnlState = pnl > 0 ? 'gain' : pnl < 0 ? 'loss' : 'flat'
const pnlLabel = pnlState === 'gain' ? 'Gain' : pnlState === 'loss' ? 'Loss' : 'Flat'
```

Render four stable cells in one unframed summary band. Add
`portfolio-value-positive` or `portfolio-value-negative` plus the visible label
so color is not the only signal.

- [ ] **Step 5: Implement allocation**

`PortfolioAllocation` receives `allocations` and `unpricedPositionCount`.
Render one fixed-height horizontal band whose segments use a repeatable
multi-family palette from CSS custom properties:

```typescript
const allocationClasses = [
  'portfolio-allocation-gold',
  'portfolio-allocation-cyan',
  'portfolio-allocation-green',
  'portfolio-allocation-rose',
  'portfolio-allocation-neutral',
]
```

Each segment gets `width: ${allocation.percentage}%`, a minimum of 2px only
when the percentage is greater than zero, and an `aria-label`. Render a compact
legend below. If there are no priced positions, render
`No raw market prices are available for allocation yet.`

- [ ] **Step 6: Implement grouped positions**

`PortfolioPositionTable` props are:

```typescript
interface PortfolioPositionTableProps {
  positions: PortfolioPosition[]
  onEditLot: (position: PortfolioPosition, lot: PortfolioLot) => void
  onDeleteLot: (position: PortfolioPosition, lot: PortfolioLot) => void
}
```

Use a real `<table>` on desktop. Each position row has an icon-only disclosure
button using Lucide `ChevronRight`/`ChevronDown`; it must have an exact
`aria-label` and `title`. Lot edit/delete buttons use Lucide `Pencil` and
`Trash2`, both with exact `aria-label` and `title`. Dialog close controls use
Lucide `X`; do not add hand-drawn SVG markup.

Expanded content is a second `<tr>` containing a nested, unframed lot table.
Use `aria-expanded` on the disclosure button and deterministic React keys.
Render `-` and `Unpriced` for current-value columns when valuation is missing.

- [ ] **Step 7: Run component tests**

Run from `frontend`:

```powershell
npm test -- --run src/components/PortfolioReadView.test.tsx
```

Expected: all read-view tests pass.

- [ ] **Step 8: Commit the read view**

```powershell
git add frontend/package.json frontend/package-lock.json frontend/src/components/PortfolioSummary.tsx frontend/src/components/PortfolioAllocation.tsx frontend/src/components/PortfolioPositionTable.tsx frontend/src/components/PortfolioReadView.test.tsx
git commit -m "feat: render portfolio positions and allocation"
```

---

### Task 8: Add Accessible Lot Create, Edit, and Delete Dialogs

**Files:**
- Create: `frontend/src/components/PortfolioLotDialog.tsx`
- Create: `frontend/src/components/PortfolioDeleteDialog.tsx`
- Create: `frontend/src/components/PortfolioLotDialog.test.tsx`

- [ ] **Step 1: Write failing dialog tests**

Test create mode:

- the dialog resets on each open;
- search waits 300ms before calling `fetchCards`;
- a newer query result cannot be overwritten by an older promise;
- choosing a card reveals quantity, cost, and date fields;
- valid submit sends an exact `PortfolioLotInput`;
- quantity less than 1, negative cost, more than two cost decimals, and missing
  date show inline errors without submitting;
- at the Free limit, existing portfolio asset IDs remain selectable and a new
  asset shows the upgrade message and `/pricing` link.

Test edit mode:

- card identity is read-only;
- the selected lot pre-fills all fields;
- submit sends only `quantity`, `unit_cost_usd`, and `purchased_on`;
- Escape and the Close button restore focus to the opener.

Test delete mode:

- names the card, date, quantity, and unit cost;
- Cancel does not delete;
- Delete invokes `onConfirm(lot.id)` once;
- busy state disables both destructive repeat submission and outside close.

- [ ] **Step 2: Run dialog tests and confirm the red state**

Run from `frontend`:

```powershell
npm test -- --run src/components/PortfolioLotDialog.test.tsx
```

Expected: dialog component imports fail.

- [ ] **Step 3: Implement create/edit dialog state**

Define:

```typescript
type PortfolioLotDialogProps =
  | {
      mode: 'create'
      open: boolean
      positionAssetIds: string[]
      positionLimit: number | null
      busy: boolean
      error: string | null
      onClose: () => void
      onSubmit: (input: PortfolioLotInput) => Promise<void>
    }
  | {
      mode: 'edit'
      open: boolean
      position: PortfolioPosition
      lot: PortfolioLot
      busy: boolean
      error: string | null
      onClose: () => void
      onSubmit: (input: PortfolioLotPatch) => Promise<void>
    }
```

Use `useFocusTrap`, `useScrollLock`, a focused search input, a 300ms debounce,
and a monotonically increasing request sequence:

```typescript
const requestSequence = useRef(0)

useEffect(() => {
  if (mode !== 'create' || !debouncedQuery.trim()) return
  const sequence = ++requestSequence.current
  setSearchState('loading')
  fetchCards({
    search: debouncedQuery.trim(),
    sort: 'change',
    limit: 8,
  }).then(result => {
    if (sequence !== requestSequence.current) return
    setResults(result.cards)
    setSearchState('ready')
  }).catch(() => {
    if (sequence !== requestSequence.current) return
    setSearchState('error')
  })
}, [debouncedQuery, mode])
```

When the dialog closes or the query clears, increment `requestSequence.current`
so late responses are ignored.

Validation rules:

```typescript
const quantityValid = /^[1-9]\d*$/.test(quantity)
const costValid = /^(0|[1-9]\d*)(\.\d{1,2})?$/.test(unitCost)
const dateValid = /^\d{4}-\d{2}-\d{2}$/.test(purchasedOn)
```

Normalize cost to two decimals at submit with
`Number(unitCost).toFixed(2)`. Do not use floating-point arithmetic for
portfolio totals; this conversion only formats form input. Keep the dialog open
while `busy` is true, render `error` in an `aria-live="polite"` region, and
let the page close the dialog only after a successful mutation and refresh.

- [ ] **Step 4: Enforce the position limit in the picker**

Derive:

```typescript
const atLimit =
  positionLimit !== null && positionAssetIds.length >= positionLimit
const isExistingPosition = positionAssetIds.includes(card.asset_id)
const isBlocked = atLimit && !isExistingPosition
```

Blocked results remain visible and explain the limit instead of silently
disappearing. The user can still select any existing position. The server-side
lock and limit remain authoritative.

- [ ] **Step 5: Implement delete confirmation**

`PortfolioDeleteDialog` uses the same focus trap and scroll lock. It accepts:

```typescript
interface PortfolioDeleteDialogProps {
  open: boolean
  position: PortfolioPosition | null
  lot: PortfolioLot | null
  busy: boolean
  onClose: () => void
  onConfirm: (lotId: string) => Promise<void>
}
```

The destructive button has visible `Delete lot` text; this is a clear command,
not an icon-only toolbar action.

- [ ] **Step 6: Run dialog tests and build**

Run from `frontend`:

```powershell
npm test -- --run src/components/PortfolioLotDialog.test.tsx
npm run build
```

Expected: all dialog tests and TypeScript build pass.

- [ ] **Step 7: Commit dialogs**

```powershell
git add frontend/src/components/PortfolioLotDialog.tsx frontend/src/components/PortfolioDeleteDialog.tsx frontend/src/components/PortfolioLotDialog.test.tsx
git commit -m "feat: add portfolio lot workflows"
```

---

### Task 9: Build the Portfolio Page and Navigation

**Files:**
- Create: `frontend/src/pages/PortfolioPage.tsx`
- Create: `frontend/src/pages/PortfolioPage.test.tsx`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/components/NavBar.tsx`
- Modify: `frontend/src/components/__tests__/NavBar.test.tsx`
- Modify: `frontend/src/styles/theme.css`

- [ ] **Step 1: Write failing page-state tests**

Mock `useUser`, the portfolio API module, `fetchCards`, and `NavBar`. Test:

- while user state is loading, the page shows fixed-size skeletons and does not
  request the portfolio;
- unauthenticated users see `Sign in to view your portfolio` and a sign-in
  action, with no portfolio request;
- authenticated empty response shows `Add your first position`;
- authenticated data renders summary, allocation, and positions;
- partial valuation preserves the table and shows a coverage warning;
- initial request failure shows Retry;
- retry succeeds;
- refresh failure after data exists leaves existing data visible and announces
  the error;
- clicking Add, Edit, and Delete performs the API mutation and then refreshes;
- mutation buttons remain disabled while their request is pending;
- a structured 403 opens the limit message and upgrade link;
- a late first load cannot replace a newer post-mutation refresh.

- [ ] **Step 2: Run the page test and confirm the red state**

Run from `frontend`:

```powershell
npm test -- --run src/pages/PortfolioPage.test.tsx
```

Expected: page import fails.

- [ ] **Step 3: Implement page orchestration**

`PortfolioPage` uses `useUser()` and a request sequence:

```typescript
const loadSequence = useRef(0)

const loadPortfolio = useCallback(async (preserveData = false) => {
  const sequence = ++loadSequence.current
  if (!preserveData) setLoadState('loading')
  try {
    const next = await fetchPortfolio()
    if (sequence !== loadSequence.current) return
    setPortfolio(next)
    setLoadState('ready')
    setPageError(null)
  } catch (error) {
    if (sequence !== loadSequence.current) return
    setLoadState('error')
    setPageError('Portfolio data is unavailable.')
  }
}, [])
```

Only call it when `!loading && email`. After each successful mutation, call
`loadPortfolio(true)`. Keep current data visible during refresh and refresh
errors.

Page composition:

```tsx
<>
  <NavBar />
  <main className="page-content portfolio-page">
    <header className="portfolio-page-header">
      <div>
        <h1 className="page-title">Portfolio</h1>
        <p className="page-subtitle">
          Purchase lots, raw market value, and unrealized performance.
        </p>
      </div>
      <button className="btn btn-primary" onClick={openCreate}>
        <Plus aria-hidden="true" size={16} />
        Add lot
      </button>
    </header>
    <PortfolioSummary summary={portfolio.summary} />
    <PortfolioAllocation
      allocations={portfolio.allocations}
      unpricedPositionCount={portfolio.summary.unpriced_position_count}
    />
    <PortfolioPositionTable
      positions={portfolio.positions}
      onEditLot={openEditLot}
      onDeleteLot={openDeleteLot}
    />
  </main>
  {lotDialog?.mode === 'create' && (
    <PortfolioLotDialog
      mode="create"
      open
      positionAssetIds={portfolio.positions.map(position => position.asset_id)}
      positionLimit={portfolio.summary.position_limit}
      busy={mutationBusy}
      error={mutationError}
      onClose={closeLotDialog}
      onSubmit={createLot}
    />
  )}
  {lotDialog?.mode === 'edit' && (
    <PortfolioLotDialog
      mode="edit"
      open
      position={lotDialog.position}
      lot={lotDialog.lot}
      busy={mutationBusy}
      error={mutationError}
      onClose={closeLotDialog}
      onSubmit={patchLot}
    />
  )}
  <PortfolioDeleteDialog
    open={deleteSelection !== null}
    position={deleteSelection?.position ?? null}
    lot={deleteSelection?.lot ?? null}
    busy={mutationBusy}
    onClose={closeDeleteDialog}
    onConfirm={deleteLot}
  />
</>
```

For Free users show
`{position_count} of {position_limit} positions used`; for unlimited tiers show
`{position_count} positions`.

- [ ] **Step 4: Add route and navigation**

Import `PortfolioPage` in `frontend/src/main.tsx` and add:

```tsx
<Route path="/portfolio" element={<PortfolioPage />} />
```

Add `{link('/portfolio', 'Portfolio')}` after Watchlist in `NavBar.tsx`.
Update the NavBar test to assert the link has the `/portfolio` target and
active state on `/portfolio`.

- [ ] **Step 5: Add responsive operational styles**

Append Portfolio-specific selectors to `frontend/src/styles/theme.css`.
Use existing tokens and no gradients:

```css
.portfolio-page {
  min-width: 0;
}

.portfolio-page-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--space-4);
  margin-bottom: var(--space-6);
}

.portfolio-summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  min-height: 96px;
  border-top: 1px solid var(--border-default);
  border-bottom: 1px solid var(--border-default);
}

.portfolio-summary-item {
  min-width: 0;
  padding: var(--space-4);
}

.portfolio-summary-item + .portfolio-summary-item {
  border-left: 1px solid var(--border-subtle);
}

.portfolio-allocation-band {
  display: flex;
  width: 100%;
  height: 14px;
  overflow: hidden;
  border-radius: var(--radius-sm);
  background: var(--bg-elevated);
}

.portfolio-table-wrap {
  width: 100%;
  overflow-x: auto;
  border-top: 1px solid var(--border-default);
}

.portfolio-table {
  width: 100%;
  min-width: 940px;
  border-collapse: collapse;
  table-layout: fixed;
}

.portfolio-allocation-gold { background: var(--gold); }
.portfolio-allocation-cyan { background: #22d3ee; }
.portfolio-allocation-green { background: #22c55e; }
.portfolio-allocation-rose { background: #fb7185; }
.portfolio-allocation-neutral { background: #94a3b8; }
.portfolio-value-positive { color: #4ade80; }
.portfolio-value-negative { color: #fb7185; }

@media (max-width: 719px) {
  .portfolio-page-header {
    align-items: stretch;
    flex-direction: column;
  }

  .portfolio-summary {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .portfolio-summary-item:nth-child(3) {
    border-left: 0;
    border-top: 1px solid var(--border-subtle);
  }

  .portfolio-summary-item:nth-child(4) {
    border-top: 1px solid var(--border-subtle);
  }
}
```

Add focused styles for labels, allocation legend, lot rows, dialog form grid,
stable skeletons, empty/error states, focus-visible outlines, and mobile
wrapping. Keep cards at `8px` radius or less. Do not put the table in a card or
nest cards.

- [ ] **Step 6: Run page, navigation, and build checks**

Run from `frontend`:

```powershell
npm test -- --run src/pages/PortfolioPage.test.tsx src/components/__tests__/NavBar.test.tsx
npm run build
```

Expected: tests and build pass with no TypeScript errors.

- [ ] **Step 7: Commit the page**

```powershell
git add frontend/src/pages/PortfolioPage.tsx frontend/src/pages/PortfolioPage.test.tsx frontend/src/main.tsx frontend/src/components/NavBar.tsx frontend/src/components/__tests__/NavBar.test.tsx frontend/src/styles/theme.css
git commit -m "feat: add portfolio workspace"
```

---

### Task 10: Verify Migration, Security, Accessibility, and Responsive Layout

**Files:**
- Modify only files implicated by a failing check.

- [ ] **Step 1: Run the focused backend suite**

Run:

```powershell
python -m pytest tests/test_portfolio_migration.py tests/test_portfolio_permissions.py tests/test_portfolio_schemas.py tests/test_portfolio_service.py tests/test_portfolio_api.py -q
```

Expected: all Portfolio tests pass.

- [ ] **Step 2: Run the full backend suite**

Run:

```powershell
python -m pytest -q
```

Expected: all tests pass except only any already documented environment-specific
eBay failures that reproduce unchanged on `main`. Compare exact failing test
names with the clean-main baseline; do not classify a new failure as baseline.

- [ ] **Step 3: Run all frontend checks**

Run from `frontend`:

```powershell
npm test
npm run build
npm run lint
```

Expected: all tests and build pass. If repository-wide lint reports existing
unrelated debt, run ESLint against every changed Portfolio file and record both
results in the PR.

- [ ] **Step 4: Verify the migration against PostgreSQL**

When `DATABASE_URL` points to the local test PostgreSQL database, run:

```powershell
alembic upgrade head
alembic downgrade 0043
alembic upgrade head
```

Expected: revision `0044` upgrades, downgrades, and upgrades without error.
Then inspect the schema and confirm the two checks, both foreign keys, and both
indexes exist. Never run the downgrade against production.

- [ ] **Step 5: Run an explicit privacy scan**

Run:

```powershell
rg -n "user_id|discord_user_id|email" backend/app/api/routes/portfolio.py backend/app/schemas/portfolio.py frontend/src/api/portfolio.ts
rg -n "portfolio" backend/app/api/routes/web.py backend/app/api/routes/market.py
```

Expected:

- no Portfolio request model or path contains `user_id`, `discord_user_id`, or
  email;
- no public market/web route exposes portfolio data;
- every lot service query for read/update/delete contains the current user ID.

- [ ] **Step 6: Start the app and verify desktop/mobile behavior**

Start the existing backend and frontend development servers on free local
ports. Use Playwright through the in-app browser at:

- Desktop: `1440 x 900`
- Tablet: `768 x 1024`
- Mobile: `390 x 844`
- Narrow mobile: `320 x 700`

Verify:

- Portfolio is reachable from primary navigation.
- Summary dimensions do not shift between loading and loaded states.
- No page-level horizontal overflow occurs.
- The wide positions table scrolls only inside its table wrapper on mobile.
- No labels, currency values, buttons, dialogs, or expanded lots overlap.
- Add/edit/delete workflows are keyboard reachable.
- Focus is trapped inside open dialogs and restored after close.
- P&L meaning is understandable without color.
- Unpriced positions never display `$0.00` as market value.
- Existing Market, Daily, Watchlist, Alerts, and Account routes still load.

Capture screenshots to the task artifact directory for all four viewports and
inspect each image before continuing.

- [ ] **Step 7: Fix only observed failures and rerun their checks**

For every failure, first add or tighten a regression test, then make the
smallest implementation change, rerun the focused check, and rerun the
appropriate full backend or frontend suite.

- [ ] **Step 8: Commit verification fixes**

If verification required changes:

```powershell
git add --update
git diff --cached --check
git commit -m "fix: harden portfolio foundation"
```

If no files changed, do not create an empty commit.

---

### Task 11: Update Product Tracking and Open the Draft PR

**Files:**
- Modify: `docs/flashcard-planet-v2/CODEX_EXECUTION_PLAN.md`

- [ ] **Step 1: Update the execution plan only after verification**

Mark Portfolio Foundation as completed with the exact delivered scope:

- purchase-lot persistence;
- authenticated CRUD;
- Free 10-position limit and Plus/Pro unlimited access;
- active-source raw valuation;
- valuation coverage and allocation;
- responsive Portfolio workspace.

Keep Decision Center, recommendations, portfolio history, graded holdings,
sales, imports/exports, and AI Portfolio Intelligence pending.

- [ ] **Step 2: Run the final diff audit**

Run:

```powershell
git status --short
git diff --check
git diff --stat main...HEAD
git log --oneline --decorate main..HEAD
```

Expected:

- no secret or `.env` file is tracked;
- no unrelated user file is modified or deleted;
- no OneDrive path appears in the diff;
- all work is under the canonical `Flashcard-planet` repository;
- commits are scoped and readable.

- [ ] **Step 3: Commit documentation**

```powershell
git add docs/flashcard-planet-v2/CODEX_EXECUTION_PLAN.md
git commit -m "docs: record portfolio foundation delivery"
```

- [ ] **Step 4: Push and open a draft PR**

Push `feat/portfolio-foundation` and open a draft PR titled:

```text
feat: add portfolio foundation
```

The PR body must include:

- What users can now do
- Raw-only valuation and missing-price behavior
- Free versus Plus/Pro limits
- Authentication and ownership controls
- Migration and rollback
- Focused/full backend results
- Frontend test/build/lint results
- Desktop/mobile visual verification
- Explicit out-of-scope follow-ups

- [ ] **Step 5: Inspect CI and review feedback**

Wait for all required checks. If a check fails, use
`superpowers:systematic-debugging` before changing code. If review feedback
arrives, use `superpowers:receiving-code-review`, verify the claim against the
approved contract, fix actionable issues with a regression test, and push the
new commit.

---

## Final Acceptance Checklist

- [ ] Multiple lots for one asset aggregate into one position.
- [ ] Free users cannot create an eleventh distinct position.
- [ ] Free users at the limit can add a lot to an existing position.
- [ ] Plus and Pro users are unlimited.
- [ ] Create-time limit checks serialize through a locked user row.
- [ ] Only the latest eligible USD raw price from the active source is used.
- [ ] Graded, non-raw, inactive-source, and missing prices never become value.
- [ ] Summary P&L excludes unpriced cost basis from its P&L denominator.
- [ ] Allocation uses priced market value only and orders deterministically.
- [ ] Zero-cost priced positions have no P&L percentage.
- [ ] Every API route requires the current authenticated user.
- [ ] Another user's lot returns 404 for update and delete.
- [ ] No Portfolio request accepts a user identifier.
- [ ] Add, edit, delete, retry, empty, loading, unpriced, and limit states work.
- [ ] Desktop and mobile layouts have no incoherent overlap or page overflow.
- [ ] Existing product workflows are unchanged.
- [ ] No Groq or other AI provider is called by Portfolio Foundation.
- [ ] No source file outside the canonical `Flashcard-planet` directory is
  moved, deleted, or replaced.
