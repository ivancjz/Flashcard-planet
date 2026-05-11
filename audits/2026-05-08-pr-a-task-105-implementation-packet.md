# PR-A implementation packet — TASK-105 Phase 2: signal-history-prune scheduler job

Date: 2026-05-08
Plan reference: `BACKLOG.md` §2 TASK-105; CLAUDE.md §7 Issue D entry
Locked decisions:
- **(B) chosen**: ship retention prune scheduler job (this PR), then ship one-shot pre-fix repeat cleanup (PR-B follow-up) after PR-A is verified working.
- **`SIGNAL_HISTORY_RETENTION_DAYS` default = 90**: preserves product-relevant transition history; configurable via env. Steady-state ≈ 90 × ~1500/day = ~135k rows ≈ ~30 MB.
- **Job interval = 24h** (consistent with `ebay-ingestion`, `retry-pass` cadence — daily cleanup is more than enough granularity for storage hygiene).

Phase 1 verification (operator confirmed 2026-05-08):
- 2026-05-07: 957 rows, 0.0% repeats
- 2026-05-08: 1,462 rows, 0.0% repeats
- Pre-fix: ~387k rows/day → 99.7% reduction ✅

Phase 1 commit `78bd30b` deployed 2026-05-06 09:58 UTC; verification window closed 2026-05-08 10:00 UTC. **Preconditions met.**

---

## Branch + commits

```
git checkout main && git pull
git checkout -b feat/task-105-signal-history-prune
```

Two commits. Each independently verifiable.

1. `feat(scheduler): signal-history-prune job with configurable retention (TASK-105)`
2. `test(scheduler): coverage for signal-history-prune retention prune`

---

## Commit 1 — `feat(scheduler): signal-history-prune job with configurable retention (TASK-105)`

**Concern:** new daily scheduler job that DELETEs `asset_signal_history` rows older than `SIGNAL_HISTORY_RETENTION_DAYS`. Wires it into the scheduler conventions (run_log, heartbeat monitoring, startup delay).

### 1.1 — Add `JOB_HISTORY_PRUNE` constant

`backend/app/services/scheduler_run_log_service.py` — add the new job constant alongside existing ones:

```python
JOB_INGESTION    = "ingestion"
JOB_BACKFILL     = "backfill"
JOB_RETRY        = "retry"
JOB_SIGNALS      = "signals"
JOB_EBAY         = "ebay-ingestion"
JOB_BULK_REFRESH = "bulk-set-price-refresh"
JOB_HEARTBEAT    = "alert-heartbeat"
JOB_YGO          = "yugioh-ingestion"
JOB_EXPLANATION  = "explanation-sweep"
JOB_DIGEST       = "market-digest-send"
JOB_HISTORY_PRUNE = "signal-history-prune"   # NEW (TASK-105)
```

### 1.2 — Add env var

`backend/app/core/config.py` — add to the existing settings block (near the other scheduler-related settings like `zero_output_alert_window_hours`):

```python
signal_history_retention_days: int = Field(default=90, ge=7, le=365)
```

`ge=7` floor: less than 7 days would lose product-meaningful transition history. `le=365` ceiling: anything more is hoarding.

### 1.3 — Import the new constant in scheduler

`backend/app/backstage/scheduler.py` — add to the existing import block (around lines 14-26):

```python
from backend.app.services.scheduler_run_log_service import (
    JOB_DIGEST,
    JOB_EBAY,
    JOB_HEARTBEAT,
    JOB_HISTORY_PRUNE,   # NEW (TASK-105)
    JOB_INGESTION,
    JOB_RETRY,
    JOB_SIGNALS,
    JOB_YGO,
    JOB_EXPLANATION,
    finish_run,
    get_last_run,
    prune_old_runs,
    start_run,
)
```

### 1.4 — Add `_STARTUP_DELAY` entry

`backend/app/backstage/scheduler.py` lines 92-102 — add the new entry. Place it after `market-digest-send` (the current latest startup runner) so the prune doesn't compete with first-mover write jobs at boot:

```python
_STARTUP_DELAY: dict[str, int] = {
    "scheduled-ingestion":    120,   #  2 min — first mover
    "signal-sweep":           600,   # 10 min
    "alert-heartbeat":        720,   # 12 min — receives first sweep result before sending
    "ebay-ingestion":         660,   # 11 min — after signal-sweep, before heartbeat reports it
    "yugioh-ingestion":       780,   # 13 min — after heartbeat, YGO sets are small so runs fast
    "bulk-set-price-refresh": 900,   # 15 min — after ingestion (120s+~5min run) and signal (600s)
    "explanation-sweep":      960,   # 16 min — after signal-sweep so new signals get explanations fast
    "market-digest-send":     1200,  # 20 min — after all other jobs have warmed up
    "signal-history-prune":   1500,  # 25 min — last; pure DB DELETE, no upstream dependency  (NEW: TASK-105)
    # "retry-pass" intentionally omitted — resume separately when confidence is high
}
```

### 1.5 — Add `_run_signal_history_prune` body

`backend/app/backstage/scheduler.py` — add new function. Mirror the canonical pattern of `_send_heartbeat`. Place it near other `_run_*` definitions (alphabetical or logical-ordering, your call). Suggested location: after `_run_explanation_sweep` if that exists, or just above `build_scheduler`.

```python
def _run_signal_history_prune() -> None:
    """Daily DELETE of asset_signal_history rows older than retention window.

    Phase 2 of Issue D fix (Phase 1 = transition guard in commit 78bd30b).
    Steady-state row count ~= retention_days × post-fix daily transition rate
    (~1500 rows/day on 2026-05-08).

    Does NOT touch pre-fix repeat rows directly — those will age out as their
    computed_at crosses the retention boundary. For immediate pre-fix bulk
    cleanup, see the one-shot trigger in PR-B (planned follow-up).
    """
    settings = get_settings()

    try:
        with SessionLocal() as _log_session:
            _run_id = start_run(_log_session, JOB_HISTORY_PRUNE)
    except Exception as exc:
        logger.exception("start_run_failed job=%s", JOB_HISTORY_PRUNE)
        send_discord_alert(
            "error",
            f"CRITICAL: start_run 失败 — {JOB_HISTORY_PRUNE}",
            f"error={exc}\nJob 已跳过，本次无 run_log 记录",
        )
        return

    _exc: BaseException | None = None
    _log_meta: dict | None = None

    try:
        retention_days = settings.signal_history_retention_days
        with SessionLocal() as session:
            # Use parameter binding for the interval (NOT string interpolation)
            # to avoid SQL injection if retention_days is ever sourced externally.
            result = session.execute(
                sa_text("""
                    DELETE FROM asset_signal_history
                    WHERE computed_at < NOW() - (:days || ' days')::INTERVAL
                """),
                {"days": retention_days},
            )
            session.commit()
            rows_deleted = result.rowcount or 0

            # Capture oldest remaining row for post-prune verification.
            oldest_remaining = session.execute(
                sa_text("SELECT MIN(computed_at) FROM asset_signal_history")
            ).scalar()

        _log_meta = {
            "retention_days_applied": retention_days,
            "rows_deleted": rows_deleted,
            "oldest_remaining_at": oldest_remaining.isoformat() if oldest_remaining else None,
        }
        logger.info(
            "signal-history-prune complete: deleted=%d retention_days=%d oldest_remaining=%s",
            rows_deleted, retention_days, oldest_remaining,
        )
    except BaseException as exc:
        _exc = exc
        raise
    finally:
        try:
            with SessionLocal() as _log_session:
                finish_run(_log_session, _run_id, _exc, meta=_log_meta)
                prune_old_runs(_log_session, JOB_HISTORY_PRUNE)
        except Exception:
            logger.exception(
                "finish_run_failed job=%s run_id=%s",
                JOB_HISTORY_PRUNE, _run_id,
            )
```

### 1.6 — Register job in `build_scheduler`

`backend/app/backstage/scheduler.py` — add an `add_job` call alongside the existing ones (similar shape to `ebay-ingestion` since both are 24h interval):

```python
    scheduler.add_job(
        _run_signal_history_prune,
        "interval",
        hours=24,
        id="signal-history-prune",
        replace_existing=True,
        max_instances=1,
        next_run_time=None,
    )
```

`next_run_time=None` is mandatory — `prepare_scheduler_for_startup` reads `_STARTUP_DELAY` to set the first run, mirroring the pattern in CLAUDE.md §6 Lesson 2.

### 1.7 — Add to `_monitored_jobs` list

`backend/app/backstage/scheduler.py` line 387:

Before:
```python
_monitored_jobs = [JOB_EBAY, JOB_INGESTION, JOB_BULK_REFRESH, JOB_SIGNALS, JOB_YGO, JOB_EXPLANATION, JOB_DIGEST]
```
After:
```python
_monitored_jobs = [JOB_EBAY, JOB_INGESTION, JOB_BULK_REFRESH, JOB_SIGNALS, JOB_YGO, JOB_EXPLANATION, JOB_DIGEST, JOB_HISTORY_PRUNE]
```

Per CLAUDE.md §6 Lesson 9: every job that calls a long-running operation and writes meaningful output must be in `_monitored_jobs` so the heartbeat detects "ran but produced nothing useful." For prune, "useful output" = `rows_deleted` in meta_json. The existing zero-output detector reads `records_written` from run-log meta, but our meta key is `rows_deleted` — confirm the detector's logic handles this. If not, either rename our meta key to `records_written` for compatibility OR extend the detector to look at `rows_deleted` too. **Verify before committing**: read `get_zero_output_jobs` in scheduler.py and confirm.

### 1.8 — Update CLAUDE.md §2 scheduler table

The existing table in CLAUDE.md §2 lists 5 jobs (the original set). It's already out of date — current production has 9 jobs. **Out of scope for this commit** — flag separately in BACKLOG.md as a small docs-sync task, OR fold into PR-B.

### Verified by

- `pytest tests/test_scheduler_startup.py -v` — pass (existing test should not regress).
- `python -c "from backend.app.backstage.scheduler import _STARTUP_DELAY; assert 'signal-history-prune' in _STARTUP_DELAY"` — passes.
- Production Railway logs after deploy: `signal-history-prune complete: deleted=N retention_days=90 oldest_remaining=...`
- Production SQL after first run: `SELECT MIN(computed_at), COUNT(*) FROM asset_signal_history` — oldest_remaining should be < 90 days old; row count should reflect the delete.
- `SELECT job_name, status, meta_json FROM scheduler_run_log WHERE job_name='signal-history-prune' ORDER BY started_at DESC LIMIT 3` — at least one success row with valid meta_json.

**Commit message:**

```
feat(scheduler): signal-history-prune job with configurable retention (TASK-105)

Phase 2 of Issue D fix. Phase 1 (transition guard in _append_history,
commit 78bd30b) reduced inflow from ~387k rows/day to ~1500 rows/day.
This commit adds the daily DELETE that bounds the table size.

Job semantics:
  - Interval: 24h
  - DELETE WHERE computed_at < NOW() - (retention_days || ' days')::INTERVAL
  - retention_days configurable via SIGNAL_HISTORY_RETENTION_DAYS env var
    (default 90, range 7-365)
  - Steady-state target: ~135k rows (~30 MB) at 90d × 1500/day

Scheduler conventions followed (CLAUDE.md §2 + §6 Lesson 2/9):
  - JOB_HISTORY_PRUNE constant in scheduler_run_log_service
  - _STARTUP_DELAY entry: 1500s (after market-digest-send, last in queue)
  - interval trigger, next_run_time=None
  - Wrapped in canonical start_run / finish_run / prune_old_runs pattern
  - meta_json captures retention_days_applied, rows_deleted,
    oldest_remaining_at
  - Added to _monitored_jobs for heartbeat zero-output detection

Does NOT include one-shot pre-fix bulk cleanup. Pre-fix rows
(2.6 GB / 5.7M rows accumulated 2026-04-21 through 2026-05-06) will
age out as computed_at crosses the 90d boundary, beginning ~2026-07-20
and complete by ~2026-08-04. For immediate cleanup, see PR-B follow-up
in BACKLOG.md.

Verified:
- pytest tests/test_scheduler_startup.py: pass
- _STARTUP_DELAY contains "signal-history-prune": yes
- Production Railway logs: "signal-history-prune complete: deleted=..."
- Production SQL post-deploy: scheduler_run_log row for signal-history-prune
  with status=success, meta_json populated
```

---

## Commit 2 — `test(scheduler): coverage for signal-history-prune retention prune`

**Concern:** test the new job's three behaviours: (a) DELETE issued with correct param, (b) run_log written, (c) meta_json shape.

**File:** `tests/test_signal_history_prune.py` (new)

Mirror the existing test patterns from `tests/test_scheduler_run_log_cleanup.py` and `tests/test_zero_output_alerting.py`.

