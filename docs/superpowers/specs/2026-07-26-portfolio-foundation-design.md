# Portfolio Foundation Design

**Date:** 2026-07-26

**Status:** Approved

**Phase:** Flashcard Planet v2, Phase 6 Portfolio Intelligence

---

## 1. Context

Flashcard Planet now has a market overview, persisted Daily Market Reports,
Catalysts, evidence-linked AI commentary, authentication, tier permissions,
watchlists, and raw market price history. It does not have a durable record of
what a user owns or paid.

The Product Bible identifies Portfolio and Decision Center surfaces as the next
development sequence. Decision support requires a reliable portfolio cost and
valuation foundation first.

## 2. Goals

1. Let an authenticated user record individual raw-card purchase lots.
2. Group lots into positions while retaining each purchase price and date.
3. Calculate deterministic cost basis, current raw market value, and unrealized
   profit or loss.
4. Show valuation coverage and avoid implying that unpriced positions have a
   market value.
5. Show market-value allocation by game.
6. Give Free users up to 10 distinct positions and Plus/Pro users unlimited
   positions.
7. Provide a focused desktop and mobile Portfolio workflow.

## 3. Non-Goals

- Graded, sealed, or manually valued holdings
- Buy, sell, hold, avoid, or rebalance recommendations
- AI commentary or price predictions
- Realized profit and loss
- Sales, disposals, transfers, fees, taxes, or dividends
- Multi-currency cost basis or foreign-exchange conversion
- Portfolio sharing, public profiles, CSV import, or CSV export
- Historical portfolio-value charts
- Scheduled valuation snapshots
- Reusing Watchlist rows as portfolio ownership records

## 4. Product Decisions

### 4.1 Purchase Lots

Every purchase is stored as an independent lot. A position is a read model that
groups all of the current user's lots by `asset_id`.

This preserves:

- Different purchase dates
- Different unit costs
- Accurate total cost basis
- A future path to lot-level disposals without changing the initial model

### 4.2 Raw-Only Valuation

Portfolio v1 values positions only from the latest accepted
`price_history.market_segment = 'raw'` observation from the currently active
price source.

The service must not:

- Fall back to graded observations
- Use another market segment
- Invent or interpolate a missing price
- Treat purchase cost as current market value

### 4.3 Access Tiers

- Free: 10 distinct positions
- Plus: unlimited positions
- Pro: unlimited positions

Additional lots for an existing asset do not consume another position.

## 5. Data Model

Migration `0044` creates `portfolio_lots`.

| Column | Type | Null | Rule |
|---|---|---:|---|
| `id` | UUID | No | Primary key |
| `user_id` | UUID | No | FK to `users.id`, delete cascade |
| `asset_id` | UUID | No | FK to `assets.id` |
| `quantity` | Integer | No | Greater than zero |
| `unit_cost_usd` | Numeric(12,2) | No | Greater than or equal to zero |
| `purchased_on` | Date | No | User-supplied purchase date |
| `created_at` | Timestamptz | No | Server timestamp |
| `updated_at` | Timestamptz | No | Server timestamp, updated on change |

Database constraints:

- `ck_portfolio_lots_quantity_positive`
- `ck_portfolio_lots_unit_cost_non_negative`

Indexes:

- `(user_id, asset_id)` for grouping and position-limit checks
- `(user_id, purchased_on DESC)` for user history reads

There is intentionally no unique constraint on `(user_id, asset_id)`.

## 6. Permission Model

Add:

```python
Feature.PORTFOLIO_UNLIMITED
FREE_PORTFOLIO_POSITION_LIMIT = 10
```

`PORTFOLIO_UNLIMITED` requires Plus. Pro inherits Plus capabilities.

The service exposes:

```python
portfolio_position_limit(access_tier: str) -> int | None
```

When creating the first lot for an asset:

1. Lock the current `users` row with `FOR UPDATE`.
2. Resolve the effective tier from subscription and access fields.
3. Count distinct portfolio `asset_id` values for the user.
4. Reject the create with a typed tier-limit error when the Free limit is
   already reached.
5. Allow more lots for an asset already in the portfolio.

## 7. Valuation Model

The service loads all positions and their latest eligible prices in bounded
queries. It must not issue one price query per position.

For every position:

```text
quantity = sum(lot.quantity)
cost_basis = sum(lot.quantity * lot.unit_cost_usd)
market_value = quantity * latest_raw_price, when a price exists
unrealized_pnl = market_value - cost_basis, when a price exists
unrealized_pnl_percent = unrealized_pnl / cost_basis * 100,
                         when price exists and cost_basis > 0
```

For the portfolio summary:

```text
total_cost_basis = cost basis of every position
priced_cost_basis = cost basis of priced positions only
total_market_value = market value of priced positions only
unrealized_pnl = total_market_value - priced_cost_basis
valuation_coverage = priced position count / total position count
```

`total_market_value` must never silently include unpriced positions.

Each allocation row contains:

- Game
- Priced market value
- Percentage of total priced market value
- Priced position count

Unpriced position count is returned separately.

## 8. API Design

All routes use `get_current_user`. Request bodies and paths never accept a user
identifier.

### 8.1 Read Portfolio

```http
GET /api/v1/portfolio
```

Response:

