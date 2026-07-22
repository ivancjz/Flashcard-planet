# Daily Report History And Detail Design

## Context

Flashcard Planet now persists one Daily Market Report per UTC date and displays the latest report on the Dashboard. Users can see today's summary but cannot browse older reports, open a shareable report URL, or inspect the market indexes, movers, and signal evidence contained in a snapshot.

## Goal

Create a complete read-only Daily Report experience with a chronological history page, a date-addressable detail page, and clear entry points from the Dashboard and primary navigation.

## Considered Approaches

1. **Separate history and detail routes.** Use `/reports` for the archive and `/reports/:reportDate` for a report. This is selected because URLs are shareable, mobile navigation is predictable, and the routes do not conflict with `/market/:assetId`.
2. **Single split-view page.** Keep dates in a left rail and the selected report on the right. This is efficient on desktop but creates more state and a weaker mobile experience.
3. **Dashboard modal.** Open reports over the Dashboard. This keeps context but does not provide a durable history destination or shareable detail links.

## Backend Contract

Add `GET /api/v1/market/daily-report?limit=30&offset=0`.

The response contains:

- `reports`: complete `DailyMarketReportResponse` objects ordered by `report_date DESC`, then `generated_at DESC`
- `total`: total stored report count
- `limit`: accepted page size
- `offset`: accepted starting offset

`limit` is constrained to 1-100 and defaults to 30. `offset` is non-negative. The existing latest, dated, and generate endpoints remain unchanged.

## History Page

`/reports` loads the latest 30 reports. Each report row contains its UTC date, sentiment, confidence, and summary. Rows link to `/reports/YYYY-MM-DD`.

The page supports:

- Loading skeleton rows
- Empty archive state
- Request failure state
- `Load older reports` when `total` exceeds the number currently rendered
- A polite live status message while another page is loaded

Desktop rows use a compact scanning layout. At widths below 640px, each row becomes a two-column summary with the report text on its own line; the page does not require horizontal scrolling.

## Detail Page

`/reports/:reportDate` loads the existing dated endpoint. The page displays:

- Report title and UTC date
- Sentiment and confidence
- Summary and evidence
- Market indexes
- Top movers
- Signal summary

Empty subsections say that no comparable data was recorded. A missing report returns a neutral not-found page; other failures return an unavailable state. A back link returns to `/reports`.

## Navigation

- Add `Daily` to the primary navigation and mark it active for both report routes.
- Add `Read full report` to the successful Dashboard Daily Report panel.
- Do not show a detail link in loading, not-generated, or unavailable Dashboard states.

## Component Boundaries

- Backend service owns ordering, pagination, and total counting.
- Frontend API functions own HTTP status mapping.
- `DailyReportsPage` owns archive pagination and append behavior.
- `DailyReportDetailPage` owns report presentation.
- Existing Dashboard rendering remains local and only gains a detail link.

## Testing

- Backend service tests cover ordering, limit, offset, and total count.
- Backend route tests cover response shape and validated query parameters.
- Frontend API tests cover list, dated success, dated 404, and other errors.
- Page tests cover loading, success, empty/not-found, error, pagination, and detail sections.
- Navigation and Dashboard tests cover the new entry points.
- Full backend and frontend suites, the production build, and desktop/mobile browser checks are required.

## Out Of Scope

- Editing or deleting reports
- Search or calendar filters
- PDF, email, Discord, or push distribution
- Comparing two report dates
- AI-generated content beyond the persisted deterministic report

