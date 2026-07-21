# Catalyst Engine Vertical Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the first evidence-backed Catalyst Engine across the existing market-event registry, public market APIs, immutable Daily Market Report snapshots, and the Dashboard.

**Architecture:** Extend `market_events` as the single catalyst source of truth, compute lifecycle state at read time, and expose verified read-only catalyst responses through the existing market router. Reuse the same typed catalyst contract for report snapshots and the frontend, while limiting deterministic driver attribution to the existing mappings plus `REPRINT -> SUPPLY_SHOCK`.

**Tech Stack:** PostgreSQL JSONB, Alembic, SQLAlchemy 2, Pydantic v2, FastAPI, pytest, React 19, TypeScript 6, Vitest, Testing Library, Vite.

---

### Task 1: Catalyst Persistence And Curated Write Validation

**Files:**
- Create: `migrations/versions/0042_add_catalyst_engine_fields.py`
- Modify: `backend/app/models/predictions.py`
- Modify: `backend/app/models/daily_market_report.py`
- Modify: `backend/app/services/market_event_service.py`
- Create: `tests/test_market_event_service.py`

- [x] **Step 1: Write failing curated-write tests**

Cover a valid event and each rejected boundary:

```python
VALID_EVENT = MarketEventCreate(
    event_date=datetime(2026, 7, 24, tzinfo=UTC),
    event_type="REPRINT",
    description="Verified regional reprint announcement.",
    source_url="https://www.pokemon.com/example",
    verified_at=datetime(2026, 7, 22, tzinfo=UTC),
    verified_by="market-ops",
    affected_games=["pokemon"],
    affected_asset_ids=[],
    affected_set_ids=["sv08"],
    expected_window_days=21,
    impact_score=78,
    confidence_score=Decimal("91.50"),
)
```

Assert the service persists every field. Parametrize invalid event types, empty games, impact scores outside `0..100`, confidence scores outside `0..100`, non-HTTP(S) source URLs, and missing `verified_at`.

- [x] **Step 2: Run the service test and verify RED**

Run: `python -m pytest tests/test_market_event_service.py -q`

Expected: the new dataclass fields and validation rules are missing.

- [x] **Step 3: Add migration `0042`**

Add the following columns and constraints:

```python
op.add_column("market_events", sa.Column("affected_games", postgresql.JSONB(), nullable=True))
op.add_column("market_events", sa.Column("impact_score", sa.Integer(), nullable=True))
op.add_column("market_events", sa.Column("confidence_score", sa.Numeric(5, 2), nullable=True))
op.add_column(
    "daily_market_reports",
    sa.Column(
        "catalysts_json",
        postgresql.JSONB(),
        nullable=False,
        server_default=sa.text("'[]'::jsonb"),
    ),
)
op.execute("UPDATE market_events SET affected_games = '[\"pokemon\"]'::jsonb WHERE affected_games IS NULL")
op.alter_column("market_events", "affected_games", nullable=False)
op.create_check_constraint(
    "ck_market_events_affected_games_nonempty",
    "market_events",
    "jsonb_typeof(affected_games) = 'array' AND jsonb_array_length(affected_games) > 0",
)
op.create_check_constraint(
    "ck_market_events_impact_score_range",
    "market_events",
    "impact_score IS NULL OR impact_score BETWEEN 0 AND 100",
)
op.create_check_constraint(
    "ck_market_events_confidence_score_range",
    "market_events",
    "confidence_score IS NULL OR confidence_score BETWEEN 0 AND 100",
)
```

The downgrade must remove the report snapshot column, all three constraints, and all three event columns in reverse dependency order.

- [x] **Step 4: Extend both ORM models**

Add non-null `affected_games` with `default=list`, nullable scores, and non-null `catalysts_json` with `default=list`. Do not use a mutable literal as a Python default.

- [x] **Step 5: Implement canonical write validation**

