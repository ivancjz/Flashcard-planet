# Codex Execution Plan: Flashcard Planet v2

Status: active
Date: 2026-07-23

## Objective

Convert Flashcard Planet from a price lookup product into a market intelligence platform, starting with one small, tested, production-shaped slice.

## Current Codebase Reality

The repository already contains:

- FastAPI backend
- SQLAlchemy models for assets, price history, signals, users, alerts, watchlists, scheduler run logs, and market events
- price search and top mover endpoints
- signal service and signal feed logic
- dashboard frontend
- scheduler and ingestion infrastructure
- existing tests for API routes, price services, signal services, and scheduler behavior

Do not rebuild these systems. Extend them.

## Phase 1: Market Overview API

Build:

```text
GET /api/v1/market/overview
```

Purpose:

Provide the first v2 dashboard intelligence endpoint. It should summarize the current market using existing price history and signals.

Response shape:

```json
{
  "generated_at": "2026-07-21T00:00:00Z",
  "market_sentiment": "bullish",
  "confidence_label": "medium",
  "indexes": [],
  "top_movers": [],
  "signal_summary": [],
  "commentary": "Evidence-based summary.",
  "evidence": []
}
```

Required behavior:

- Use raw market segment price history by default.
- Group market index summaries by game.
- Compute game movement from latest versus previous raw observations.
- Include only evidence-backed commentary.
- Return `insufficient_data` when there is not enough evidence.
- Do not call any LLM provider.
- Do not create a scheduler job in this slice.

## Phase 2: Frontend Dashboard Integration

After the API is verified:

- Wire dashboard hero metrics to `/api/v1/market/overview`.
- Show market sentiment, top movers, signal counts, and commentary.
- Keep free-tier restrictions intact.
- Avoid exposing Pro-only fields.

## Phase 3: Daily Market Report

After Phase 1 and 2:

- Add persisted daily market report snapshot model.
- Add interval scheduler job.
- Every scheduler run must write `scheduler_run_log` success or failure.
- Generate deterministic report first.
- Add LLM summary only after evidence cache and prompt rules exist.

## Phase 4: Catalyst Engine - Complete 2026-07-22

Delivered:

- Extended the existing `market_events` registry through migration `0042`; no duplicate Catalyst model or event registry was created.
- Added curated affected asset, set, and game mappings; nullable impact and confidence scores; source evidence; and validation at the service and database boundaries.
- Implemented the exact deterministic lifecycle: `upcoming` before `event_date`, `active` from `event_date` through the inclusive `active_until`, and `expired` afterward. `active_until` uses `expected_window_days` or a 14-day default.
- Added read-only `GET /api/v1/market/catalysts` and `GET /api/v1/market/catalysts/{catalyst_id}` APIs with filtering, stable ordering, pagination, and public evidence fields.
- Added only the narrow `REPRINT` to `SUPPLY_SHOCK` deterministic driver attribution; other new display event types remain unmapped.
- Persisted immutable Catalyst snapshots in `daily_market_reports.catalysts_json`; published report reads validate and return the stored snapshot without querying live events.
- Added the independent Dashboard Catalyst panel and the Daily Report detail snapshot section, including loading, empty, error, null-score, and stale-request behavior.
- Added focused persistence, lifecycle, API, attribution, Daily Report, scheduler, client, and UI regression coverage.

Done evidence: 152 selected backend tests and 123 frontend tests across 15 files passed; changed backend modules and migration `0042` compiled; scoped Catalyst ESLint and the production frontend build succeeded; and a fresh disposable PostgreSQL 16 database completed `upgrade head`, `downgrade 0041`, `upgrade head`, with `alembic current` confirming `0042 (head)`. Direct inspection confirmed the Catalyst type index and non-negative event-window constraint. Desktop and mobile browser checks passed, and final review found no remaining blocking or important issues.

## Phase 5: Daily Report AI Intelligence - Complete 2026-07-23

Delivered:

- Added migration `0043` and a cache-keyed Daily Report intelligence model. Rows are unique by report, evidence hash, and prompt version, with bounded attempts and explicit pending, published, insufficient-evidence, and failed states.
- Built canonical evidence bundles for indexes, movers, signals, catalysts, and report evidence. Citation IDs and DOM target anchors are server-owned, deterministic, ASCII-safe, and carry exact public source record keys.
- Added strict plain-JSON commentary validation. Unknown citations, unsupported numbers or units, markup, URLs, advice, forecasts, guarantees, and unsupported causal claims are rejected before persistence or publication.
- Added the v2 positive observational grammar and a unit-aware lexical scanner. The validator accepts only evidence-linked observations, confines uncertainty language to the risk field, and rejects altered number forms, unsupported units, forecast paraphrases, and explicit causal claims.
- Added provider metadata without storing or logging raw model responses or complete prompts. Public responses omit provider, model, attempt, error, prompt, and source URL details.
- Implemented concurrency-safe claims with row locking, stale-claim recovery, a three-attempt limit, and claim ownership checks. The database session is closed before provider execution and a fresh session revalidates the evidence hash before publication.
- Preserved field-scoped evidence references for headline, commentary, observations, and risk. Normalized report-evidence labels retain an exact server source key so citation anchors resolve to the original report row.
- Added a default-off interval scheduler job. Insufficient evidence does not call a provider, and published cache keys are not generated twice.
- Extended the existing read-only Daily Report routes. No public generation endpoint or write route was added, and invalid stored commentary degrades to unavailable rather than reaching clients.
- Added Dashboard and Daily Report detail experiences for published, insufficient-evidence, and unavailable states. Commentary is rendered as React text, citations navigate to focused evidence targets, and deterministic report content remains usable for every fallback.

Verification evidence:

- 261 focused backend tests passed and one environment-gated PostgreSQL test skipped, covering persistence, evidence contracts, validation, repository state transitions, cross-session orchestration, API boundaries, scheduling, startup, and provider metadata. The skipped test passed separately against a migrated disposable PostgreSQL 16 plus pgvector database.
- The complete backend suite produced 1555 passes, one environment-gated skip, and three existing eBay scheduler failures. All three failures were reproduced unchanged on the pre-Phase-5 merged baseline commit `adc262b`; no Daily Report AI test failed.
- 138 frontend tests across 16 files passed. Scoped ESLint passed for every changed Daily Report frontend file, and the TypeScript production build completed successfully.
- Repository-wide ESLint still reports 18 existing errors in unrelated, unchanged frontend modules. These remain baseline debt and were not mixed into the Daily Report AI change.
- A fresh disposable PostgreSQL 16 plus pgvector database completed `upgrade head`, `downgrade 0042`, and `upgrade head`; `alembic current` confirmed `0043 (head)`. Direct inspection confirmed the foreign key, cache-key unique constraint, both check constraints, and both business indexes. A real two-session contention test confirmed exactly one worker claims a new cache key.
- Security scans found no public generation route, model-content HTML or Markdown rendering, non-GET Daily Report route, raw provider response persistence, or complete prompt persistence/logging.
- Browser QA used the real FastAPI API with `DAILY_REPORT_AI_ENABLED=false` at 1440x900 and 375x812. Published commentary wrapped without page overflow; headline, commentary, and risk each displayed only their field-scoped citation; and the normalized `market_segment=raw` citation focused the exact raw report-evidence row. All five evidence target kinds were present in the broader acceptance fixture. Insufficient evidence remained neutral and used the deterministic Dashboard fallback. Unavailable intelligence omitted the AI section while preserving Evidence, Catalysts, Indexes, Movers, and Signal Summary. Browser consoles contained no errors.

Provider note: no production or staging provider call was made during this verification. The published browser fixture was locally persisted only after passing the same production validator.

## Engineering Guardrails

- Follow `AGENTS.md`.
- New scheduler jobs use interval triggers.
- Every scheduler job writes run logs.
- Never use `CURRENT_TIMESTAMP` in triggers; use `clock_timestamp()`.
- Every `price_history` insert must populate `market_segment`.
- Signal computations use `market_segment='raw'` by default.
- Source labels must use canonical full names.
- Set identity is `metadata->>'set_id'`, not `set_code`.
- No import-time side effects.
- Test happy path and error/empty path.

## Done Means

Phase 1 is done when:

- backend service tests pass
- API route tests pass
- route is included under `/api/v1`
- insufficient-data behavior is explicit
- raw segment filtering is tested
- no LLM or scheduler work is introduced
