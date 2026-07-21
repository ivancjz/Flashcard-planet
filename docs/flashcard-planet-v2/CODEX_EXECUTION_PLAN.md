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

## Phase 4: Catalyst Engine

Add:

- catalyst model
- affected asset/set/game mapping
- impact score
- confidence
- event source evidence
- lifecycle status: upcoming, active, expired

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