Define one exported immutable event-type set:

```python
CATALYST_EVENT_TYPES = frozenset({
    "INFLUENCER", "SUPPLY", "TOURNAMENT", "RELEASE", "REPRINT",
    "PRICE_CHANGE", "ANNIVERSARY", "COLLABORATION", "LIMITED_PRODUCT",
    "POLICY", "SOCIAL_TREND",
})
```

Extend `MarketEventCreate` with `affected_games`, `impact_score`, and `confidence_score`. Normalize event type and game identifiers to lowercase/uppercase at the service boundary, validate the URL with `urllib.parse.urlparse`, and preserve `None` scores as unscored rather than converting them to zero.

- [x] **Step 6: Run focused persistence tests and verify GREEN**

Run: `python -m pytest tests/test_market_event_service.py tests/test_driver_attribution_service.py tests/test_fundamental_signal_service.py -q`

Expected: all tests pass after existing direct `MarketEvent` fixtures include `affected_games=["pokemon"]`.

- [x] **Step 7: Commit the persistence slice**

```text
git add migrations/versions/0042_add_catalyst_engine_fields.py backend/app/models/predictions.py backend/app/models/daily_market_report.py backend/app/services/market_event_service.py tests/test_market_event_service.py tests/test_driver_attribution_service.py tests/test_fundamental_signal_service.py
git commit -m "feat: extend market events for catalysts"
```

### Task 2: Catalyst Lifecycle, Filtering, And Response Contract

**Files:**
- Create: `backend/app/schemas/catalyst.py`
- Create: `backend/app/services/catalyst_service.py`
- Create: `tests/test_catalyst_service.py`

- [x] **Step 1: Write failing lifecycle and listing tests**

Use a fixed `as_of=datetime(2026, 7, 22, 12, tzinfo=UTC)` and cover:

```python
assert catalyst_lifecycle(future_event, as_of=as_of) == "upcoming"
assert catalyst_lifecycle(current_event, as_of=as_of) == "active"
assert catalyst_lifecycle(old_event, as_of=as_of) == "expired"
```

Also verify the default 14-day active window, an explicit `expected_window_days`, selected-game plus `global` matching, repeatable status filtering, event-type filtering, pagination totals, score ordering with nulls last, and omission of `verified_by` from public responses.

- [x] **Step 2: Run the service test and verify RED**

Run: `python -m pytest tests/test_catalyst_service.py -q`

Expected: catalyst schemas and service functions do not exist.

- [x] **Step 3: Define the public schemas**

Create these contracts:

```python
CatalystLifecycle = Literal["upcoming", "active", "expired"]
ImpactLabel = Literal["high", "medium", "low", "unscored"]
ConfidenceLabel = Literal["high", "medium", "low", "insufficient_data"]

class CatalystResponse(BaseModel):
    id: UUID
    event_date: datetime
    active_until: datetime
    event_type: str
    description: str
    source_url: str
    affected_games: list[str]
    affected_asset_ids: list[str]
    affected_set_ids: list[str]
    expected_window_days: int | None
    impact_score: int | None
    impact_label: ImpactLabel
    confidence_score: Decimal | None
    confidence_label: ConfidenceLabel
    status: CatalystLifecycle
    verified_at: datetime

class CatalystListResponse(BaseModel):
    catalysts: list[CatalystResponse]
    total: int
    limit: int
    offset: int
    as_of: datetime
```

Do not add `verified_by` to either public schema.

- [x] **Step 4: Implement lifecycle and read service**

Implement:

```python
def catalyst_lifecycle(event: MarketEvent, *, as_of: datetime) -> CatalystLifecycle:
    window_days = event.expected_window_days if event.expected_window_days is not None else 14
    if event.event_date > as_of:
        return "upcoming"
    if as_of <= event.event_date + timedelta(days=window_days):
        return "active"
    return "expired"
```

