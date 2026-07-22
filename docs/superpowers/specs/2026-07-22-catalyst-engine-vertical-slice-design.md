# Catalyst Engine Vertical Slice Design

Status: implemented and verified
Date: 2026-07-22

## Purpose

Build the first evidence-backed Catalyst Engine across the existing market event registry, public market API, Daily Market Report snapshots, and Dashboard.

The feature must answer:

- Which verified events may matter to the market now or soon?
- Which games, sets, and assets are affected?
- How large could the impact be according to the curated record?
- How strong is the supporting evidence?

This slice presents verified catalysts. It does not claim that an event caused a price move unless the existing deterministic driver attribution rules independently establish that relationship.

## Chosen Architecture

Extend `market_events` instead of creating a separate catalyst table.

The existing registry already owns:

- event date and type
- evidence URL and verification timestamp
- affected asset and set mappings
- expected activity window
- deterministic driver attribution integration

Using it as the single event source avoids duplicate records and prevents the Catalyst UI from disagreeing with the price-driver engine.

The first version retains JSON arrays for affected assets, sets, and games. The registry is manually curated and small, so normalized association tables are deferred until automated ingestion creates a demonstrated scale or query problem.

## Alternatives Considered

Normalized event-to-asset, event-to-set, and event-to-game association tables would improve large-registry query performance, but they would force an immediate rewrite of the working driver-attribution engine. That cost is not justified before automated ingestion exists.

A separate `catalysts` table would provide cleaner naming but create two event registries with overlapping evidence and mapping responsibilities. It was rejected because the Dashboard and driver-attribution engine could disagree about the same event.

## Data Model

Migration `0042` extends `market_events` with:

| Column | Type | Rules |
| --- | --- | --- |
| `affected_games` | JSONB | Non-null list. Existing curated records are backfilled to `["pokemon"]`. New global industry events use `["global"]`. |
| `impact_score` | Integer, nullable | Editorial score from 0 through 100. Null means unscored; it must never be converted to zero. |
| `confidence_score` | Numeric(5,2), nullable | Evidence confidence from 0 through 100. Null means insufficient evidence; it must never be converted to zero. |

Database checks enforce both score ranges. Existing events are not assigned invented scores during migration.

The migration expands the existing event type constraint to this canonical set:

- `INFLUENCER`
- `SUPPLY`
- `TOURNAMENT`
- `RELEASE`
- `REPRINT`
- `PRICE_CHANGE`
- `ANNIVERSARY`
- `COLLABORATION`
- `LIMITED_PRODUCT`
- `POLICY`
- `SOCIAL_TREND`

An index on `event_type` supports type filtering. The existing event-date index remains the primary timeline index.

## Score Semantics

Scores are curated assertions, not automatically inferred facts.

Impact labels:

- `high`: score 80 through 100
- `medium`: score 50 through 79
- `low`: score 0 through 49
- `unscored`: null

Confidence labels:

- `high`: score 80 through 100
- `medium`: score 50 through 79
- `low`: score 0 through 49
- `insufficient_data`: null

The create service validates the ranges, requires at least one affected game, and accepts only canonical event types. It continues to require a non-empty evidence URL and verification timestamp. New evidence URLs must use `http` or `https`.

The public response includes `verified_at` but omits `verified_by` so internal operator identifiers are not exposed.

## Lifecycle

Lifecycle is derived at read time and is not stored in the database.

Given an `as_of` UTC timestamp:

- `upcoming`: `event_date > as_of`
- `active`: `event_date <= as_of <= active_until`
- `expired`: `active_until < as_of`

`active_until` is `event_date + expected_window_days`. A null window uses the existing 14-day driver-attribution default. Both active boundaries are inclusive.

The lifecycle helper is a pure function so API queries, report generation, and tests use one definition. Historical report generation passes its report-generation timestamp instead of reading the current wall clock.

For the manually curated v1 registry, lifecycle filtering and final ordering may occur in the service after one bounded database read. This keeps date arithmetic consistent across PostgreSQL and SQLite tests. Automated event ingestion is out of scope; pagination must be moved fully into SQL before the registry becomes unbounded.

## Driver Attribution Compatibility

The four existing event types retain their current mappings and confidence weights.

`REPRINT` is the only new type admitted into deterministic price-driver attribution in this slice. It behaves as a supply-shock event and is included anywhere the current engine queries `SUPPLY` events.

The other new catalyst types are display and reporting evidence only. They do not become price-move explanations until separate deterministic attribution rules and tests exist. Unknown types continue to produce no causal claim.