```python
"""Tests for signal-history-prune scheduler job (TASK-105 Phase 2)."""
from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import select

from backend.app.models.asset_signal_history import AssetSignalHistory
from backend.app.models.scheduler_run_log import SchedulerRunLog
from backend.app.services.scheduler_run_log_service import JOB_HISTORY_PRUNE


def _seed_history(db, *, asset_id, days_old, label="IDLE"):
    row = AssetSignalHistory(
        asset_id=asset_id,
        label=label,
        previous_label=None,
        confidence=0.9,
        price_delta_pct=0.0,
        liquidity_score=0.5,
        prediction=None,
        computed_at=datetime.now(timezone.utc) - timedelta(days=days_old),
        signal_context={},
    )
    db.add(row)
    db.commit()


def test_prune_deletes_rows_older_than_retention(db_session, monkeypatch):
    """Rows older than SIGNAL_HISTORY_RETENTION_DAYS get DELETEd."""
    monkeypatch.setenv("SIGNAL_HISTORY_RETENTION_DAYS", "30")
    # Reload settings cache if your config uses lru_cache / similar
    from backend.app.core.config import get_settings
    get_settings.cache_clear()

    _seed_history(db_session, asset_id="aaaa-1111", days_old=45)  # should be pruned
    _seed_history(db_session, asset_id="bbbb-2222", days_old=29)  # should be kept

    from backend.app.backstage.scheduler import _run_signal_history_prune
    _run_signal_history_prune()

    remaining = db_session.execute(
        select(AssetSignalHistory.asset_id).order_by(AssetSignalHistory.asset_id)
    ).scalars().all()
    assert remaining == ["bbbb-2222"]


def test_prune_writes_scheduler_run_log_with_meta(db_session, monkeypatch):
    """Job writes run_log row with status=success and meta_json populated."""
    monkeypatch.setenv("SIGNAL_HISTORY_RETENTION_DAYS", "30")
    from backend.app.core.config import get_settings
    get_settings.cache_clear()

    _seed_history(db_session, asset_id="cccc-3333", days_old=60)

    from backend.app.backstage.scheduler import _run_signal_history_prune
    _run_signal_history_prune()

    log_row = db_session.execute(
        select(SchedulerRunLog)
        .where(SchedulerRunLog.job_name == JOB_HISTORY_PRUNE)
        .order_by(SchedulerRunLog.started_at.desc())
        .limit(1)
    ).scalar_one()

    assert log_row.status == "success"
    assert log_row.meta_json is not None
    assert log_row.meta_json["retention_days_applied"] == 30
    assert log_row.meta_json["rows_deleted"] >= 1
    assert "oldest_remaining_at" in log_row.meta_json


def test_prune_handles_empty_table(db_session, monkeypatch):
    """Job runs cleanly when there are no rows to prune."""
    monkeypatch.setenv("SIGNAL_HISTORY_RETENTION_DAYS", "30")
    from backend.app.core.config import get_settings
    get_settings.cache_clear()

    # Seed only recent rows
    _seed_history(db_session, asset_id="dddd-4444", days_old=5)

    from backend.app.backstage.scheduler import _run_signal_history_prune
    _run_signal_history_prune()

    log_row = db_session.execute(
        select(SchedulerRunLog)
        .where(SchedulerRunLog.job_name == JOB_HISTORY_PRUNE)
        .order_by(SchedulerRunLog.started_at.desc())
        .limit(1)
    ).scalar_one()

    assert log_row.status == "success"
    assert log_row.meta_json["rows_deleted"] == 0
```

**Test fixture concern:** `db_session` fixture conventions — match whatever the existing test suite uses (`tests/conftest.py`). If it doesn't autouse a clean DB, these tests need explicit cleanup of `asset_signal_history` between cases. Check `tests/test_signal_delta.py` or `tests/test_alert_service.py` for the canonical pattern.

**Verified by:**
- `pytest tests/test_signal_history_prune.py -v` — all 3 tests pass.
- Coverage report shows `_run_signal_history_prune` body executed.
- Existing test suite (`pytest tests/`) — no regressions.

**Commit message:**

```
test(scheduler): coverage for signal-history-prune retention prune

3 test cases:
  1. test_prune_deletes_rows_older_than_retention — old rows go,
     new rows stay
  2. test_prune_writes_scheduler_run_log_with_meta — run_log row
     created with correct status and meta_json shape
  3. test_prune_handles_empty_table — no-op runs without error

Mirrors existing test pattern from test_scheduler_run_log_cleanup.py.

Verified:
- pytest tests/test_signal_history_prune.py -v: 3 passed
- pytest tests/: no regressions in existing suite
```