Add `list_catalysts(...)`, `get_catalyst(...)`, score-label helpers, and a shared row-to-response mapper. Query only verified rows, normalize `as_of` to UTC, filter the small curated registry in service code for JSON-array and computed-status compatibility, then paginate after filtering. Order active by impact descending then event date descending, upcoming by event date ascending then impact descending, and expired by event date descending then impact descending. Null impact scores sort after scored rows within each lifecycle group; retain a deterministic ID tie-breaker.

- [x] **Step 5: Run the service test and verify GREEN**

Run: `python -m pytest tests/test_catalyst_service.py -q`

Expected: lifecycle, filtering, ordering, pagination, and public privacy tests pass.

- [x] **Step 6: Commit the catalyst read service**

```text
git add backend/app/schemas/catalyst.py backend/app/services/catalyst_service.py tests/test_catalyst_service.py
git commit -m "feat: add catalyst lifecycle service"
```

### Task 3: Read-Only Catalyst Market API

**Files:**
- Modify: `backend/app/api/routes/market.py`
- Create: `tests/test_catalyst_api.py`

- [x] **Step 1: Write failing route tests**

Test:

```text
GET /api/v1/market/catalysts?status=active&status=upcoming&game=pokemon&event_type=REPRINT&limit=3&offset=0
GET /api/v1/market/catalysts/{catalyst_id}
```

Assert query values reach the service unchanged after event-type normalization, unknown IDs return `404`, and invalid `limit=0`, `limit=101`, or `offset=-1` return `422`.

- [x] **Step 2: Run the API test and verify RED**

Run: `python -m pytest tests/test_catalyst_api.py -q`

Expected: both endpoints return `404` because they are not registered.

- [x] **Step 3: Register list and detail endpoints**

Add routes under the existing `/market` router:

```python
@router.get("/catalysts", response_model=CatalystListResponse)
def catalyst_index(
    status: list[CatalystLifecycle] | None = Query(None),
    game: str | None = Query(None),
    event_type: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_database),
) -> CatalystListResponse:
    return list_catalysts(
        db,
        statuses=status,
        game=game,
        event_type=event_type,
        limit=limit,
        offset=offset,
    )
```

The detail route returns the same `CatalystResponse` contract and raises `HTTPException(404, "Catalyst not found.")` when absent. No create, update, or delete endpoint is permitted in this slice.

- [x] **Step 4: Run API and service tests and verify GREEN**

Run: `python -m pytest tests/test_catalyst_api.py tests/test_catalyst_service.py -q`

Expected: all catalyst backend read tests pass.

- [x] **Step 5: Commit the public API**

```text
git add backend/app/api/routes/market.py tests/test_catalyst_api.py
git commit -m "feat: expose verified market catalysts"
```

### Task 4: Deterministic REPRINT Driver Attribution

**Files:**
- Modify: `backend/app/services/driver_attribution_service.py`
- Modify: `tests/test_driver_attribution_service.py`

- [x] **Step 1: Write failing attribution tests**

Create a verified `REPRINT` event that targets the test asset/set and assert:

```python
assert result.driver_type == "SUPPLY_SHOCK"
assert result.event_type == "REPRINT"
```

Add a negative test proving `PRICE_CHANGE`, `ANNIVERSARY`, `COLLABORATION`, `LIMITED_PRODUCT`, `POLICY`, and `SOCIAL_TREND` do not silently create causal attribution.

- [x] **Step 2: Run the attribution test and verify RED**

Run: `python -m pytest tests/test_driver_attribution_service.py -q`

Expected: `REPRINT` is not mapped or included in the supply event query.

- [x] **Step 3: Add the narrow attribution mapping**

Add only:

```python
EVENT_TYPE_TO_DRIVER["REPRINT"] = "SUPPLY_SHOCK"
EVENT_TYPE_WEIGHTS["REPRINT"] = EVENT_TYPE_WEIGHTS["SUPPLY"]
```

