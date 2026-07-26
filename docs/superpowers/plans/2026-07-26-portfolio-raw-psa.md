# Portfolio Raw and PSA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users record Raw and PSA 1-10 purchase lots as independent positions, value each position only from its exact accepted market segment, and see official catalog art throughout the Portfolio workspace.

**Architecture:** Extend `portfolio_lots` with condition and PSA grade instead of cloning catalog assets. A small identity helper supplies one canonical `(asset_id, condition, psa_grade)` contract to schemas, tier-limit checks, grouping, and valuation; the portfolio service loads exact active-source prices in bounded queries and keeps missing grades unpriced. The existing React Portfolio flow adds condition controls, official images, exact-grade labels, and filtering while retaining the old Raw API compatibility field for staged deployment.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, PostgreSQL/SQLite tests, Pytest, React 19, TypeScript 6, Vite, Vitest, Testing Library, Lucide React, existing Flashcard Planet CSS tokens.

---

## Approved Contract

Source of truth:

`docs/superpowers/specs/2026-07-26-portfolio-raw-psa-private-photos-design.md`

This plan implements the first two approved slices:

1. Condition/grade persistence, contracts, grouping, limits, and exact valuation
2. Raw/PSA frontend experience and official catalog images

Invariants:

- Supported holdings are `raw` and `psa` only.
- PSA grade is an integer from 1 through 10.
- Position identity is `(asset_id, condition, psa_grade)`.
- Raw, PSA 9, and PSA 10 for one card are three distinct positions.
- Existing lots migrate to Raw without data loss.
- Required market segments come from `build_market_segment()`.
- PSA observations must match segment, `grade_company='PSA'`, and exact grade.
- Missing exact prices remain `Unpriced`; no Raw, neighboring-grade, or
  other-company fallback is allowed.
- Adding PSA holdings does not change graded-data admission or signal authority.
- Free-tier limits count complete position identities.
- Official card art comes from catalog metadata and is not user-uploaded media.
- Existing clients that omit condition continue to create Raw lots.
- `latest_raw_price_usd` remains temporarily for old clients; new clients use
  `latest_price_usd`.

## File Map

### Persistence and identity

- Create `migrations/versions/0045_add_portfolio_condition.py`: Raw backfill,
  condition/grade constraints, and identity index.
- Modify `backend/app/models/portfolio_lot.py`: persisted condition and grade.
- Create `backend/app/services/portfolio_identity.py`: canonical identity,
  validation, position key, and market-segment derivation.
- Modify `tests/test_portfolio_migration.py`: revision `0045` and model contract.
- Create `tests/test_portfolio_identity.py`: pure identity behavior.

### Backend contracts and behavior

- Modify `backend/app/schemas/portfolio.py`: condition-aware requests and
  responses, compatibility price field, official image, and unpriced cost.
- Modify `backend/app/services/portfolio_service.py`: complete-identity limits,
  grouping, bounded exact valuation, and image extraction.
- Modify `backend/app/api/routes/portfolio.py`: unchanged route shape with new
  request/response fields.
- Modify `tests/test_portfolio_schemas.py`: Raw/PSA validation.
- Modify `tests/test_portfolio_service.py`: CRUD, limits, grouping, valuation,
  summary, and query bounds.
- Modify `tests/test_portfolio_api.py`: backward-compatible payloads and new
  fields.

### Frontend

- Modify `frontend/src/types/portfolio.ts`: condition-aware API types.
- Modify `frontend/src/api/portfolio.test.ts`: exact create and patch payloads.
- Modify `frontend/src/components/PortfolioLotDialog.tsx`: official image,
  condition segmented control, and PSA grade menu.
- Modify `frontend/src/components/PortfolioLotDialog.test.tsx`: interaction and
  validation.
- Modify `frontend/src/components/PortfolioPositionTable.tsx`: image, holding
  label, exact price, and condition filters.
- Modify `frontend/src/components/PortfolioReadView.test.tsx`: rendered
  positions, images, filters, and unpriced state.
- Modify `frontend/src/components/PortfolioSummary.tsx`: unpriced cost.
- Modify `frontend/src/pages/PortfolioPage.tsx`: complete position keys and
  updated copy.
- Modify `frontend/src/pages/PortfolioPage.test.tsx`: mutation orchestration and
  limit behavior.
- Modify `frontend/src/styles/theme.css`: fixed image dimensions, controls,
  filters, and responsive layout.

### Delivery

- Modify `docs/flashcard-planet-v2/CODEX_EXECUTION_PLAN.md`: record completion
  only after all verification passes.

---

### Task 1: Persist Condition and PSA Grade

**Files:**
- Modify: `tests/test_portfolio_migration.py`
- Create: `migrations/versions/0045_add_portfolio_condition.py`
- Modify: `backend/app/models/portfolio_lot.py`

- [ ] **Step 1: Write the failing model contract**

Extend the expected model columns and checks in
`tests/test_portfolio_migration.py`:

```python
EXPECTED_COLUMNS = [
    "id",
    "user_id",
    "asset_id",
    "condition",
    "psa_grade",
    "quantity",
    "unit_cost_usd",
    "purchased_on",
    "created_at",
    "updated_at",
]

def test_model_defines_condition_grade_contract():
    model = importlib.import_module(
        "backend.app.models.portfolio_lot"
    ).PortfolioLot
    table = model.__table__
    checks = {
        constraint.name: str(constraint.sqltext)
        for constraint in table.constraints
        if isinstance(constraint, sa.CheckConstraint)
    }

    assert str(table.c.condition.type) == "VARCHAR(8)"
    assert table.c.condition.nullable is False
    assert table.c.condition.default.arg == "raw"
    assert isinstance(table.c.psa_grade.type, sa.SmallInteger)
    assert table.c.psa_grade.nullable is True
    assert checks["ck_portfolio_lots_condition"] == (
        "condition IN ('raw', 'psa')"
    )
    assert checks["ck_portfolio_lots_condition_grade"] == (
        "(condition = 'raw' AND psa_grade IS NULL) OR "
        "(condition = 'psa' AND psa_grade BETWEEN 1 AND 10)"
    )
    assert "ix_portfolio_lots_user_holding" in {
        index.name for index in table.indexes
    }
```

Update the index assertion so the new grouping index contains:

```python
["user_id", "asset_id", "condition", "psa_grade"]
```

- [ ] **Step 2: Write the failing revision 0045 contract**

Add a loader for `0045_add_portfolio_condition.py` and assert:

```python
def test_condition_migration_metadata_and_operations():
    migration = _load_revision("0045_add_portfolio_condition.py")
    assert migration.revision == "0045"
    assert migration.down_revision == "0044"

    migration.upgrade()

    add_column_calls = migration.op.add_column.call_args_list
    assert [call.args[:2] for call in add_column_calls] == [
        ("portfolio_lots", mock.ANY),
        ("portfolio_lots", mock.ANY),
    ]
    assert add_column_calls[0].args[1].name == "condition"
    assert add_column_calls[1].args[1].name == "psa_grade"
    migration.op.execute.assert_called_once()
    migration.op.alter_column.assert_called_once_with(
        "portfolio_lots",
        "condition",
        existing_type=sa.String(length=8),
        nullable=False,
        server_default=sa.text("'raw'"),
    )
```

Assert the upgrade drops `ix_portfolio_lots_user_asset`, creates the two named
checks, and creates:

```python
call(
    "ix_portfolio_lots_user_holding",
    "portfolio_lots",
    ["user_id", "asset_id", "condition", "psa_grade"],
)
```

Assert downgrade drops the new index and checks, drops the two columns, and
restores `ix_portfolio_lots_user_asset`.

- [ ] **Step 3: Run the persistence tests and confirm failure**

Run:

```powershell
python -m pytest tests/test_portfolio_migration.py -q
```

Expected: failures report missing `condition`, `psa_grade`, and revision `0045`.

- [ ] **Step 4: Extend the SQLAlchemy model**

In `backend/app/models/portfolio_lot.py`, import `SmallInteger` and `String`.
Add these checks and replace the old grouping index:

```python
CheckConstraint(
    "condition IN ('raw', 'psa')",
    name="ck_portfolio_lots_condition",
),
CheckConstraint(
    "(condition = 'raw' AND psa_grade IS NULL) OR "
    "(condition = 'psa' AND psa_grade BETWEEN 1 AND 10)",
    name="ck_portfolio_lots_condition_grade",
),
Index(
    "ix_portfolio_lots_user_holding",
    "user_id",
    "asset_id",
    "condition",
    "psa_grade",
),
```

Add fields before quantity:

```python
condition: Mapped[str] = mapped_column(
    String(8),
    nullable=False,
    default="raw",
    server_default="raw",
)
psa_grade: Mapped[int | None] = mapped_column(
    SmallInteger,
    nullable=True,
)
```

- [ ] **Step 5: Add migration 0045**

Create `migrations/versions/0045_add_portfolio_condition.py`. Upgrade:

```python
op.add_column(
    "portfolio_lots",
    sa.Column("condition", sa.String(length=8), nullable=True),
)
op.add_column(
    "portfolio_lots",
    sa.Column("psa_grade", sa.SmallInteger(), nullable=True),
)
op.execute("UPDATE portfolio_lots SET condition = 'raw' WHERE condition IS NULL")
op.alter_column(
    "portfolio_lots",
    "condition",
    existing_type=sa.String(length=8),
    nullable=False,
    server_default=sa.text("'raw'"),
)
op.create_check_constraint(
    "ck_portfolio_lots_condition",
    "portfolio_lots",
    "condition IN ('raw', 'psa')",
)
op.create_check_constraint(
    "ck_portfolio_lots_condition_grade",
    "portfolio_lots",
    "(condition = 'raw' AND psa_grade IS NULL) OR "
    "(condition = 'psa' AND psa_grade BETWEEN 1 AND 10)",
)
op.drop_index(
    "ix_portfolio_lots_user_asset",
    table_name="portfolio_lots",
)
op.create_index(
    "ix_portfolio_lots_user_holding",
    "portfolio_lots",
    ["user_id", "asset_id", "condition", "psa_grade"],
)
```

Downgrade reverses that order, restores the old two-column index, and leaves all
former lots intact as Raw once revision `0045` is reapplied.

- [ ] **Step 6: Run persistence tests**

Run:

```powershell
python -m pytest tests/test_portfolio_migration.py tests/test_init_db.py -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit persistence**

```powershell
git add migrations/versions/0045_add_portfolio_condition.py backend/app/models/portfolio_lot.py tests/test_portfolio_migration.py
git commit -m "feat: persist portfolio condition and psa grade"
```

---

### Task 2: Define One Canonical Holding Identity

**Files:**
- Create: `tests/test_portfolio_identity.py`
- Create: `backend/app/services/portfolio_identity.py`
- Modify: `backend/app/schemas/portfolio.py`
- Modify: `tests/test_portfolio_schemas.py`

- [ ] **Step 1: Write failing identity tests**

Create `tests/test_portfolio_identity.py`:

```python
from uuid import UUID

