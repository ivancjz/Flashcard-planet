# Dashboard Daily Report Design

## Context

Flashcard Planet already generates and persists one deterministic Daily Market Report snapshot per UTC date. The Dashboard currently shows a live Market Overview but does not expose the persisted report, so users cannot see the daily intelligence artifact that the scheduler produces.

## Goal

Show the latest persisted Daily Market Report near the top of the Dashboard with a clear distinction between a report that has not yet been generated and a request that failed.

## Considered Approaches

1. **Add a focused Daily Report band above Market Overview.** This keeps the report prominent while preserving the live overview as a separate, more detailed market module. This is the selected approach.
2. **Replace Market Overview with the Daily Report.** This removes duplication, but it also hides live data between scheduled snapshots.
3. **Create a dedicated Daily Report page.** This provides more room for future sections, but adds navigation and routing before the first report experience needs them.

## User Experience

The Dashboard loads the latest report in parallel with its existing data requests. The report band appears before Market Overview and contains:

- Product label: `Flashcard Planet Daily`
- Report title and UTC report date
- Market sentiment and confidence label
- Evidence-based summary
- Up to three evidence statements

The band uses the existing dark surface, typography, spacing, and color tokens. It remains a single responsive section rather than a collection of nested cards.

## States

- **Loading:** Reserve a stable section with `aria-busy="true"` and a concise loading label.
- **Available:** Render the report content and evidence.
- **Not generated:** A `404` from the latest-report endpoint becomes a neutral empty state: `Today's report has not been generated yet.`
- **Unavailable:** Network errors and non-404 responses become an error state: `Daily report unavailable.`

## Data Contract

The frontend adds a `DailyMarketReport` type matching `DailyMarketReportResponse` and a `fetchLatestDailyMarketReport()` client function. The function returns `null` for `404`, throws for other unsuccessful responses, and returns the parsed report for successful responses.

## Component Boundary

`DashboardPage` owns loading and request state. A local `DailyMarketReportPanel` owns presentation and receives:

- `report: DailyMarketReport | null | undefined`
- `unavailable: boolean`

`undefined` means loading, `null` means no generated report, and a report object means success.

## Testing

API tests cover successful parsing, `404` to `null`, and non-404 failure. Dashboard tests cover the successful report, the not-generated state, and the unavailable state. The full frontend test suite and production build must pass, followed by desktop and mobile browser inspection.

## Out Of Scope

- Dedicated report history or detail route
- Manual report generation controls
- LLM-generated commentary
- Email, Discord, PDF, or push distribution UI

