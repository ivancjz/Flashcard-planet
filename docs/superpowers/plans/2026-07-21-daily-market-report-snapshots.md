# Daily Market Report Snapshots Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist deterministic Daily Market Report snapshots generated from the existing v2 Market Overview service.

**Architecture:** Add one `daily_market_reports` table, a focused SQLAlchemy model, a service that upserts one report per UTC report date, read/generate routes under `/api/v1/market/daily-report`, and a daily scheduler job that persists a report snapshot. The first version is deterministic and does not call LLM providers.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, Pydantic v2, PostgreSQL JSONB, pytest with SQLite-compatible JSON coercion.

---

### Task 1: Model, Schema, And Migration

**Files:**
- Create: `backend/app/models/daily_market_report.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/app/schemas/daily_market_report.py`
- Create: `migrations/versions/0041_add_daily_market_reports.py`

- [ ] **Step 1: Write model and schema tests first**

Add tests that expect a `DailyMarketReport` model and response schema to import cleanly and serialize a stored market overview.

- [ ] **Step 2: Implement model, schema, and migration**

Create a table with `id`, `report_date`, `generated_at`, `status`, `market_sentiment`, `confidence_label`, `title`, `summary`, `overview_json`, `evidence_json`, `created_at`, and `updated_at`.

- [ ] **Step 3: Verify targeted tests pass**

Run: `python -m pytest tests/test_daily_market_report_service.py`

### Task 2: Report Generation Service

**Files:**
- Create: `backend/app/services/daily_market_report_service.py`
- Test: `tests/test_daily_market_report_service.py`

- [ ] **Step 1: Write failing service tests**

Cover report creation, same-date upsert behavior, latest report lookup, and missing-date behavior.

- [ ] **Step 2: Implement deterministic report generation**

Use `get_market_overview(db)` as the evidence source. Persist the overview payload and a concise summary string. Do not call any LLM.

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/test_daily_market_report_service.py`

### Task 3: Market Report Routes

**Files:**
- Modify: `backend/app/api/routes/market.py`
- Test: `tests/test_daily_market_report_api.py`

- [ ] **Step 1: Write failing API route tests**

Cover:
- `GET /api/v1/market/daily-report/latest`
- `GET /api/v1/market/daily-report/{report_date}`

Security follow-up: report generation is scheduler-internal. No unauthenticated public route may create or overwrite a published snapshot.

- [ ] **Step 2: Implement routes**

Return typed `DailyMarketReportResponse` payloads. Return `404` when no latest or dated report exists.

- [ ] **Step 3: Run route tests**

Run: `python -m pytest tests/test_daily_market_report_api.py`

### Task 4: Daily Scheduler Job

**Files:**
- Modify: `backend/app/services/scheduler_run_log_service.py`
- Modify: `backend/app/backstage/scheduler.py`
- Test: `tests/test_daily_market_report_scheduler.py`

- [ ] **Step 1: Write failing scheduler tests**

Cover:
- daily report job registration
- successful snapshot run-log metadata
- failed snapshot run-log metadata written through a fresh database session after rolling back the report session

- [ ] **Step 2: Implement scheduler integration**

Register a 24-hour interval job with `next_run_time=None`, run one deterministic report snapshot, and write scheduler run-log success or error state.

- [ ] **Step 3: Run scheduler tests**

Run: `python -m pytest tests/test_daily_market_report_scheduler.py`

### Task 5: Verification And Delivery

- [ ] **Step 1: Run full targeted backend verification**

Run:

```text
python -m pytest tests/test_daily_market_report_service.py tests/test_daily_market_report_api.py tests/test_daily_market_report_scheduler.py tests/test_market_overview_service.py tests/test_market_overview_api.py
```

- [ ] **Step 2: Commit and push**

Commit message:

```text
feat: persist daily market report snapshots
```

- [ ] **Step 3: Update PR #82**

Add a PR comment with test output and scope.