---

## After both commits land on the branch

1. Push: `git push -u origin feat/task-105-signal-history-prune`
2. Open PR-A: `gh pr create --base main --title 'feat(scheduler): signal-history-prune job — TASK-105 Phase 2 (PR-A)'`. Body: copy both commit messages.
3. Codex Cloud review (5–10 min). Likely findings to anticipate:
   - **Will probably flag**: `prune_old_runs(_log_session, JOB_HISTORY_PRUNE)` runs after every prune execution. If `prune_old_runs` itself queries `scheduler_run_log` without limit, it could be slow. Check the implementation; if needed, add a limit clause.
   - **Possible flag**: `result.rowcount` after a DELETE — Postgres returns the count, but some drivers don't. Check via local test.
   - **Less likely but possible**: missing index on `asset_signal_history.computed_at`. If the table has 5.7M rows and no index on this column, the daily DELETE will be slow. Check `\d asset_signal_history` (or the Alembic migration that created it).
4. Manual verification before merge:
   - First scheduled run on production (~25 min after deploy): check Railway logs for "signal-history-prune complete: deleted=N..."
   - SQL: `SELECT MIN(computed_at), COUNT(*) FROM asset_signal_history` — oldest_remaining should be ≤ 90 days; total count should reflect the delete (likely a few thousand rows on first run, since pre-fix accumulation only goes back ~14 days as of today, all within the 90d window — no bulk delete yet).
   - SQL: `SELECT * FROM scheduler_run_log WHERE job_name='signal-history-prune' ORDER BY started_at DESC LIMIT 3` — status=success, meta_json populated.
5. Merge after review-gate green. Railway auto-deploys.
6. **48h post-deploy verification gate (TASK-105 DoD):**
   - `/admin/diag/signal-history-stats?days=7` (already exists) — shows daily writes still ~1500/day post-fix.
   - DB total size unchanged for first ~75 days (pre-fix rows still within 90d window). Then pre-fix accumulation begins aging out and DB size starts dropping. Track via Railway storage tab weekly.

---

## What's deferred to PR-B (TASK-106, follow-up)

After PR-A is verified working for ~48h:

- **One-shot pre-fix repeat cleanup endpoint** at `/admin/trigger/cleanup-prefix-history`
- DELETEs in batches of 100k rows: `WHERE previous_label IS NOT NULL AND previous_label = label AND computed_at < '2026-05-06 09:58:00 UTC'` (the 78bd30b deploy timestamp)
- Returns `{rows_deleted_total, batches_run, duration_seconds}`
- Operator runs once after PR-A verified
- Reclaims ~2.5 GB instantly (the 99% repeat-row pre-fix accumulation)
- Transition rows (~1% of pre-fix data) preserved as historical product context

Add to BACKLOG.md as TASK-106 once PR-A merges. **Do not start before PR-A's 48h verification.**

---

## Verification probes available (no code change needed)

- `GET /admin/diag/signal-history-stats?days=7` — daily writes breakdown (already deployed, still useful for Phase 2 monitoring; sentinel can be updated to "REMOVE AFTER: TASK-106 verified" or kept as ongoing diagnostic).
- `psql $DATABASE_URL -c "SELECT MIN(computed_at), MAX(computed_at), COUNT(*), pg_total_relation_size('asset_signal_history') / 1024 / 1024 AS size_mb FROM asset_signal_history;"` — point-in-time snapshot of table state.
- `railway logs --service backend | grep signal-history-prune` — see job runs in real time.

---

## Open question for the operator

**`SIGNAL_HISTORY_RETENTION_DAYS` initial production value.** Packet defaults to 90. Want to override on deploy — say to 60 — to start the recovery sooner without waiting for PR-B? Set it via `railway variables set SIGNAL_HISTORY_RETENTION_DAYS=60` before merging PR-A. Storage tradeoff: 90d → ~30 MB steady-state; 60d → ~20 MB; 30d → ~10 MB. All trivial compared to current 2.6 GB; the choice is product-history horizon, not space.

Default if you don't answer: 90 (lean conservative, PR-B will reclaim space fast anyway).