import pytest

from backend.app.services.portfolio_identity import (
    PortfolioIdentity,
    normalize_holding,
)

ASSET_ID = UUID("11111111-1111-1111-1111-111111111111")


@pytest.mark.parametrize(
    ("condition", "grade", "segment", "key"),
    [
        ("raw", None, "raw", f"{ASSET_ID}:raw"),
        ("psa", 1, "psa_1", f"{ASSET_ID}:psa:1"),
        ("psa", 10, "psa_10", f"{ASSET_ID}:psa:10"),
    ],
)
def test_identity_has_canonical_segment_and_key(condition, grade, segment, key):
    identity = PortfolioIdentity(ASSET_ID, condition, grade)
    assert identity.market_segment == segment
    assert identity.position_key == key


@pytest.mark.parametrize(
    ("condition", "grade"),
    [
        ("raw", 10),
        ("psa", None),
        ("psa", 0),
        ("psa", 11),
        ("bgs", 10),
    ],
)
def test_invalid_holding_combinations_fail(condition, grade):
    with pytest.raises(ValueError):
        normalize_holding(condition, grade)
```

- [ ] **Step 2: Extend failing schema tests**

Add to `tests/test_portfolio_schemas.py`:

```python
def test_create_defaults_to_raw_for_old_clients():
    request = PortfolioLotCreateRequest(
        asset_id=ASSET_ID,
        quantity=1,
        unit_cost_usd="10.00",
        purchased_on="2026-07-20",
    )
    assert request.condition == "raw"
    assert request.psa_grade is None


@pytest.mark.parametrize("grade", range(1, 11))
def test_create_accepts_every_integer_psa_grade(grade):
    request = PortfolioLotCreateRequest(
        asset_id=ASSET_ID,
        condition="psa",
        psa_grade=grade,
        quantity=1,
        unit_cost_usd="10.00",
        purchased_on="2026-07-20",
    )
    assert request.psa_grade == grade


@pytest.mark.parametrize(
    "payload",
    [
        {"condition": "raw", "psa_grade": 10},
        {"condition": "psa"},
        {"condition": "psa", "psa_grade": 0},
        {"condition": "psa", "psa_grade": 11},
        {"condition": "bgs", "psa_grade": 10},
    ],
)
def test_create_rejects_invalid_holding(payload):
    with pytest.raises(ValidationError):
        PortfolioLotCreateRequest(
            asset_id=ASSET_ID,
            quantity=1,
            unit_cost_usd="10.00",
            purchased_on="2026-07-20",
            **payload,
        )


def test_patch_allows_explicit_null_only_for_psa_grade():
    patch = PortfolioLotPatchRequest(
        condition="raw",
        psa_grade=None,
    )
    assert patch.model_fields_set == {"condition", "psa_grade"}
    with pytest.raises(ValidationError):
        PortfolioLotPatchRequest(condition=None)
```

- [ ] **Step 3: Run tests and confirm failure**

Run:

```powershell
python -m pytest tests/test_portfolio_identity.py tests/test_portfolio_schemas.py -q
```

Expected: identity module and condition/grade schema fields are missing.

- [ ] **Step 4: Implement the pure identity helper**

Create `backend/app/services/portfolio_identity.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from backend.app.ingestion.market_segment import build_market_segment

PortfolioCondition = Literal["raw", "psa"]


def normalize_holding(
    condition: str,
    psa_grade: int | None,
) -> tuple[PortfolioCondition, int | None]:
    normalized = condition.strip().lower()
    if normalized == "raw" and psa_grade is None:
        return "raw", None
    if normalized == "psa" and isinstance(psa_grade, int) and 1 <= psa_grade <= 10:
        return "psa", psa_grade
    raise ValueError("Raw requires no grade; PSA requires an integer grade from 1 to 10.")


@dataclass(frozen=True, order=True)
class PortfolioIdentity:
    asset_id: UUID
    condition: PortfolioCondition
    psa_grade: int | None

    def __post_init__(self) -> None:
        condition, grade = normalize_holding(self.condition, self.psa_grade)
        object.__setattr__(self, "condition", condition)
        object.__setattr__(self, "psa_grade", grade)

    @property
    def market_segment(self) -> str:
        if self.condition == "raw":
            return build_market_segment()
        return build_market_segment("PSA", str(self.psa_grade))

    @property
    def position_key(self) -> str:
        if self.condition == "raw":
            return f"{self.asset_id}:raw"
        return f"{self.asset_id}:psa:{self.psa_grade}"
```

- [ ] **Step 5: Extend Pydantic contracts**

In `backend/app/schemas/portfolio.py`:

```python
from backend.app.services.portfolio_identity import normalize_holding

class PortfolioLotCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: UUID
    condition: Literal["raw", "psa"] = "raw"
    psa_grade: int | None = Field(default=None, ge=1, le=10)
    quantity: int = Field(ge=1)
    unit_cost_usd: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    purchased_on: date

    @model_validator(mode="after")
    def validate_holding(self) -> "PortfolioLotCreateRequest":
        normalize_holding(self.condition, self.psa_grade)
        return self
