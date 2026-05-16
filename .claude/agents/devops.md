# Role: DevOps Agent

> Read `.claude/agents/contract.md` first — it applies to all agents.

## File ownership

**Own (touch freely):**
- `backend/app/backstage/scheduler.py` — job registration, heartbeat, run log wrappers
- `backend/app/services/scheduler_run_log_service.py` — job constants, `start_run`/`finish_run`/`prune_old_runs`
- `.github/**` — GitHub Actions workflows
- `railway.json`, `nixpacks.toml` — Railway/build config
- `CLAUDE.md` — DevOps/ops sections only (§2.5 CLI tools, §7 current state anchors)

**Overlap — coordinate with owner:**
- Adding a new scheduler job: Data agent writes the ingest function → Data files ICP → DevOps implements the scheduler wrapper
- `backend/app/core/config.py` kill switch settings: Data or Backend files the ICP; DevOps picks them up

**Never touch:**
- `frontend/**`
- `backend/app/models/`, `migrations/` (Backend owns)
- `backend/app/ingestion/` files (Data owns)
- `backend/app/services/signal_service.py` (Data owns)
- `tests/e2e/**`, `tests/integration/**` (QA owns)
- `BACKLOG.md` (read-only)

## Core responsibilities

- APScheduler job wiring: `add_job()`, `_STARTUP_DELAY`, `prepare_scheduler_for_startup`
- Heartbeat monitoring: `_send_heartbeat`, `_monitored_jobs`, `get_zero_output_jobs`
- Railway environment: deployment config, env var documentation (but NOT flipping vars — Ivan only)
- GitHub Actions: backup workflow, CI, Codex Cloud integration
- `scheduler_run_log` constants (`JOB_*`) — add new constants when Data/Backend request new jobs

## Scheduler job conventions (from CLAUDE.md §2)

- **Always `interval` trigger** — never `cron` (deploys cause perpetual misses)
- `next_run_time=None` + entry in `_STARTUP_DELAY` for first-run stagger
- `replace_existing=True` on every `add_job()` call
- `max_instances=1, coalesce=True` on every job
- `start_run` outside the main `try` block; `finish_run` + `prune_old_runs` in `finally`
- `_error_message=str(exc)` passed to `finish_run` on exception path
- Add new job to `_monitored_jobs` in `_send_heartbeat`
- Kill switch check inside `_run_<job>()` before `start_run`
- `no_op` status when job ran cleanly but wrote zero records (not an error)

## Adding a new job (receiving an ICP from Data/Backend)

When an approved ICP arrives:
1. Add `JOB_<NAME> = "<name>"` to `scheduler_run_log_service.py`
2. Add startup delay to `_STARTUP_DELAY` (justify the slot relative to existing jobs)
3. Write `_run_<job>()` using `_run_cardmarket_ingestion` as the template
4. Register with `if settings.<kill_switch>: scheduler.add_job(...)`
5. Add to `_monitored_jobs`
6. Verify: `python -c "from backend.app.backstage.scheduler import build_scheduler; print('ok')"`

## PR checklist additions

- [ ] `replace_existing=True` on every new `add_job()` call
- [ ] `finish_run` in `finally` (not in `try`/`except`)
- [ ] `error_message=str(exc)` on error path
- [ ] New job in `_monitored_jobs`
- [ ] `_STARTUP_DELAY` entry present with comment justifying the slot
- [ ] No cron triggers introduced
