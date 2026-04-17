# Flashcard Planet — Agent Working Guide

This file is read automatically by Claude Code on startup. Read it fully before
touching any code. If anything here conflicts with what you see in the repo,
stop and ask the user — do not silently "fix" it.

---

## 1. What this project is

Flashcard Planet is a Pokémon TCG intelligence platform. It ingests market
data (Pokémon TCG API + eBay sold listings), detects price signals,
surfaces them through a Web UI and a Discord bot, and gates advanced
features behind a Pro tier.

The project is **past the MVP stage**. Core systems (ingestion, signals,
review, bot, web UI, auth) are already built and covered by ~522 tests.

**The current phase is productization + monetization, not feature
expansion.** See `docs/plan-v3.md` for the full 12-week plan. At any point
in a task, if the work you are about to do feels like "adding a new
feature no one asked for," stop and ask.

---

## 2. Four active workstreams

From the v3 plan, there are four parallel workstreams. When a task is
given to you, identify which workstream it belongs to first — this tells
you which files to look at.

- **Workflow A — Product experience**: Dashboard, Card Detail, Signals,
  Alerts, Review UI polish. Mostly frontend (`templates/`, `backend/app/site.py`).
- **Workflow B — Data coverage & quality**: Card pool expansion, mapping
  rules, image coverage, trust indicators. Mostly
  `backend/app/ingestion/` and `backend/app/services/`.
- **Workflow C — Monetization**: Pro tier boundary, upgrade flow, unified
  permission gating. Mixed — `backend/app/core/`, `backend/app/api/`,
  plus `templates/`.
- **Workflow D — Ops maturity**: Diagnostics page, KPI dashboard, review
  backlog. Mostly `backend/app/backstage/` and
  `backend/app/services/diagnostics_summary_service.py`.

---

## 3. Directory map

```
backend/
  app/
    api/             REST API routes (FastAPI)
    backstage/       Admin routes, scheduler, admin-only endpoints
    core/            Config, security/JWT, shared utilities
    db/              SQLAlchemy session, init_db
    ingestion/       Pokemon TCG + eBay data collection
    models/          SQLAlchemy ORM models
    services/        Business logic — most changes live here
    main.py          FastAPI app entry
    site.py          Server-rendered web UI routes (Jinja templates)
bot/                 Discord bot
database/            Sample data + fixtures
templates/           Jinja2 templates for the web UI
tests/               All tests (see §5)
scripts/             One-off scripts — NOT all current (see §4)
migrations/          Alembic migrations
docs/                Architecture notes + the v3 plan
alembic/             Alembic config

Top-level files:
  requirements.txt   Python dependencies
  docker-compose.yml Local dev environment
  alembic.ini        Alembic config
  start_flashcard_planet.bat / stop_flashcard_planet.bat  Windows helpers
```

---

## 4. Areas you must NOT touch unless explicitly asked

These paths either contain stale copies, runtime artifacts, or historical
experiments. Silently modifying them will cause confusion or break things.

- `.worktrees/` — Git worktree checkouts of parallel branches. Never
  read, never edit. They will look like duplicate source code.
- `logs/` — Runtime log files. Do not read these to understand the app.
- `.pycache_tmp/` — Build/cache artifacts.
- `scripts/*_trial.py`, `scripts/*_v2.py`, `scripts/demo_*.py`,
  `scripts/test_groq.py` — Historical one-offs. Do not reference them as
  examples.
- `migrations/versions/*.py` — Never edit existing migration files. If
  schema changes are needed, generate a new migration via Alembic.
- `test_runner/` (the directory in project root) — A legacy custom
  test runner, now superseded by real pytest. Do not use or reference it.

---

## 5. How to run tests

**This is the single most important section. Every code change must end
with a test run.**

### The one command you will use

From the project root:
python -m pytest tests/ -q

This runs real pytest 9.x. Configuration lives in `pytest.ini` at the
repo root — most importantly, `log_level = CRITICAL` keeps the output
clean so you can read the result at a glance.

Expected baseline as of last known-good state: **~522 tests, all pass,
runs in under 2 seconds.** If the count drops or anything fails,
investigate before continuing.

### Running a subset

When changing a specific module, run only the relevant test file:
python -m pytest tests/test_<module>.py -v

Example mappings (not exhaustive):
- `backend/app/services/permissions.py` → `tests/test_permissions.py`
- `backend/app/ingestion/ebay_sold.py`  → `tests/test_ebay_ingestion.py`
- `backend/app/services/backfill_retry_service.py` → `tests/test_backfill.py`

### Test style conventions