```

Add optional patch fields:

```python
condition: Literal["raw", "psa"] | None = None
psa_grade: int | None = Field(default=None, ge=1, le=10)
```

Change the existing patch null validator so `psa_grade=None` is allowed, while
all other explicitly supplied nulls still fail. Cross-field validation of a
partial patch runs in the service after merging it with the stored lot.

Extend `PortfolioLotResponse` with condition and grade. Extend
`PortfolioPositionResponse` with:

```python
position_key: str
condition: Literal["raw", "psa"]
psa_grade: int | None
market_segment: str
image_url: str | None
latest_price_usd: Decimal | None
latest_raw_price_usd: Decimal | None
```

Extend `PortfolioSummaryResponse` with:

```python
unpriced_cost_basis: Decimal
```

- [ ] **Step 6: Run identity and schema tests**

Run:

```powershell
python -m pytest tests/test_portfolio_identity.py tests/test_portfolio_schemas.py -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit identity and contracts**

```powershell
git add backend/app/services/portfolio_identity.py backend/app/schemas/portfolio.py tests/test_portfolio_identity.py tests/test_portfolio_schemas.py
git commit -m "feat: define portfolio holding identity"
```

---

### Task 3: Enforce Complete-Identity Position Limits

**Files:**
- Modify: `tests/test_portfolio_service.py`
- Modify: `backend/app/services/portfolio_service.py`

- [ ] **Step 1: Write failing create-limit tests**

Add service tests proving:

```python
def test_raw_and_psa_for_one_asset_are_distinct_positions(sqlite_db):
    user = add_user(sqlite_db, "free")
    asset = add_asset(sqlite_db)
    create_portfolio_lot(sqlite_db, user, make_request(asset))
    psa = create_portfolio_lot(
        sqlite_db,
        user,
        make_request(asset, condition="psa", psa_grade=10),
    )
    assert psa.condition == "psa"
    assert psa.psa_grade == 10


def test_same_psa_grade_is_existing_position_at_free_limit(sqlite_db):
    user, assets = fill_ten_positions(
        sqlite_db,
        first_condition="psa",
        first_psa_grade=10,
    )
    added = create_portfolio_lot(
        sqlite_db,
        user,
        make_request(assets[0], condition="psa", psa_grade=10),
    )
    assert added.psa_grade == 10
```

Build the ten-position fixture so one identity is PSA 10 and the rest are Raw.
Assert PSA 9 on that same card is an eleventh identity and is rejected.

- [ ] **Step 2: Write failing edit-limit tests**

Cover both net-count outcomes:

```python
def test_edit_only_source_lot_can_move_identity_at_limit(sqlite_db):
    user, lots = fill_ten_lots(sqlite_db)
    updated = update_portfolio_lot(
        sqlite_db,
        user,
        lots[0].id,
        PortfolioLotPatchRequest(condition="psa", psa_grade=10),
    )
    assert updated.condition == "psa"
    assert updated.psa_grade == 10


def test_edit_rejected_when_source_remains_and_target_is_new(sqlite_db):
    user, lots = fill_ten_lots(sqlite_db)
    create_portfolio_lot(
        sqlite_db,
        user,
        make_request(lots[0].asset),
    )
    with pytest.raises(PortfolioPositionLimitError):
        update_portfolio_lot(
            sqlite_db,
            user,
            lots[0].id,
            PortfolioLotPatchRequest(condition="psa", psa_grade=10),
        )
```

Also test merging a lot into an existing target identity at the limit.

- [ ] **Step 3: Run limit tests and confirm failure**

Run:

```powershell
python -m pytest tests/test_portfolio_service.py -k "position or identity or limit" -q
```

Expected: existing asset-only limit logic miscounts condition identities and
does not validate grade changes.

- [ ] **Step 4: Add identity-aware helpers**

In `backend/app/services/portfolio_service.py`, add:

```python
def _identity_for_lot(lot: PortfolioLot) -> PortfolioIdentity:
    return PortfolioIdentity(lot.asset_id, lot.condition, lot.psa_grade)


def _identity_exists(
    db: Session,
    user_id: UUID,
    identity: PortfolioIdentity,
    *,
    excluding_lot_id: UUID | None = None,
) -> bool:
    query = select(PortfolioLot.id).where(
        PortfolioLot.user_id == user_id,
        PortfolioLot.asset_id == identity.asset_id,
        PortfolioLot.condition == identity.condition,
        PortfolioLot.psa_grade.is_(None)
        if identity.psa_grade is None
        else PortfolioLot.psa_grade == identity.psa_grade,
    )
    if excluding_lot_id is not None:
        query = query.where(PortfolioLot.id != excluding_lot_id)
    return db.scalar(query.limit(1)) is not None
```

Add one bounded distinct-position count using:

```python
select(
    PortfolioLot.asset_id,
    PortfolioLot.condition,
    PortfolioLot.psa_grade,
).where(
    PortfolioLot.user_id == user_id
).distinct()
```

Count the resulting subquery. Do not use `COUNT(DISTINCT asset_id)`.

- [ ] **Step 5: Apply net-count enforcement**

Create behavior shared by create and update:

```text
create_result = current_count + 1 when target does not exist

update_result =
    current_count
    + 1 when target does not exist
    - 1 when no other lot remains in the source identity
```

Lock the user before any count. Reject only when the resulting count exceeds
the resolved tier limit.

For updates, merge the persisted lot with the patch:

```python
next_condition = payload.condition if "condition" in payload.model_fields_set else lot.condition
next_grade = payload.psa_grade if "psa_grade" in payload.model_fields_set else lot.psa_grade
next_condition, next_grade = normalize_holding(next_condition, next_grade)
```