Change supply-specific matching from `event_types=["SUPPLY"]` to `event_types=["SUPPLY", "REPRINT"]`. Keep every existing mapping unchanged and do not add mappings for the other new display-only event types.

- [x] **Step 4: Run attribution regression tests and verify GREEN**

Run: `python -m pytest tests/test_driver_attribution_service.py tests/test_fundamental_signal_service.py -q`

Expected: existing attribution remains stable and REPRINT is attributed as a supply shock.

- [x] **Step 5: Commit the attribution change**

```text
git add backend/app/services/driver_attribution_service.py tests/test_driver_attribution_service.py
git commit -m "feat: attribute verified reprints"
```

### Task 5: Immutable Daily Report Catalyst Snapshots

**Files:**
- Modify: `backend/app/schemas/daily_market_report.py`
- Modify: `backend/app/services/catalyst_service.py`
- Modify: `backend/app/services/daily_market_report_service.py`
- Modify: `tests/test_daily_market_report_service.py`
- Modify: `tests/test_daily_market_report_api.py`

- [x] **Step 1: Write failing report snapshot tests**

Cover these behaviors:

- Generation captures at most five verified catalysts.
- Selection includes active catalysts plus upcoming catalysts within 30 days.
- Expired and farther-future catalysts are excluded.
- Ordering is inherited from the catalyst service.
- A report with no catalysts stores and returns `[]`.
- Changing a source event after publication does not change a previously returned stored snapshot.
- An exception during catalyst selection aborts before `db.commit()` and does not publish a partial report.

- [x] **Step 2: Run report tests and verify RED**

Run: `python -m pytest tests/test_daily_market_report_service.py tests/test_daily_market_report_api.py -q`

Expected: the report contract has no catalysts and generation does not select them.

- [x] **Step 3: Add a report-selection helper**

In `catalyst_service.py`, implement:

```python
def select_daily_report_catalysts(
    db: Session,
    *,
    as_of: datetime,
    limit: int = 5,
) -> list[CatalystResponse]:
    page = list_catalysts(
        db,
        statuses=["active", "upcoming"],
        limit=100,
        offset=0,
        as_of=as_of,
    )
    horizon = as_of + timedelta(days=30)
    eligible = [
        item for item in page.catalysts
        if item.status == "active" or item.event_date <= horizon
    ]
    return eligible[:limit]
```

- [x] **Step 4: Persist and return typed snapshots**

Add `catalysts: list[CatalystResponse]` to `DailyMarketReportResponse`. During generation, select catalysts before mutating/publishing the report row, serialize with `model_dump(mode="json")`, and assign `row.catalysts_json`. In `_response_from_row`, validate stored entries with `CatalystResponse.model_validate` and never re-query live events.

Update API fixtures to include `catalysts=[]`. Preserve the existing report date and overview behavior.

- [x] **Step 5: Run Daily Report regressions and verify GREEN**

Run:

```text
python -m pytest tests/test_daily_market_report_service.py tests/test_daily_market_report_api.py tests/test_daily_market_report_scheduler.py -q
```

Expected: persisted catalyst snapshots, API serialization, empty behavior, and scheduler generation all pass.

- [x] **Step 6: Commit report integration**

```text
git add backend/app/schemas/daily_market_report.py backend/app/services/catalyst_service.py backend/app/services/daily_market_report_service.py tests/test_daily_market_report_service.py tests/test_daily_market_report_api.py
git commit -m "feat: snapshot catalysts in daily reports"
```

### Task 6: Typed Frontend Catalyst Client