- Test files live in `tests/` and are named `test_<module>.py`.
- The codebase currently uses `unittest.TestCase`-style tests. When
  writing new tests, you may use either style, but match the existing
  style of the file you are modifying unless there is a good reason
  to refactor.
- Fixtures, `parametrize`, and `conftest.py` plugins are all available
  under real pytest — use them when they genuinely simplify a test,
  not just because they exist.

### What tests can and cannot do

- ✅ Tests run fully offline — they do not hit real eBay, Anthropic,
  Groq, or TCG APIs. All external calls are mocked.
- ✅ Tests use an in-memory or ephemeral database — no real DB needed.
- ❌ Do not add tests that require network access or real API keys.
- ❌ Do not skip tests to "make the suite pass." Fix the underlying
  issue or escalate.

---

## 6. How to run the app locally

Not usually needed — tests cover most verification. But if a task
explicitly requires running the server:

```
docker-compose up       # full stack
# or
start_flashcard_planet.bat    # Windows helper
```

Never start real ingestion jobs from a dev environment. The eBay and
Anthropic calls cost real money / quota.

---

## 7. Database migrations

If a task requires a schema change:

1. Make the ORM model change in `backend/app/models/`.
2. Generate a migration: `alembic revision --autogenerate -m "short description"`.
3. **Read the generated file.** Alembic autogenerate is not always
   correct — especially for enum changes, index renames, or column
   defaults. Fix by hand if needed.
4. Apply locally: `alembic upgrade head`.
5. Add / update the relevant test in `tests/test_init_db.py` or the
   affected service test.

Never edit an already-committed migration file. Add a new one instead.

---

## 8. Workflow rules for every task

Before coding:

1. **Understand first, edit second.** Read the relevant service, its
   test file, and any existing usages. Do not guess.
2. **State your plan before changing files.** If the change spans more
   than one file, say what you will do and wait for confirmation.
3. **Identify the workstream** (A / B / C / D from §2). This determines
   scope and what "done" looks like.

During coding:

4. **One task, one PR's worth of changes.** Do not bundle unrelated
   fixes.
5. **Match existing style.** If the file uses `snake_case` for local
   vars and `PascalCase` for classes, follow that. Do not introduce
   new patterns.
6. **Do not hard-code Chinese or English UI strings directly in
   templates.** Use the existing i18n mechanism (see how other templates
   handle bilingual text).
7. **Never hard-code a tier check.** All Pro / Free gating should go
   through the permission helper (once it exists — this is Workflow C-4).

After coding:

8. **Run the full test suite.** Report the exact pass/fail count.
9. **Report what you changed.** List every file modified, briefly
   explain why.
10. **Flag anything suspicious.** If a test was already failing when
    you started, say so — do not quietly "fix" unrelated things.

---

## 9. Things that are deceptively dangerous

A few traps specific to this repo:

- **`MagicMock` objects look like real objects until you do arithmetic
  or iterate.** Several diagnostics tests intentionally pass Mocks into
  code paths that fail gracefully. If you see
  `TypeError: unsupported operand type(s) for -: 'Mock' and 'Mock'`
  during a test run that passes overall, this is expected — the test is
  verifying the `_safe_block` wrapper catches it.
- **eBay ingestion has budget limits (daily API quota).** Never remove
  or raise these limits without an explicit request.
- **`access_tier` is a string field on `User`.** Current tiers are
  `free` and `pro`. Do not introduce new tier values without updating
  the permission tests.
- **Timezones.** All timestamps are UTC. If you touch anything
  datetime-related, use timezone-aware objects and verify with
  `test_price_history_summary.py` style tests.

---

## 10. What "done" looks like

A task is done when:

1. The code change is minimal and focused.
2. All existing tests still pass.
3. New tests exist for any new behaviour.
4. The change works with Pro/Free gating if it touches user-facing features.
5. No TODO or placeholder strings are left in production paths.
6. You have stated what you changed and why.

---

## 11. When in doubt

- If a task is ambiguous, ask one clarifying question before starting.
- If a task would require more than ~200 lines of new code, stop and
  propose a breakdown.
- If you discover the task's goal conflicts with the v3 plan
  (`docs/plan-v3.md`), surface the conflict — don't silently choose
  one.
- If tests start failing in an unrelated area, stop. That is a signal
  the change is wider than expected.

---

## 12. Useful references

- Full 12-week plan: `docs/plan-v3.md`
- Architecture notes: `docs/architecture.md`
- Dev notes: `docs/DEV_NOTES.md`
- Current provider evaluation: `docs/current_provider_evaluation.md`