Persist both normalized values with the other supplied fields.

- [ ] **Step 6: Run service limit tests**

Run:

```powershell
python -m pytest tests/test_portfolio_service.py -k "create or update or limit or identity" -q
```

Expected: all selected tests pass, including refreshed-tier and ownership
regressions.

- [ ] **Step 7: Commit limit behavior**

```powershell
git add backend/app/services/portfolio_service.py tests/test_portfolio_service.py
git commit -m "feat: count portfolio positions by holding identity"
```

---

### Task 4: Add Exact Raw and PSA Valuation

**Files:**
- Modify: `tests/test_portfolio_service.py`
- Modify: `backend/app/services/portfolio_service.py`

- [ ] **Step 1: Write failing exact-valuation tests**

Create one card with Raw, PSA 9, and PSA 10 lots and observations:

```python
add_price(asset, "raw", "100.00")
add_price(asset, "psa_9", "300.00", grade_company="PSA", grade_score="9")
add_price(asset, "psa_10", "700.00", grade_company="PSA", grade_score="10")

portfolio = get_portfolio(sqlite_db, user)
by_key = {position.position_key: position for position in portfolio.positions}

assert by_key[f"{asset.id}:raw"].latest_price_usd == Decimal("100.00")
assert by_key[f"{asset.id}:raw"].latest_raw_price_usd == Decimal("100.00")
assert by_key[f"{asset.id}:psa:9"].latest_price_usd == Decimal("300.00")
assert by_key[f"{asset.id}:psa:9"].latest_raw_price_usd is None
assert by_key[f"{asset.id}:psa:10"].latest_price_usd == Decimal("700.00")
```

Add separate tests proving these rows cannot value PSA 10:

```text
market_segment=raw
market_segment=psa_9
market_segment=psa_10 with grade_company=BGS
market_segment=psa_10 with grade_score=9
market_segment=psa_10 from an inactive source
market_segment=psa_10 in a non-USD currency
```

- [ ] **Step 2: Write failing summary and image tests**

Set catalog metadata:

```python
asset.metadata_json = {
    "images": {
        "small": "https://images.example/moonbreon-small.png",
    }
}
```

Assert the position returns that `image_url`, missing metadata returns null, and:

```python
assert summary.unpriced_cost_basis == (
    summary.total_cost_basis - summary.priced_cost_basis
)
```

- [ ] **Step 3: Run valuation tests and confirm failure**

Run:

```powershell
python -m pytest tests/test_portfolio_service.py -k "price or valuation or image or summary" -q
```

Expected: positions still group by asset and the service reads Raw only.

- [ ] **Step 4: Replace the Raw-only price loader**

Replace `_latest_raw_prices()` with `_latest_position_prices()` returning:

```python
dict[tuple[UUID, str], _LatestPrice]
```

Build the finite set of required segments from identities. Query active-source
USD rows for the required asset IDs and segments in one window query. Apply:

```python
eligible_segment = or_(
    and_(
        PriceHistory.market_segment == "raw",
        PriceHistory.grade_company.is_(None),
        PriceHistory.grade_score.is_(None),
    ),
    *[
        and_(
            PriceHistory.market_segment == f"psa_{grade}",
            func.upper(PriceHistory.grade_company) == "PSA",
            PriceHistory.grade_score == str(grade),
        )
        for grade in sorted(required_psa_grades)
    ],
)
```

Rank by `(asset_id, market_segment)`, then `captured_at DESC, id DESC`. Keep
`get_active_price_source_filter(db)` and `currency == "USD"`.

- [ ] **Step 5: Group by complete identity**

Change:

```python
grouped_lots: dict[PortfolioIdentity, list[PortfolioLot]]
```

Use `PortfolioIdentity` for grouping and price lookup. Return:

```python
position_key=identity.position_key,
condition=identity.condition,
psa_grade=identity.psa_grade,
market_segment=identity.market_segment,
image_url=(asset.metadata_json or {}).get("images", {}).get("small"),
latest_price_usd=latest_price,
latest_raw_price_usd=(
    latest_price if identity.condition == "raw" else None
),
```

Calculate `unpriced_cost_basis` in both empty and populated summaries.

- [ ] **Step 6: Keep query counts bounded**

Extend the existing query-count test with Raw plus ten PSA identities for one
asset and assert the service still performs a constant number of SELECTs. The
allowed bound may increase only if the new identity count query is executed by
the read path; `get_portfolio()` itself should remain the existing lot query
plus one price query.

- [ ] **Step 7: Run all backend portfolio tests**

Run:

```powershell
python -m pytest tests/test_portfolio_identity.py tests/test_portfolio_migration.py tests/test_portfolio_schemas.py tests/test_portfolio_service.py tests/test_portfolio_api.py tests/test_portfolio_permissions.py -q
```

Expected: all selected tests pass.

- [ ] **Step 8: Commit valuation**

```powershell
git add backend/app/services/portfolio_service.py tests/test_portfolio_service.py
git commit -m "feat: value raw and psa portfolio positions exactly"
```

---

### Task 5: Preserve the HTTP Contract

**Files:**
- Modify: `tests/test_portfolio_api.py`
- Modify: `backend/app/api/routes/portfolio.py`

- [ ] **Step 1: Add failing API contract cases**

Extend the valid Raw payload test to omit condition and assert the service
receives:

```python
assert payload.condition == "raw"
assert payload.psa_grade is None
```

Add:

```python
PSA_PAYLOAD = {
    **VALID_PAYLOAD,
    "condition": "psa",
    "psa_grade": 10,
}

def test_post_accepts_psa_grade(client, service):
    response = client.post("/api/v1/portfolio/lots", json=PSA_PAYLOAD)
    assert response.status_code == 201
    payload = service.create_portfolio_lot.call_args.args[2]
    assert payload.condition == "psa"
    assert payload.psa_grade == 10
```

Add `422` cases for invalid combinations, and a patch case with:

```json
{"condition": "raw", "psa_grade": null}
```

- [ ] **Step 2: Run API tests and confirm failure**

Run:

```powershell
python -m pytest tests/test_portfolio_api.py -q
```

Expected: fixtures and response models do not yet include all new fields.

- [ ] **Step 3: Update route response fixtures and mappings**

Keep the same four route paths. Update `_lot_response()` and test fixtures to
include condition and grade through `PortfolioLotResponse.model_validate`.

Do not add a user ID, condition-specific route, or graded-price route. Existing
error mappings remain:

```text
401 unauthenticated
403 complete-identity position limit
404 missing or foreign lot
422 invalid condition/grade
```

- [ ] **Step 4: Run API and router tests**

Run:

```powershell
python -m pytest tests/test_portfolio_api.py tests/test_main.py -q
```

Expected: all selected tests pass and route registration remains unchanged.

- [ ] **Step 5: Commit API compatibility**

```powershell
git add backend/app/api/routes/portfolio.py tests/test_portfolio_api.py
git commit -m "feat: expose portfolio condition and grade"
```

---

### Task 6: Extend Frontend Types and Requests

**Files:**
- Modify: `frontend/src/types/portfolio.ts`
- Modify: `frontend/src/api/portfolio.test.ts`
- Modify: `frontend/src/api/portfolio.ts`

- [ ] **Step 1: Write failing API serialization tests**

Update create expectations:

```typescript
await createPortfolioLot({
  asset_id: 'asset-1',
  condition: 'psa',
  psa_grade: 10,
  quantity: 1,
  unit_cost_usd: '650.00',
  purchased_on: '2026-07-01',
})

expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
  asset_id: 'asset-1',
  condition: 'psa',
  psa_grade: 10,
  quantity: 1,
  unit_cost_usd: '650.00',
  purchased_on: '2026-07-01',
})
```

Add a patch expectation for:

```typescript
{ condition: 'raw', psa_grade: null }
```

- [ ] **Step 2: Run frontend API tests and confirm failure**

Run:

```powershell
cd frontend
npm test -- --run src/api/portfolio.test.ts
```

Expected: TypeScript rejects new fields.

- [ ] **Step 3: Extend frontend types**

In `frontend/src/types/portfolio.ts` add:

```typescript
export type PortfolioCondition = 'raw' | 'psa'
```

Add condition and grade to lot/input. Make `psa_grade` nullable. Add to position:

```typescript
position_key: string
condition: PortfolioCondition
psa_grade: number | null
market_segment: string
image_url: string | null
latest_price_usd: string | null
```

Keep `latest_raw_price_usd` temporarily. Add `unpriced_cost_basis` to summary.
Allow patch to include `condition` and `psa_grade`.

- [ ] **Step 4: Run API tests and type check**

Run:

```powershell
cd frontend
npm test -- --run src/api/portfolio.test.ts
npm run build
```

Expected: API tests and TypeScript build pass.

- [ ] **Step 5: Commit frontend contracts**

```powershell
git add frontend/src/types/portfolio.ts frontend/src/api/portfolio.ts frontend/src/api/portfolio.test.ts
git commit -m "feat: add raw and psa portfolio client contracts"
```

---

### Task 7: Add Condition Controls and Official Card Art

**Files:**
- Modify: `frontend/src/components/PortfolioLotDialog.test.tsx`
- Modify: `frontend/src/components/PortfolioLotDialog.tsx`
- Modify: `frontend/src/pages/PortfolioPage.tsx`
- Modify: `frontend/src/pages/PortfolioPage.test.tsx`
- Modify: `frontend/src/styles/theme.css`

- [ ] **Step 1: Write failing dialog interaction tests**

Add a card fixture with:

```typescript
image_url: 'https://images.example/moonbreon.png'
```

Assert:

```typescript
expect(screen.getByRole('img', { name: 'Moonbreon' })
  .getAttribute('src')).toBe(card.image_url)
expect(screen.getByRole('button', { name: 'Raw' })
  .getAttribute('aria-pressed')).toBe('true')
expect(screen.queryByLabelText('PSA grade')).toBeNull()

fireEvent.click(screen.getByRole('button', { name: 'PSA' }))
expect(screen.getByLabelText('PSA grade')).toBeTruthy()
fireEvent.change(screen.getByLabelText('PSA grade'), {
  target: { value: '10' },
})
fireEvent.click(screen.getByRole('button', { name: 'Save lot' }))

expect(onSubmit).toHaveBeenCalledWith({
  asset_id: card.asset_id,
  condition: 'psa',
  psa_grade: 10,
  quantity: 1,
  unit_cost_usd: '650.00',
  purchased_on: '2026-07-01',
})
```

Test switching back to Raw clears grade and submits `psa_grade: null`. Test edit
mode starts from its lot's exact condition and grade.

- [ ] **Step 2: Replace asset-only limit props**

Change create-dialog props from `positionAssetIds` to `positionKeys`. Add:

```typescript
function holdingKey(
  assetId: string,
  condition: PortfolioCondition,
  grade: number | null,
): string {
  return condition === 'raw'
    ? `${assetId}:raw`
    : `${assetId}:psa:${grade}`
}
```

At the Free limit, card search remains selectable. Disable submission only when
the chosen complete identity is absent from `positionKeys`. This lets a user
add another PSA 10 lot while correctly blocking a new PSA 9 position.

- [ ] **Step 3: Run dialog tests and confirm failure**

Run:

```powershell
cd frontend
npm test -- --run src/components/PortfolioLotDialog.test.tsx src/pages/PortfolioPage.test.tsx
```

Expected: the current dialog has no image or condition controls and uses
asset-only limit state.

- [ ] **Step 4: Implement the selected-card presentation**

Render the official image in a fixed container:

```tsx
<CardArt
  name={activePosition.name}
  imageUrl={'image_url' in activePosition ? activePosition.image_url : null}
  type={null}
  rarity={null}
  size="sm"
/>
```

Use the existing `CardArt` component rather than a raw `<img>` when its props
support the required fallback. Update position response types so edit mode also
has `image_url`.

- [ ] **Step 5: Implement Raw/PSA controls**

Use a two-button segmented control:

```tsx
<div className="portfolio-condition-control" aria-label="Card condition">
  {(['raw', 'psa'] as const).map(value => (
    <button
      key={value}
      type="button"
      aria-pressed={condition === value}
      onClick={() => {
        setCondition(value)
        setPsaGrade(value === 'raw' ? '' : (psaGrade || '10'))
      }}
    >
      {value === 'raw' ? 'Raw' : 'PSA'}
    </button>
  ))}
</div>
```

For PSA:

```tsx
<select
  id="portfolio-psa-grade"
  aria-label="PSA grade"
  value={psaGrade}
  onChange={event => setPsaGrade(event.target.value)}
>
  {Array.from({ length: 10 }, (_, index) => index + 1).map(grade => (
    <option key={grade} value={grade}>{grade}</option>
  ))}
</select>
```

Validate the grade before submission and serialize it as a number.

- [ ] **Step 6: Update page orchestration and copy**

Pass `portfolio.positions.map(position => position.position_key)` to the dialog.
Change raw-only copy such as "raw market value" to "exact market value" or
"Raw and PSA market value."

The create and edit mutation functions remain one request followed by one
portfolio refresh.

- [ ] **Step 7: Add stable responsive styles**

In `frontend/src/styles/theme.css`, add fixed image dimensions, an 8px-or-less
radius, segmented-control selected state, grade field spacing, and 320px mobile
rules. Do not introduce gradients, oversized headings, or nested cards.

- [ ] **Step 8: Run dialog and page tests**

Run:

```powershell
cd frontend
npm test -- --run src/components/PortfolioLotDialog.test.tsx src/pages/PortfolioPage.test.tsx
```

Expected: all selected tests pass.

- [ ] **Step 9: Commit the add/edit experience**

```powershell
git add frontend/src/components/PortfolioLotDialog.tsx frontend/src/components/PortfolioLotDialog.test.tsx frontend/src/pages/PortfolioPage.tsx frontend/src/pages/PortfolioPage.test.tsx frontend/src/styles/theme.css
git commit -m "feat: add raw and psa portfolio controls"
```

---

### Task 8: Render and Filter Exact Positions

**Files:**
- Modify: `frontend/src/components/PortfolioReadView.test.tsx`
- Modify: `frontend/src/components/PortfolioPositionTable.tsx`
- Modify: `frontend/src/components/PortfolioSummary.tsx`
- Modify: `frontend/src/styles/theme.css`

- [ ] **Step 1: Write failing position rendering tests**

Create Raw, PSA 9, and unpriced PSA 10 fixtures for the same asset. Assert:

```typescript
expect(screen.getByText('Raw')).toBeTruthy()
expect(screen.getByText('PSA 9')).toBeTruthy()
expect(screen.getByText('PSA 10')).toBeTruthy()
expect(screen.getByText('$300.00')).toBeTruthy()
expect(screen.getByText('Unpriced')).toBeTruthy()
expect(screen.queryByText('$0.00')).toBeNull()
expect(screen.getAllByRole('img', { name: 'Moonbreon' }).length).toBe(3)
expect(screen.getByText('Unpriced cost $650.00')).toBeTruthy()
```

Add filter tests:

```typescript
fireEvent.click(screen.getByRole('button', { name: 'PSA' }))
expect(screen.queryByText('Raw')).toBeNull()
expect(screen.getByText('PSA 9')).toBeTruthy()

fireEvent.change(screen.getByLabelText('PSA grade filter'), {
  target: { value: '10' },
})
expect(screen.queryByText('PSA 9')).toBeNull()
expect(screen.getByText('PSA 10')).toBeTruthy()
```

- [ ] **Step 2: Run read-view tests and confirm failure**

Run:

```powershell
cd frontend
npm test -- --run src/components/PortfolioReadView.test.tsx
```

Expected: table uses `latest_raw_price_usd`, has no image/holding label, and has
no filters.

- [ ] **Step 3: Render exact position fields**

Use `position.position_key` as the React key and expansion key. Render:

```tsx
<CardArt
  name={position.name}
  imageUrl={position.image_url}
  type={null}
  rarity={null}
  size="sm"
/>
<span className="portfolio-condition-badge">
  {position.condition === 'raw' ? 'Raw' : `PSA ${position.psa_grade}`}
</span>
```