**Files:**
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/api/api.ts`
- Modify: `frontend/src/api/api.test.ts`
- Modify: `frontend/src/pages/DashboardPage.test.tsx`
- Modify: `frontend/src/pages/DailyReportsPage.test.tsx`
- Modify: `frontend/src/pages/DailyReportDetailPage.test.tsx`

- [x] **Step 1: Write failing client tests**

Assert the client requests repeated status parameters and all filters:

```ts
await fetchCatalysts({
  status: ['active', 'upcoming'],
  game: 'pokemon',
  eventType: 'REPRINT',
  limit: 3,
  offset: 0,
})
```

The expected URL contains `status=active&status=upcoming`, and `fetchCatalyst(id)` maps `404` to `null` while throwing for other errors.

- [x] **Step 2: Run client tests and verify RED**

Run from `frontend/`: `npm test -- src/api/api.test.ts`

Expected: catalyst types and client functions are missing.

- [x] **Step 3: Add shared TypeScript contracts**

Add:

```ts
export type CatalystStatus = 'upcoming' | 'active' | 'expired'

export interface Catalyst {
  id: string
  event_date: string
  active_until: string
  event_type: string
  description: string
  source_url: string
  affected_games: string[]
  affected_asset_ids: string[]
  affected_set_ids: string[]
  expected_window_days: number | null
  impact_score: number | null
  impact_label: 'high' | 'medium' | 'low' | 'unscored'
  confidence_score: MarketNumber | null
  confidence_label: 'high' | 'medium' | 'low' | 'insufficient_data'
  status: CatalystStatus
  verified_at: string
}

