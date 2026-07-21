# Codex Execution Plan: Flashcard Planet v2

Status: active
Date: 2026-07-21

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

Done evidence: 146 selected backend tests and 123 frontend tests across 15 files passed; changed backend modules and migration `0042` compiled; scoped Catalyst ESLint and the production frontend build succeeded; and a fresh disposable PostgreSQL 16 database completed `upgrade head`, `downgrade 0041`, `upgrade head`, with `alembic current` confirming `0042 (head)`.

Phase 5 AI Intelligence remains next and is out of scope for the completed Catalyst Engine slice.

## Phase 5: AI Intelligence Engine

Add LLM only after deterministic evidence objects exist.

Rules:

- AI may summarize evidence.
- AI may not invent causes.
- Every explanation must reference evidence fields.
- Low confidence must produce "Insufficient evidence."
- LLM failure must not break API responses.

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