Read price from `latest_price_usd`. Preserve the explicit `valuation_status`
branch so null never formats as zero.

- [ ] **Step 4: Add local condition and grade filters**

Keep filter state inside `PortfolioPositionTable`:

```typescript
const [conditionFilter, setConditionFilter] =
  useState<'all' | PortfolioCondition>('all')
const [gradeFilter, setGradeFilter] = useState<'all' | `${number}`>('all')
```

Use `All / Raw / PSA` segmented buttons. Show the grade menu only for PSA.
Filtering changes display only and does not refetch the portfolio.

- [ ] **Step 5: Show unpriced cost in the summary**

Add a concise detail under valuation coverage:

```tsx
<span>
  Unpriced cost {formatUsd(summary.unpriced_cost_basis)}
</span>
```

Keep total market value based only on priced positions.

- [ ] **Step 6: Run read-view and page tests**

Run:

```powershell
cd frontend
npm test -- --run src/components/PortfolioReadView.test.tsx src/pages/PortfolioPage.test.tsx
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit position rendering**

```powershell
git add frontend/src/components/PortfolioPositionTable.tsx frontend/src/components/PortfolioSummary.tsx frontend/src/components/PortfolioReadView.test.tsx frontend/src/styles/theme.css
git commit -m "feat: render exact raw and psa portfolio positions"
```

---

### Task 9: Verify Migration, Security, and Responsive Delivery

**Files:**
- Modify: `tests/test_portfolio_migration.py`
- Modify: `docs/flashcard-planet-v2/CODEX_EXECUTION_PLAN.md`

- [ ] **Step 1: Run the real PostgreSQL migration path**

Start a temporary PostgreSQL database and stamp or upgrade it to revision
`0044`. Insert at least two existing `portfolio_lots` rows, then run:

```powershell
python -m alembic upgrade 0045
```

Verify:

```sql
SELECT condition, psa_grade, COUNT(*)
FROM portfolio_lots
GROUP BY condition, psa_grade;
```

Expected: every pre-existing row is `raw`, null grade.

Attempt invalid inserts for Raw with grade and PSA without grade. Expected:
named check-constraint failures.

- [ ] **Step 2: Verify downgrade and re-upgrade**

Run:

```powershell
python -m alembic downgrade 0044
python -m alembic upgrade 0045
```

Expected: both commands succeed and the `0045` schema returns exactly once.
Do not downgrade a production database containing PSA lots.

- [ ] **Step 3: Run backend verification**

Run:

```powershell
python -m pytest tests/test_portfolio_identity.py tests/test_portfolio_migration.py tests/test_portfolio_schemas.py tests/test_portfolio_service.py tests/test_portfolio_api.py tests/test_portfolio_permissions.py -q
python -m pytest -q
```

Expected: scoped and full backend suites pass.

- [ ] **Step 4: Run frontend verification**

Run:

```powershell
cd frontend
npm test -- --run
npm run build
npx eslint src/types/portfolio.ts src/api/portfolio.ts src/api/portfolio.test.ts src/components/PortfolioLotDialog.tsx src/components/PortfolioLotDialog.test.tsx src/components/PortfolioPositionTable.tsx src/components/PortfolioReadView.test.tsx src/components/PortfolioSummary.tsx src/pages/PortfolioPage.tsx src/pages/PortfolioPage.test.tsx
```

Expected: all frontend tests pass, build succeeds, and scoped lint has no
errors.

- [ ] **Step 5: Run browser acceptance**

Use the real FastAPI API with representative Raw, priced PSA 9, and unpriced
PSA 10 positions. Capture and inspect:

```text
1440x900
1024x768
390x844
320x568
```

Verify:

- Official images load or use the existing fallback.
- Raw, PSA 9, and PSA 10 are independent.
- PSA controls work by keyboard.
- Grade menu appears only for PSA.
- Filters do not resize the layout unexpectedly.
- Unpriced PSA never shows `$0`.
- Dialog focus trap, Escape, scroll lock, and validation remain correct.
- No page-level horizontal overflow exists.

- [ ] **Step 6: Run the security regression scan**

Run:

```powershell
rg -n "user_id.*PortfolioLot(Create|Patch)|latest_raw_price_usd.*psa|market_segment == \"raw\"" backend/app/schemas/portfolio.py backend/app/services/portfolio_service.py backend/app/api/routes/portfolio.py
```

Expected:

- No request schema accepts `user_id`.
- PSA response population never uses the compatibility Raw field.
- The new exact valuation path is not hard-coded to Raw only.

- [ ] **Step 7: Record delivery**

Update `docs/flashcard-planet-v2/CODEX_EXECUTION_PLAN.md` with:

```text
Portfolio Raw + PSA: delivered
- Existing lots backfilled to Raw
- PSA grades 1-10 tracked as independent identities
- Exact accepted-segment valuation only
- Official catalog images and responsive filters
- Scoped/full test, migration, build, lint, and browser evidence
```

Include actual pass counts, migration environment, and screenshot paths.

- [ ] **Step 8: Commit verification records**

```powershell
git add tests/test_portfolio_migration.py docs/flashcard-planet-v2/CODEX_EXECUTION_PLAN.md
git commit -m "docs: record raw and psa portfolio delivery"
```

---

## Completion Gate

Do not start
`docs/superpowers/plans/2026-07-26-portfolio-private-photos.md` until all nine
tasks above pass and Raw/PSA behavior is reviewable as working software.