## Public API

### List Catalysts

```text
GET /api/v1/market/catalysts
```

Query parameters:

- `status`: repeatable values from `upcoming`, `active`, and `expired`
- `game`: canonical game identifier such as `pokemon`
- `event_type`: one canonical event type
- `limit`: default 20, minimum 1, maximum 100
- `offset`: default 0, minimum 0

Game filtering includes records whose `affected_games` contains the requested game or `global`.

Default ordering is:

1. active events by impact score descending, then event date descending
2. upcoming events by event date ascending, then impact score descending
3. expired events by event date descending, then impact score descending

Null impact scores sort after scored records within the same lifecycle group.

Response:

```json
{
  "catalysts": [],
  "total": 0,
  "limit": 20,
  "offset": 0,
  "as_of": "2026-07-22T00:00:00Z"
}
```

Each catalyst contains:

- id
- event date, active-until timestamp, and lifecycle status
- event type and description
- source URL and verification timestamp
- affected game, set, and asset identifiers
- expected window days
- impact score and label
- confidence score and label

### Catalyst Detail

```text
GET /api/v1/market/catalysts/{catalyst_id}
```

The endpoint returns the same catalyst shape or `404` when no verified record exists.

Both endpoints are read-only. Manual creation remains in the evidence-validating service and curated seed or backstage workflows; this slice does not add a public write route.

## Daily Market Report Integration

`daily_market_reports` gains a non-null `catalysts_json` JSONB column with an empty-list default. Existing reports are backfilled to `[]` so historical responses remain valid.

Report generation snapshots at most five catalysts:

1. active catalysts
2. upcoming catalysts scheduled within the next 30 days

The common Catalyst service performs selection and serialization. Active records sort before upcoming records, followed by impact score and event timing.

The report response gains a `catalysts` array. The snapshot stores the complete public catalyst shape used at generation time, including source evidence. Later edits to `market_events` must not alter an already published report.

Daily report summary text and market sentiment remain unchanged in this slice. The mere presence of a catalyst must not generate wording that claims it caused a market move.

The Daily Report detail page adds a `Market Catalysts` section after Evidence and before Market Indexes. Empty snapshots display `No verified catalysts were captured for this report.`

## Dashboard Integration

The Dashboard loads verified active and upcoming catalysts independently from the existing market overview and Daily Report requests:

```text
GET /api/v1/market/catalysts?status=active&status=upcoming&game=pokemon&limit=3
```

The initial game filter follows the Dashboard's selected game. Changing games reloads the Catalyst panel without affecting card search or report state.

A focused `MarketCatalystsPanel` component renders a full-width section with compact rows, not nested cards. Each row shows:

- lifecycle and event-type labels
- event description
- event date
- impact label or `Unscored`
- confidence label or `Insufficient evidence`
- external evidence link

Source links open in a new tab with `rel="noreferrer"`. The panel has stable loading, empty, and unavailable states. A failed Catalyst request must not hide or break other Dashboard content.

No standalone Catalyst page is created in this slice.

## Frontend Types And Clients

The shared frontend API types gain `Catalyst`, `CatalystLifecycle`, and `CatalystListResponse` contracts that match the backend response exactly.

The API client provides:

- `fetchCatalysts(params)`
- `fetchCatalyst(catalystId)`

Repeated lifecycle filters are encoded as repeated `status` query parameters. Non-404 failures throw. The detail client maps `404` to `null` for future consumers even though this slice does not create a detail page.

## Error And Empty Behavior

- Invalid filters, UUIDs, score ranges, or pagination values return `422`.
- Missing detail records return `404`.
- Null scores are explicitly labeled and never coerced to numeric zero.
- Unverified records never appear in public Catalyst responses.
- A Daily Report can still be generated when no catalysts exist.
- No matching catalysts produces a valid report with an empty snapshot.
- An unexpected Catalyst selection error fails report generation before publication, allowing the existing scheduler run log to record the failure instead of publishing an incomplete snapshot.
- Dashboard Catalyst failure is isolated to its panel.

## Testing

Backend coverage includes:

- migration/model fields and score constraints
- lifecycle boundaries and the 14-day default
- score labels, including null values
- evidence URL, affected-game, type, and score validation
- game, type, lifecycle, pagination, and ordering behavior
- global-event inclusion in game filters
- public omission of `verified_by`
- list/detail API success, empty, 404, and 422 paths
- `REPRINT` supply-shock attribution without changing other mappings
- Daily Report snapshot immutability, ordering, empty behavior, and selection failure isolation

