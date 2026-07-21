# Dashboard Daily Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Display the latest persisted Daily Market Report on the Dashboard with explicit loading, not-generated, and unavailable states.

**Architecture:** Add one typed API function that maps `404` to `null`, then let `DashboardPage` load the report in parallel with its existing requests. A focused local presentation component renders the report without introducing a new route or duplicating backend business logic.

**Tech Stack:** React 19, TypeScript 6, Fetch API, Vitest, Testing Library, Vite.

---

### Task 1: Daily Report API Contract

**Files:**
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/api/api.ts`
- Test: `frontend/src/api/api.test.ts`

- [x] **Step 1: Write failing API tests**

Add tests that call `fetchLatestDailyMarketReport()` and assert:

```ts
expect(fetchMock).toHaveBeenCalledWith('/api/v1/market/daily-report/latest')
expect(result?.title).toBe('Flashcard Planet Daily')
```

Also assert that a `404` response returns `null` and a `503` response rejects with `daily market report fetch failed`.

- [x] **Step 2: Run the API tests and verify RED**

Run: `npm test -- src/api/api.test.ts`

Expected: FAIL because `fetchLatestDailyMarketReport` is not exported.

- [x] **Step 3: Add the response type and API function**

Add a `DailyMarketReport` interface with the backend fields and implement:

```ts
export async function fetchLatestDailyMarketReport(): Promise<DailyMarketReport | null> {
  const res = await fetch(`${BASE}/api/v1/market/daily-report/latest`)
  if (res.status === 404) return null
  if (!res.ok) throw new Error('daily market report fetch failed')
  return res.json()
}
```

- [x] **Step 4: Run the API tests and verify GREEN**

Run: `npm test -- src/api/api.test.ts`

Expected: all API tests pass.

### Task 2: Dashboard Daily Report Band

**Files:**
- Modify: `frontend/src/pages/DashboardPage.tsx`
- Test: `frontend/src/pages/DashboardPage.test.tsx`

- [x] **Step 1: Write failing Dashboard tests**

Mock `fetchLatestDailyMarketReport` and assert the available state renders `Flashcard Planet Daily`, the report title, `Bullish`, `Medium confidence`, the report date, summary, and evidence. Add separate tests for a `null` result and a rejected request.

- [x] **Step 2: Run the Dashboard tests and verify RED**

Run: `npm test -- src/pages/DashboardPage.test.tsx`

Expected: FAIL because the Dashboard does not fetch or render Daily Market Reports.

- [x] **Step 3: Implement request state and presentation**

Add `dailyReport` and `dailyReportUnavailable` state, fetch the report in the initial effect, and render:

```tsx
<DailyMarketReportPanel report={dailyReport} unavailable={dailyReportUnavailable} />
```

The panel must use `undefined` for loading, `null` for not generated, and a report object for success. It must render before `MarketOverviewPanel` and use existing theme tokens.

- [x] **Step 4: Run the Dashboard tests and verify GREEN**

Run: `npm test -- src/pages/DashboardPage.test.tsx`

Expected: all Dashboard tests pass.

### Task 3: Verification And Delivery

**Files:**
- Modify: `frontend/dist/**` through the existing build command

- [x] **Step 1: Run complete frontend tests**

Run: `npm test`

Expected: zero failed test files and zero failed tests.

- [x] **Step 2: Build production assets**

Run: `npm run build`

Expected: TypeScript and Vite complete with exit code 0.

- [x] **Step 3: Inspect desktop and mobile layouts**

Open the Dashboard in the in-app browser at desktop and mobile widths. Verify that the report band is visible, text does not overlap, evidence wraps cleanly, and no horizontal scrolling appears.

- [x] **Step 4: Commit and push**

Commit message:

```text
feat: show daily market report on dashboard
```

- [x] **Step 5: Update PR #82**

Add a concise PR comment listing the new Dashboard behavior, verification results, and commit.
