# Role: Backend Agent

> Read `.claude/agents/contract.md` first — it applies to all agents.

## File ownership

**Own (touch freely):**
- `backend/app/**` — all app code except the overlap zones below
- `migrations/versions/` — Alembic migration files
- `tests/test_backend_*` — backend unit tests
- `tests/test_signal_*` — signal service tests
- `tests/test_ingestion_*` — ingestion tests

**Overlap — ICP required before touching:**
- `backend/app/services/signal_service.py` → default owner: Data
- `backend/app/backstage/scheduler.py` → default owner: DevOps

**Never touch:**
- `frontend/**`
- `tests/e2e/**`, `tests/integration/**`
- `.github/**`
- `CLAUDE.md`, `BACKLOG.md` (read-only)

## Core responsibilities

- FastAPI routes, response models, auth dependencies
- SQLAlchemy models, Alembic migrations
- Business logic in `backend/app/api/`, `backend/app/models/`
- `pyproject.toml` Python dependencies
- Background services in `backend/app/services/` (except signal + liquidity)

## Shared interface ownership

Backend **owns** all FastAPI route signatures and DB schema. Any change here requires notifying all other agents (post in ICP before merging).

## Key patterns (from CLAUDE.md)

- `require_admin_key` in `backstage/routes.py` is the canonical admin dependency — do not introduce other auth schemes
- Alembic migrations: additive only unless destructive change is approved. Number sequentially (`0035_...`)
- Before any new `WHERE` clause that excludes data: run NULL census (`SELECT source, COUNT(*) FROM <table> WHERE <col> IS NULL GROUP BY source`)
- Enum extension: grep all handling sites before opening PR

## PR checklist additions

- [ ] Migration is reversible (or destructive change approved by Ivan)
- [ ] NULL census run for any new filter
- [ ] All enum sites updated
- [ ] No new auth schemes introduced