Frontend coverage includes:

- typed query encoding, including repeated statuses
- Dashboard panel loading, success, empty, and unavailable states
- selected-game reload behavior
- source-link security attributes
- null score labels
- Daily Report detail Catalyst rendering and empty snapshot label
- desktop and mobile browser checks for overlap and page-level horizontal overflow

## Implementation Evidence

- Implementation commits run from `b9b932b` through `1eb1d7b`, inclusive.
- Migration `0042` extends the existing `market_events` registry with Catalyst scope and nullable scores, adds immutable `daily_market_reports.catalysts_json` snapshots, and preserves `market_events` as the single event source.
- The public Catalyst endpoints are `GET /api/v1/market/catalysts` and `GET /api/v1/market/catalysts/{catalyst_id}`. Daily Report list, latest, and dated reads return the stored Catalyst snapshot in their existing response contract.
- The main frontend surfaces are the independent Dashboard `MarketCatalystsPanel` and the Daily Report detail `Market Catalysts` section rendered from `report.catalysts`.
- Fresh backend verification passed 152 Catalyst-related tests. Python compilation passed for all changed backend modules and migration `0042`.
- Fresh frontend verification passed 123 tests across 15 files. The production TypeScript/Vite build transformed 70 modules, and the scoped Catalyst ESLint command completed with no errors.
- A fresh disposable `postgres:16` container completed `upgrade head`, `downgrade 0041`, and `upgrade head`; `alembic current` confirmed `0042 (head)`. Direct PostgreSQL inspection confirmed `ix_market_events_event_type` and `ck_market_events_expected_window_days_nonnegative`. The pre-existing migration `0038` required the PostgreSQL 16 pgvector package to be installed in the disposable container. The container used a dynamic host port and was removed afterward.
- Live browser QA passed at desktop `1440x900` and mobile `390x844`. The populated Dashboard, Dashboard empty state, Pokemon-to-Yu-Gi-Oh switch, and populated Daily Report detail showed no page-level horizontal overflow, stale cross-game Catalyst rows, incoherent overlap, broken supported evidence links, or browser console warnings/errors. The report section order remained Evidence, Market Catalysts, then Market Indexes. Focused component tests cover Dashboard loading/error presentation and empty Daily Report snapshots.
- Public-safety inspection confirmed that `verified_by` is not exposed, Catalyst routes are GET-only, null scores remain unknown, only `REPRINT` adds driver attribution, report reads use stored snapshots, and no LLM, scraping, notification, recommendation, prediction behavior, or automatic scoring was added in this range.
- Final review findings were closed in `1eb1d7b`: zero-day windows now remain zero across lifecycle, attribution, and fundamental analysis; negative windows are rejected at service and database boundaries; unknown `event_type` filters return `422` while case-insensitive canonical values remain accepted; and the specified type index is present. Follow-up review found no remaining blocking or important issues.
- The full backend suite completed with 1,360 passes and one unrelated existing failure in `tests/test_ebay_ingestion_deadline.py::DeadlineTriggerTests::test_meta_json_carries_deadline_flag`; the isolated test reproduces the same failure outside the Catalyst scope.

## Non-Blocking Follow-Ups

- Add explicit registry-capacity telemetry before the curated registry grows beyond 1,000 records.
- Extract a shared Catalyst formatting utility if the Dashboard and report presentation continue to evolve together.
- Strengthen row and list semantics in the Daily Report Catalyst UI.

## Out Of Scope

- automated news or social ingestion
- LLM catalyst detection or causal explanation
- public create, edit, or delete endpoints
- standalone Catalyst archive or detail pages
- push, email, or Discord Catalyst notifications
- normalized catalyst association tables
- automatic impact or confidence scoring
- changes to market sentiment or recommendation logic

## Acceptance Criteria

- `market_events` is the single Catalyst source of truth.
- Every public Catalyst has evidence and a verification timestamp.
- Lifecycle is deterministic and shared by API and report generation.
- Null scores remain explicitly unknown.
- New event types do not create unsupported causal claims.
- The API supports filtered, stable pagination.
- Published Daily Reports retain immutable Catalyst snapshots.
- Dashboard Catalyst failures are isolated.
- Backend and frontend tests pass.
- Production frontend build succeeds.
- Desktop and mobile browser checks show no page-level horizontal overflow or incoherent overlap.