```json
{
  "summary": {
    "total_cost_basis": "1250.00",
    "priced_cost_basis": "1000.00",
    "total_market_value": "1375.00",
    "unrealized_pnl": "375.00",
    "unrealized_pnl_percent": "37.50",
    "position_count": 3,
    "priced_position_count": 2,
    "unpriced_position_count": 1,
    "valuation_coverage_percent": "66.67",
    "position_limit": 10
  },
  "allocations": [],
  "positions": []
}
```

Each position includes card identity, game, aggregate metrics, latest price
timestamp, valuation state, and its ordered lots.

### 8.2 Create Lot

```http
POST /api/v1/portfolio/lots
```

Request:

```json
{
  "asset_id": "uuid",
  "quantity": 2,
  "unit_cost_usd": "125.00",
  "purchased_on": "2026-07-01"
}
```

Returns the created lot with HTTP 201.

### 8.3 Update Lot

```http
PATCH /api/v1/portfolio/lots/{lot_id}
```

The patch accepts quantity, unit cost, and purchase date. At least one field is
required. Asset identity cannot be changed; a mistaken asset is handled by
deleting the lot and creating the correct one.

### 8.4 Delete Lot

```http
DELETE /api/v1/portfolio/lots/{lot_id}
```

Returns HTTP 204. Deleting the final lot removes the position from the read
model.

## 9. API Errors

- `401`: user is not authenticated
- `403`: Free distinct-position limit reached, with upgrade URL
- `404`: asset or user-owned lot does not exist
- `422`: quantity, cost, date, UUID, or empty patch is invalid

A lot belonging to another user returns `404`, not `403`, to avoid exposing its
existence.

## 10. Frontend Experience

Add `/portfolio` and a primary navigation item.

The page is an operational workspace, not a marketing page.

### 10.1 Summary

A compact summary strip shows:

- Total cost
- Current value
- Unrealized P&L
- Valuation coverage

Positive and negative P&L use accessible color plus sign and label, not color
alone.

### 10.2 Allocation

Show a horizontal allocation band and a compact legend by game. Percentages are
based only on priced market value. Unpriced positions are called out beside the
coverage metric.

### 10.3 Positions

The main table shows:

- Card
- Game
- Total quantity
- Average unit cost
- Latest raw price
- Cost basis
- Market value
- Unrealized P&L

Rows expand to show lots ordered by purchase date descending. Lot actions use
icon buttons with tooltips.

### 10.4 Add and Edit

The add flow uses the existing card search API, then collects quantity, USD unit
cost, and purchase date.

Free users see their distinct-position usage. At the limit:

- Adding a lot to an existing position remains available.
- Selecting a new asset explains the limit and offers the existing upgrade
  route.

### 10.5 States

- Unauthenticated: sign-in state
- Loading: stable skeleton dimensions
- Empty: focused add-first-position action
- Partial valuation: normal table plus explicit coverage warning
- API failure: retry action without clearing previously loaded data

## 11. Component Boundaries

Backend:

- `PortfolioLot` model owns persistence only.
- Portfolio schemas own API contracts and decimal serialization.
- Portfolio service owns authorization-scoped CRUD, tier limits, grouping, and
  valuation.
- Portfolio routes own transaction boundaries and HTTP error mapping.

Frontend:

- API module owns network requests.
- Portfolio page owns loading and mutation orchestration.
- Position table owns grouped display and expansion.
- Lot dialog owns validated form state.
- Allocation component owns the allocation band and legend.

## 12. Security and Privacy

- Every route requires authentication.
- Every lot read, update, and delete includes `user_id = current_user.id`.
- Public market endpoints do not expose portfolio data.
- Logs must not contain cost basis or full portfolio payloads.
- No public sharing token or user lookup route is introduced.

## 13. Testing Strategy

Backend:

- Migration upgrade, downgrade, indexes, FKs, and check constraints
- Free distinct-position limit
- Same-asset additional lot at the Free limit
- Plus and Pro unlimited behavior
- Concurrent create serialization through the user lock
- User ownership isolation
- Create, patch, delete, and empty-patch validation
- Multi-lot aggregation
- Latest raw active-source price selection
- Rejection of graded/non-raw prices
- Missing-price coverage behavior
- Zero-cost P&L percentage behavior
- Game allocation totals and deterministic ordering
- Authentication and API error mapping

Frontend:

- Authenticated load
- Unauthenticated state
- Empty and partial-valuation states
- Add, edit, and delete lot workflows
- Free position limit behavior
- Position expansion
- Allocation rendering
- API failure and stale-request behavior
- Desktop and mobile overflow checks

## 14. Rollout

- One migration and one feature PR
- No data backfill
- No scheduler
- No provider or AI call
- No production portfolio is created automatically

## 15. Acceptance Criteria

- Authenticated users can manage purchase lots without specifying a user ID.
- Multiple lots for one asset aggregate into one position.
- Free users cannot exceed 10 distinct positions.
- Plus and Pro users have no position limit.
- Valuation uses only the latest eligible raw price.
- Missing prices remain explicit and do not distort P&L.
- Another user's lot cannot be observed or mutated.
- Backend, frontend, migration, and responsive browser tests pass.
- The existing Market, Daily Report, Watchlist, Alerts, and account workflows
  remain unchanged.
