# Daily Report History And Detail Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a paginated Daily Report archive, shareable dated report pages, and navigation from the Dashboard.

**Architecture:** Extend the existing daily-report service with a count plus descending paginated query and expose it through the existing market router. Add typed frontend API clients, one archive page, one detail page, and route/navigation entry points while reusing the persisted report payload without new AI or ingestion behavior.

**Tech Stack:** FastAPI, SQLAlchemy 2, Pydantic v2, pytest, React 19, React Router, TypeScript 6, Vitest, Testing Library, Vite.

---

### Task 1: Backend History Service And Schema

**Files:**
- Modify: `backend/app/schemas/daily_market_report.py`
- Modify: `backend/app/services/daily_market_report_service.py`
- Test: `tests/test_daily_market_report_service.py`

- [x] **Step 1: Write the failing service test**

Create three dated reports and call:

```python
page = list_daily_market_reports(sqlite_db, limit=2, offset=1)
```

Assert `page.total == 3`, dates are descending, the second and third newest records are returned, and `limit`/`offset` are preserved.

- [x] **Step 2: Run the service test and verify RED**

Run: `python -m pytest tests/test_daily_market_report_service.py -q`

Expected: collection fails because `list_daily_market_reports` and `DailyMarketReportListResponse` do not exist.

- [x] **Step 3: Implement the list response and query**

Add:

```python
class DailyMarketReportListResponse(BaseModel):
    reports: list[DailyMarketReportResponse]
    total: int
    limit: int
    offset: int
```

Implement `list_daily_market_reports(db, *, limit=30, offset=0)` using one count query and one descending paginated row query.

- [x] **Step 4: Run the service test and verify GREEN**

Run: `python -m pytest tests/test_daily_market_report_service.py -q`

Expected: all daily report service tests pass.

### Task 2: Backend History Route

**Files:**
- Modify: `backend/app/api/routes/market.py`
- Test: `tests/test_daily_market_report_api.py`

- [x] **Step 1: Write failing route tests**

Assert `GET /api/v1/market/daily-report?limit=20&offset=10` returns the typed page and calls:

```python
list_daily_market_reports(db, limit=20, offset=10)
```

Also assert `limit=0`, `limit=101`, and `offset=-1` return `422`.

- [x] **Step 2: Run the route tests and verify RED**

Run: `python -m pytest tests/test_daily_market_report_api.py -q`

Expected: the history route is missing.

- [x] **Step 3: Implement the history route**

Register `GET /daily-report` before the dated route with `Query(30, ge=1, le=100)` and `Query(0, ge=0)`.

- [x] **Step 4: Run the route tests and verify GREEN**

Run: `python -m pytest tests/test_daily_market_report_api.py -q`

Expected: all route tests pass.

### Task 3: Frontend Daily Report API