export interface CatalystListResponse {
  catalysts: Catalyst[]
  total: number
  limit: number
  offset: number
  as_of: string
}
```

Extend `DailyMarketReport` with `catalysts: Catalyst[]`.

Add `catalysts: []` to existing typed Daily Report test fixtures so the required contract does not leave the TypeScript build broken before the report-detail UI task.

- [x] **Step 4: Implement the list and detail clients**

Use `URLSearchParams.append` for repeatable statuses, uppercase `eventType` only at the outgoing API boundary, and URL-encode the detail ID. Preserve null scores without numeric coercion.

- [x] **Step 5: Run client tests and verify GREEN**

Run from `frontend/`: `npm test -- src/api/api.test.ts`

Expected: all API client tests pass.

- [x] **Step 6: Commit the frontend contract**

```text
git add frontend/src/types/api.ts frontend/src/api/api.ts frontend/src/api/api.test.ts
git commit -m "feat: add catalyst frontend client"
```

### Task 7: Dashboard Market Catalysts Panel

**Files:**
- Create: `frontend/src/components/MarketCatalystsPanel.tsx`
- Create: `frontend/src/components/__tests__/MarketCatalystsPanel.test.tsx`
- Modify: `frontend/src/pages/DashboardPage.tsx`
- Modify: `frontend/src/pages/DashboardPage.test.tsx`
- Modify: `frontend/src/styles/theme.css`

- [x] **Step 1: Write failing focused component tests**

Cover stable loading, request error, empty state, populated active/upcoming rows, null score labels, source links, and safe formatting for unknown event types. Expected copy:

```text
Market Catalysts
No verified catalysts are active or upcoming for this market.
Impact: Unscored
Confidence: Insufficient evidence
```

- [x] **Step 2: Run the component test and verify RED**

Run from `frontend/`: `npm test -- src/components/__tests__/MarketCatalystsPanel.test.tsx`

Expected: the focused component module is missing.

- [x] **Step 3: Implement the focused presentational component**

Give the component this explicit prop contract:

```ts
interface MarketCatalystsPanelProps {
  catalysts: Catalyst[] | undefined
  unavailable: boolean
}
```

Render a compact full-width market band with at most three rows. Each row shows lifecycle, event type, date, description, impact, confidence, and an external evidence link with `rel="noreferrer"`. Do not add investment recommendations, causal wording, or a nested card layout.

- [x] **Step 4: Write failing Dashboard integration tests**

Mock `fetchCatalysts`, assert the initial call uses:

```ts
{
  status: ['active', 'upcoming'],
  game: 'pokemon',
  limit: 3,
  offset: 0,
}
```

Switch to Yu-Gi-Oh and assert a new request uses `game: 'yugioh'`. Verify catalyst failure does not hide the Daily Report, Market Overview, or card grid.

- [x] **Step 5: Run the Dashboard test and verify RED**

Run from `frontend/`: `npm test -- src/pages/DashboardPage.test.tsx`

Expected: the Dashboard neither fetches nor renders catalysts.

- [x] **Step 6: Integrate independent catalyst state**

Add catalyst data and unavailable state to `DashboardPage`. Fetch when `activeGame` changes, protect against stale responses with an `active` cleanup flag, and render `MarketCatalystsPanel` after Market Overview. The request must not share loading/error state with cards or other market panels.

- [x] **Step 7: Style and verify the Dashboard panel**

Use existing theme variables, radius at or below 8px, stable grid tracks, visible focus styles, and responsive rows that stack without horizontal overflow below 720px.

Run from `frontend/`:

```text
npm test -- src/components/__tests__/MarketCatalystsPanel.test.tsx src/pages/DashboardPage.test.tsx
```

Expected: component and integration tests pass.

- [x] **Step 8: Commit the Dashboard slice**

```text
git add frontend/src/components/MarketCatalystsPanel.tsx frontend/src/components/__tests__/MarketCatalystsPanel.test.tsx frontend/src/pages/DashboardPage.tsx frontend/src/pages/DashboardPage.test.tsx frontend/src/styles/theme.css
git commit -m "feat: show catalysts on dashboard"
```

### Task 8: Daily Report Catalyst Section

**Files:**
- Modify: `frontend/src/pages/DailyReportDetailPage.tsx`
- Modify: `frontend/src/pages/DailyReportDetailPage.test.tsx`
- Modify: `frontend/src/pages/DailyReportsPage.test.tsx`
- Modify: `frontend/src/pages/DashboardPage.test.tsx`
- Modify: `frontend/src/styles/theme.css`

- [x] **Step 1: Update all report fixtures and write failing detail tests**

Add `catalysts: []` to every `DailyMarketReport` fixture. In the detail-page suite, verify the new section appears after Evidence and before Market Indexes, renders persisted catalyst data, handles null scores, and uses this exact empty label:

```text
No verified catalysts were captured for this report.
```

- [x] **Step 2: Run affected page tests and verify RED**

Run from `frontend/`:

```text
npm test -- src/pages/DailyReportDetailPage.test.tsx src/pages/DailyReportsPage.test.tsx src/pages/DashboardPage.test.tsx
```

Expected: fixtures fail the extended type contract and the detail section is absent.

- [x] **Step 3: Render the immutable report snapshot**

Add a `Market Catalysts` section immediately after Evidence. Render from `report.catalysts`; do not call the live catalyst endpoint from the report page. Reuse small formatting helpers from the Dashboard component only if moving them to a shared utility removes real duplication without coupling page state.

- [x] **Step 4: Style and verify the report section**

Keep the section unframed, align its density with existing report tables, permit descriptions to wrap, and keep source links keyboard-accessible.

Run from `frontend/`:

```text
npm test -- src/pages/DailyReportDetailPage.test.tsx src/pages/DailyReportsPage.test.tsx src/pages/DashboardPage.test.tsx
```

Expected: all affected page tests pass.

- [x] **Step 5: Commit the report UI**

```text
git add frontend/src/pages/DailyReportDetailPage.tsx frontend/src/pages/DailyReportDetailPage.test.tsx frontend/src/pages/DailyReportsPage.test.tsx frontend/src/pages/DashboardPage.test.tsx frontend/src/styles/theme.css
git commit -m "feat: show catalysts in daily reports"
```

### Task 9: Full Verification, Visual QA, And Delivery

**Files:**
- Modify: `docs/flashcard-planet-v2/CODEX_EXECUTION_PLAN.md`
- Modify: `docs/superpowers/specs/2026-07-22-catalyst-engine-vertical-slice-design.md`
- Modify: `docs/superpowers/plans/2026-07-22-catalyst-engine-vertical-slice.md`
- Regenerate: `frontend/dist/**`

- [ ] **Step 1: Run the backend catalyst regression suite**

Run:

```text
python -m pytest tests/test_market_event_service.py tests/test_catalyst_service.py tests/test_catalyst_api.py tests/test_driver_attribution_service.py tests/test_fundamental_signal_service.py tests/test_daily_market_report_service.py tests/test_daily_market_report_api.py tests/test_daily_market_report_scheduler.py tests/test_market_overview_service.py tests/test_market_overview_api.py -q
```

Expected: every selected backend test passes.

- [ ] **Step 2: Run frontend tests and build**

Run from `frontend/`:

```text
npm test
npm run build
```

Expected: the full Vitest suite passes and Vite produces a successful production build.

- [ ] **Step 3: Run scoped lint**

Run from `frontend/`:

```text
npx eslint src/api/api.ts src/api/api.test.ts src/types/api.ts src/components/MarketCatalystsPanel.tsx src/components/__tests__/MarketCatalystsPanel.test.tsx src/pages/DashboardPage.tsx src/pages/DashboardPage.test.tsx src/pages/DailyReportDetailPage.tsx src/pages/DailyReportDetailPage.test.tsx src/pages/DailyReportsPage.test.tsx
```

Expected: no lint error in catalyst-related files. Record the known unrelated full-repository lint baseline separately; do not broaden this slice into cleanup work.

- [ ] **Step 4: Apply and inspect the database migration**

Run against a disposable PostgreSQL database:

```text
python -m alembic upgrade head
python -m alembic downgrade 0041
python -m alembic upgrade head
```

Expected: `0042` upgrades, reverses, and reapplies without data or constraint errors.

- [ ] **Step 5: Perform browser QA**

Start the existing local app, then inspect desktop `1440x900` and mobile `390x844`:

- Dashboard with populated catalysts.
- Dashboard empty, loading, and error states.
- Game switch from Pokemon to Yu-Gi-Oh without stale catalyst rows.
- Daily Report detail with populated and empty catalyst snapshots.
- No overlapping text, page-level horizontal overflow, layout shifts, or broken external evidence links.

- [ ] **Step 6: Review scope and public safety**

Confirm with searches and API responses:

- `verified_by` is absent from public schemas and JSON.
- No public catalyst write endpoint exists.
- Null scores remain null/unscored.
- Only `REPRINT` adds a new deterministic driver mapping.
- Daily Report pages read stored snapshots rather than live catalyst data.
- No LLM, auto-scoring, scraping, notification, recommendation, or prediction behavior was introduced.

- [ ] **Step 7: Update delivery documents and plan checkboxes**

Mark Phase 4 Catalyst Engine complete in `CODEX_EXECUTION_PLAN.md`, add verification evidence and implementation commit references to the approved design, and check off each completed item in this plan.

- [ ] **Step 8: Commit generated assets and delivery records**

```text
git add docs/flashcard-planet-v2/CODEX_EXECUTION_PLAN.md docs/superpowers/specs/2026-07-22-catalyst-engine-vertical-slice-design.md docs/superpowers/plans/2026-07-22-catalyst-engine-vertical-slice.md
git add -f frontend/dist
git commit -m "docs: complete catalyst engine vertical slice"
```

- [ ] **Step 9: Final branch review and publish**

Run:

```text
git status --short
git log --oneline --decorate -12
git diff origin/codex/fp-v2-market-overview...HEAD --stat
```

Expected: only intentional Catalyst Engine work is present and the worktree is clean. Push `codex/fp-v2-market-overview`, update Draft PR #82 with the API/UI/verification summary, and keep the PR in draft until the user requests merge readiness.