**Files:**
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/api/api.ts`
- Modify: `frontend/src/api/api.test.ts`

- [ ] **Step 1: Write failing client tests**

Test that `fetchDailyMarketReports({ limit: 30, offset: 0 })` requests the encoded list endpoint and returns `DailyMarketReportListResponse`. Test that `fetchDailyMarketReportByDate('2026-07-21')` returns a report, maps `404` to `null`, and throws for other failures.

- [ ] **Step 2: Run the client tests and verify RED**

Run: `npm test -- src/api/api.test.ts`

Expected: imports fail because both functions are missing.

- [ ] **Step 3: Implement the typed clients**

Add:

```ts
export interface DailyMarketReportListResponse {
  reports: DailyMarketReport[]
  total: number
  limit: number
  offset: number
}
```

Implement the list and dated fetch functions. Encode the report date with `encodeURIComponent`.

- [ ] **Step 4: Run the client tests and verify GREEN**

Run: `npm test -- src/api/api.test.ts`

Expected: all API client tests pass.

### Task 4: Daily Report Archive Page

**Files:**
- Create: `frontend/src/pages/DailyReportsPage.tsx`
- Create: `frontend/src/pages/DailyReportsPage.test.tsx`
- Modify: `frontend/src/styles/theme.css`

- [ ] **Step 1: Write failing archive page tests**

Mock the list client and cover loading, populated rows, empty archive, request error, and `Load older reports` appending the next page.

- [ ] **Step 2: Run the archive page tests and verify RED**

Run: `npm test -- src/pages/DailyReportsPage.test.tsx`

Expected: the page module is missing.

- [ ] **Step 3: Implement the archive page**

Render `NavBar`, page heading, responsive report rows linking to dated routes, stable loading/error/empty states, and a load-more button while `reports.length < total`.

- [ ] **Step 4: Run the archive page tests and verify GREEN**

Run: `npm test -- src/pages/DailyReportsPage.test.tsx`

Expected: all archive page tests pass.

### Task 5: Daily Report Detail Page

**Files:**
- Create: `frontend/src/pages/DailyReportDetailPage.tsx`
- Create: `frontend/src/pages/DailyReportDetailPage.test.tsx`

- [ ] **Step 1: Write failing detail page tests**

Cover loading, full report rendering, missing report, request error, market indexes, top movers, signal summary, and empty subsection labels.

- [ ] **Step 2: Run the detail tests and verify RED**

Run: `npm test -- src/pages/DailyReportDetailPage.test.tsx`

Expected: the page module is missing.

- [ ] **Step 3: Implement the detail page**

Read `reportDate` with `useParams`, call the dated client, and render the persisted snapshot in compact full-width sections. Keep tables responsive without page-level horizontal overflow.

- [ ] **Step 4: Run the detail tests and verify GREEN**

Run: `npm test -- src/pages/DailyReportDetailPage.test.tsx`

Expected: all detail tests pass.

### Task 6: Routes And Entry Points

**Files:**
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/components/NavBar.tsx`
- Modify: `frontend/src/components/__tests__/NavBar.test.tsx`
- Modify: `frontend/src/pages/DashboardPage.tsx`
- Modify: `frontend/src/pages/DashboardPage.test.tsx`

- [ ] **Step 1: Write failing navigation tests**

Assert the primary nav includes `Daily`, the Dashboard success panel links to `/reports/2026-07-21`, and inactive Dashboard states contain no `Read full report` link.

- [ ] **Step 2: Run the navigation tests and verify RED**

Run: `npm test -- src/components/__tests__/NavBar.test.tsx src/pages/DashboardPage.test.tsx`

Expected: the new entry points are missing.

- [ ] **Step 3: Implement routes and links**

Register `/reports` and `/reports/:reportDate`, add the primary nav entry, and add the successful Dashboard report link.

- [ ] **Step 4: Run the navigation tests and verify GREEN**

Run: `npm test -- src/components/__tests__/NavBar.test.tsx src/pages/DashboardPage.test.tsx`

Expected: all navigation tests pass.

### Task 7: Verification And Delivery

- [ ] **Step 1: Run backend verification**

Run:

```text
python -m pytest tests/test_daily_market_report_service.py tests/test_daily_market_report_api.py tests/test_daily_market_report_scheduler.py tests/test_market_overview_service.py tests/test_market_overview_api.py -q
```

- [ ] **Step 2: Run frontend verification and build**

Run `npm test` and `npm run build` from `frontend/`.

- [ ] **Step 3: Inspect browser layouts**

Verify `/reports` and `/reports/2026-07-21` at desktop and mobile widths. Confirm no text overlap, page-level horizontal scroll, clipped evidence, or unusable controls.

- [ ] **Step 4: Request independent code review**

Review the full phase diff against the design and resolve all actionable findings.

- [ ] **Step 5: Commit, push, and update PR #82**

Use focused commits for backend, frontend, and any review fixes. Add a PR comment with verification results and commit SHAs.
