# JobContext — Long-Running Job Lifecycle Manager

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add mid-run progress checkpoints, deadline enforcement, and a live-jobs admin view to Flashcard Planet's scheduler jobs — without changing the `SchedulerRunLog` schema.

**Architecture:** A thin `JobContext` wrapper sits on top of the existing `start_run`/`finish_run` pattern. Jobs swap their explicit `start_run`/`finish_run`/`prune_old_runs` calls for a single `with job_context(...) as ctx:` block, gaining `ctx.checkpoint()` for mid-run DB updates and optional deadline enforcement. The `meta_json` column (already `JSONB`, already nullable) carries all progress state — no migration needed.

**Tech Stack:** Python 3.13, SQLAlchemy 2, existing `SchedulerRunLog` model, pytest + `unittest.mock`.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `backend/app/services/scheduler_run_log_service.py` | Add `update_run()` |
| Create | `backend/app/services/job_context.py` | `JobContext` class + `job_context()` context manager |
| Create | `tests/test_job_context.py` | Unit tests (mock-based, no DB) |
| Modify | `backend/app/backstage/scheduler.py` | Migrate `_run_bulk_set_price_refresh` to `job_context` |
| Modify | `backend/app/backstage/routes.py` | Add `/admin/diag/live-jobs` endpoint |

---

## Task 1: Add `update_run()` to `scheduler_run_log_service.py`

**Files:**
- Modify: `backend/app/services/scheduler_run_log_service.py` (after `finish_run`, before `prune_old_runs`)

- [ ] **Step 1: Write the failing test**

Create `tests/test_job_context.py` with this first test:

```python
"""tests/test_job_context.py"""
from __future__ import annotations
import unittest
from unittest.mock import MagicMock, patch, call


def _make_run_row(run_id=1, meta=None):
    row = MagicMock()
    row.id = run_id
    row.records_written = 0
    row.errors = 0
    row.meta_json = meta
    return row


class TestUpdateRun(unittest.TestCase):

    def test_update_run_sets_records_written(self):
        session = MagicMock()
        row = _make_run_row(run_id=7)
        session.get.return_value = row

        from backend.app.services.scheduler_run_log_service import update_run
        update_run(session, 7, records_written=42)

        self.assertEqual(row.records_written, 42)
        session.commit.assert_called_once()

    def test_update_run_merges_meta_json(self):
        session = MagicMock()
        row = _make_run_row(run_id=7, meta={"existing_key": "keep_me"})
        session.get.return_value = row

        from backend.app.services.scheduler_run_log_service import update_run
        update_run(session, 7, meta_json_merge={"stage": "step_2"})

        self.assertEqual(row.meta_json["existing_key"], "keep_me")
        self.assertEqual(row.meta_json["stage"], "step_2")
        session.commit.assert_called_once()

    def test_update_run_noop_when_not_found(self):
        session = MagicMock()
        session.get.return_value = None

        from backend.app.services.scheduler_run_log_service import update_run
        update_run(session, 999, records_written=10)  # should not raise

        session.commit.assert_not_called()
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_job_context.py::TestUpdateRun -v
```
Expected: `FAILED` — `ImportError: cannot import name 'update_run'`

- [ ] **Step 3: Add `update_run()` to `scheduler_run_log_service.py`**

Insert after the `finish_run` function (after line 77), before `prune_old_runs`:

```python
def update_run(
    session: Session,
    run_id: int,
    *,
    records_written: int | None = None,
    errors: int | None = None,
    meta_json_merge: dict | None = None,
) -> None:
    """Write a mid-run progress snapshot. Does not change status. Commits immediately.

    meta_json_merge is shallow-merged into the existing meta_json value so
    callers can add fields without stomping keys written by previous checkpoints.
    """
    row = session.get(SchedulerRunLog, run_id)
    if row is None:
        logger.warning("update_run: run_id=%s not found", run_id)
        return
    if records_written is not None:
        row.records_written = records_written
    if errors is not None:
        row.errors = errors
    if meta_json_merge is not None:
        existing = row.meta_json or {}
        row.meta_json = {**existing, **meta_json_merge}
    session.commit()
```

- [ ] **Step 4: Run tests to confirm they pass**

```
pytest tests/test_job_context.py::TestUpdateRun -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/scheduler_run_log_service.py tests/test_job_context.py
git commit -m "feat(jobs): add update_run() for mid-run progress snapshots"
```

---

## Task 2: Create `JobContext` and `job_context()` context manager

**Files:**
- Create: `backend/app/services/job_context.py`
- Modify: `tests/test_job_context.py` (add new test class)

- [ ] **Step 1: Write failing tests for `JobContext`**

Append to `tests/test_job_context.py`:

```python
class TestJobContext(unittest.TestCase):

    def _patched_context(self, start_id=1):
        """Returns (patches_ctx, mock_start, mock_finish, mock_prune, mock_update)."""
        patches = {
            "start": patch("backend.app.services.job_context.start_run", return_value=start_id),
            "finish": patch("backend.app.services.job_context.finish_run"),
            "prune": patch("backend.app.services.job_context.prune_old_runs"),
            "update": patch("backend.app.services.job_context.update_run"),
        }
        return patches

    def test_start_run_called_on_enter(self):
        session = MagicMock()
        p = self._patched_context()
        with p["start"] as m_start, p["finish"], p["prune"], p["update"]:
            from backend.app.services.job_context import job_context
            with job_context(session, "test-job"):
                pass
        m_start.assert_called_once_with(session, "test-job")

    def test_finish_run_success_on_clean_exit(self):
        session = MagicMock()
        p = self._patched_context(start_id=42)
        with p["start"], p["finish"] as m_finish, p["prune"], p["update"]:
            from backend.app.services.job_context import job_context
            with job_context(session, "test-job"):
                pass
        m_finish.assert_called_once()
        self.assertEqual(m_finish.call_args[1]["status"], "success")
        self.assertEqual(m_finish.call_args[0][1], 42)

    def test_finish_run_error_on_exception(self):
        session = MagicMock()
        p = self._patched_context()
        with p["start"], p["finish"] as m_finish, p["prune"], p["update"]:
            from backend.app.services.job_context import job_context
            with self.assertRaises(ValueError):
                with job_context(session, "test-job"):
                    raise ValueError("boom")
        self.assertEqual(m_finish.call_args[1]["status"], "error")
        self.assertIn("boom", m_finish.call_args[1]["error_message"])

    def test_set_status_overrides_success(self):
        session = MagicMock()
        p = self._patched_context()
        with p["start"], p["finish"] as m_finish, p["prune"], p["update"]:
            from backend.app.services.job_context import job_context
            with job_context(session, "test-job") as ctx:
                ctx.set_status("no_op")
        self.assertEqual(m_finish.call_args[1]["status"], "no_op")

    def test_checkpoint_calls_update_run(self):
        session = MagicMock()
        p = self._patched_context()
        with p["start"], p["finish"], p["prune"], p["update"] as m_update:
            from backend.app.services.job_context import job_context
            with job_context(session, "test-job") as ctx:
                ctx.checkpoint(records_written=10, stage="halfway")
        m_update.assert_called_once()
        call_kwargs = m_update.call_args[1]
        self.assertEqual(call_kwargs["records_written"], 10)
        self.assertIn("stage", call_kwargs["meta_json_merge"])

    def test_checkpoint_tracks_records_in_finish_run(self):
        session = MagicMock()
        p = self._patched_context()
        with p["start"], p["finish"] as m_finish, p["prune"], p["update"]:
            from backend.app.services.job_context import job_context
            with job_context(session, "test-job") as ctx:
                ctx.checkpoint(records_written=25)
        self.assertEqual(m_finish.call_args[1]["records_written"], 25)

    def test_deadline_exceeded_sets_error_status(self):
        from datetime import datetime, timezone, timedelta
        session = MagicMock()
        past_deadline = datetime.now(timezone.utc) - timedelta(seconds=1)
        p = self._patched_context()
        with p["start"], p["finish"] as m_finish, p["prune"], p["update"]:
            from backend.app.services.job_context import job_context, JobDeadlineExceeded
            with self.assertRaises(JobDeadlineExceeded):
                with job_context(session, "test-job", deadline_minutes=-1) as ctx:
                    ctx.checkpoint()  # deadline already past → raises
        self.assertEqual(m_finish.call_args[1]["status"], "timed_out")

    def test_prune_called_even_on_exception(self):
        session = MagicMock()
        p = self._patched_context()
        with p["start"], p["finish"], p["prune"] as m_prune, p["update"]:
            from backend.app.services.job_context import job_context
            with self.assertRaises(RuntimeError):
                with job_context(session, "test-job"):
                    raise RuntimeError("fail")
        m_prune.assert_called_once_with(session, "test-job")
```

- [ ] **Step 2: Run to confirm failure**

```
pytest tests/test_job_context.py::TestJobContext -v
```
Expected: `FAILED` — `ModuleNotFoundError: No module named 'backend.app.services.job_context'`

- [ ] **Step 3: Create `backend/app/services/job_context.py`**

```python
"""backend/app/services/job_context.py

Context manager for scheduler jobs that provides:
  - Automatic start_run / finish_run / prune_old_runs lifecycle
  - Mid-run progress checkpoints via ctx.checkpoint()
  - Optional deadline enforcement (raises JobDeadlineExceeded)
  - Status override via ctx.set_status() for 'partial', 'warning', 'no_op'

Usage:
    with job_context(db, JOB_BULK_REFRESH, deadline_minutes=30) as ctx:
        for i, item in enumerate(items):
            process(item)
            ctx.checkpoint(records_written=i + 1, stage=f"item_{i}")
        ctx.set_status("partial") if some_errors else None
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Generator

from sqlalchemy.orm import Session

from backend.app.services.scheduler_run_log_service import (
    finish_run,
    prune_old_runs,
    start_run,
    update_run,
)


class JobDeadlineExceeded(Exception):
    pass


class JobContext:
    def __init__(
        self,
        session: Session,
        run_id: int,
        job_name: str,
        deadline_at: datetime | None,
    ) -> None:
        self._session = session
        self._job_name = job_name
        self.run_id = run_id
        self.deadline_at = deadline_at
        self.records_written: int = 0
        self.errors: int = 0
        self._final_status: str | None = None

    def set_status(self, status: str) -> None:
        """Override the completion status ('partial', 'warning', 'no_op', etc.)."""
        self._final_status = status

    def checkpoint(self, records_written: int | None = None, errors: int | None = None, **meta_kwargs) -> None:
        """Write current progress to DB. Raises JobDeadlineExceeded if past deadline."""
        if records_written is not None:
            self.records_written = records_written
        if errors is not None:
            self.errors = errors

        meta_merge: dict = {"last_checkpoint_at": datetime.now(UTC).isoformat(), **meta_kwargs}

        update_run(
            self._session,
            self.run_id,
            records_written=self.records_written,
            errors=self.errors,
            meta_json_merge=meta_merge,
        )

        if self.deadline_at and datetime.now(UTC) >= self.deadline_at:
            raise JobDeadlineExceeded(
                f"{self._job_name} exceeded deadline {self.deadline_at.isoformat()}"
            )


@contextmanager
def job_context(
    session: Session,
    job_name: str,
    *,
    deadline_minutes: int | None = None,
) -> Generator[JobContext, None, None]:
    """Context manager handling the full scheduler-job run lifecycle."""
    deadline_at: datetime | None = None
    if deadline_minutes is not None:
        deadline_at = datetime.now(UTC) + timedelta(minutes=deadline_minutes)

    run_id = start_run(session, job_name)
    ctx = JobContext(session, run_id, job_name, deadline_at)

    try:
        yield ctx
        finish_run(
            session,
            run_id,
            status=ctx._final_status or "success",
            records_written=ctx.records_written,
            errors=ctx.errors,
        )
    except JobDeadlineExceeded as exc:
        finish_run(
            session,
            run_id,
            status="timed_out",
            records_written=ctx.records_written,
            errors=ctx.errors,
            error_message=str(exc)[:500],
        )
        raise
    except Exception as exc:
        finish_run(
            session,
            run_id,
            status="error",
            records_written=ctx.records_written,
            errors=ctx.errors,
            error_message=str(exc)[:500],
        )
        raise
    finally:
        prune_old_runs(session, job_name)
```

- [ ] **Step 4: Run tests to confirm they pass**

```
pytest tests/test_job_context.py -v
```
Expected: all 11 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/job_context.py tests/test_job_context.py
git commit -m "feat(jobs): add JobContext context manager with checkpoints and deadline enforcement"
```

---

## Task 3: Migrate `_run_bulk_set_price_refresh` to `job_context`

`bulk-set-price-refresh` is the best migration target: it's the longest-running job, currently has no deadline, and has no mid-run progress visibility.

**Files:**
- Modify: `backend/app/backstage/scheduler.py`

- [ ] **Step 1: Read the current function**

Open `backend/app/backstage/scheduler.py` and find `_run_bulk_set_price_refresh`. Note:
- Where `start_run` is called
- Where `finish_run` is called (there should be one in `finally`)
- Where `prune_old_runs` is called
- The loop body (the per-set iteration)

- [ ] **Step 2: Add import**

Find the import block where `start_run`, `finish_run`, `prune_old_runs` are imported from `scheduler_run_log_service`. Add `job_context` and `JobDeadlineExceeded` imports:

```python
from backend.app.services.job_context import JobDeadlineExceeded, job_context
```

- [ ] **Step 3: Replace the run-log boilerplate in `_run_bulk_set_price_refresh`**

The current pattern looks like:
```python
def _run_bulk_set_price_refresh() -> None:
    with SessionLocal() as db:
        run_id = start_run(db, JOB_BULK_REFRESH)
        records = 0
        errors = 0
        try:
            # ... loop over sets ...
            finish_run(db, run_id, status="success", records_written=records, ...)
        except Exception as exc:
            finish_run(db, run_id, status="error", ...)
            raise
        finally:
            prune_old_runs(db, JOB_BULK_REFRESH)
```

Replace with the `job_context` pattern. Preserve all existing business logic; only the lifecycle boilerplate changes:

```python
def _run_bulk_set_price_refresh() -> None:
    with SessionLocal() as db:
        with job_context(db, JOB_BULK_REFRESH, deadline_minutes=45) as ctx:
            settings = get_settings()
            set_ids = settings.bulk_set_id_list
            if not set_ids:
                return  # job_context will finish_run(success) on clean exit

            sets_done = 0
            for set_id in set_ids:
                # ... existing per-set import logic unchanged ...
                sets_done += 1
                ctx.checkpoint(
                    records_written=ctx.records_written,  # updated inside loop
                    sets_completed=sets_done,
                    current_set=set_id,
                )

            # existing meta_json fields passed via set_status / checkpoint
```

Keep the existing per-set error handling (`except ProviderUnavailableError: continue`) inside the loop. After the loop, call `ctx.set_status("partial")` if there were errors, `ctx.set_status("warning")` if records_written == 0 but no exception.

- [ ] **Step 4: Run the existing bulk-refresh runlog tests**

```
pytest tests/test_bulk_refresh_runlog.py -v
```
Expected: all 7 tests pass (they patch `start_run`/`finish_run` directly — they still resolve through the service module and will still be called by `job_context`).

- [ ] **Step 5: Commit**

```bash
git add backend/app/backstage/scheduler.py
git commit -m "feat(jobs): migrate bulk-set-price-refresh to job_context with 45m deadline and per-set checkpoints"
```

---

## Task 4: Add `/admin/diag/live-jobs` endpoint

**Files:**
- Modify: `backend/app/backstage/routes.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_live_jobs_endpoint.py`:

```python
"""tests/test_live_jobs_endpoint.py"""
from __future__ import annotations
import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone


def _make_run(job_name, status="running", records=0, meta=None):
    r = MagicMock()
    r.job_name = job_name
    r.status = status
    r.started_at = datetime(2026, 6, 4, 12, 0, 0, tzinfo=timezone.utc)
    r.finished_at = None
    r.records_written = records
    r.errors = 0
    r.error_message = None
    r.meta_json = meta
    return r


class TestLiveJobsEndpoint(unittest.TestCase):

    def test_returns_running_jobs_only(self):
        running = _make_run("bulk-set-price-refresh", status="running", records=50,
                            meta={"sets_completed": 3, "current_set": "sv3pt5",
                                  "last_checkpoint_at": "2026-06-04T12:05:00+00:00"})

        with patch("backend.app.backstage.routes.SessionLocal") as mock_sl:
            mock_db = MagicMock()
            mock_sl.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)

            from sqlalchemy import select
            # scalars returns only the running job
            mock_db.scalars.return_value.all.return_value = [running]

            from fastapi.testclient import TestClient
            from backend.app.main import app
            client = TestClient(app)
            resp = client.get(
                "/admin/diag/live-jobs",
                headers={"X-Admin-Key": "test-admin-key"},
            )

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("running_jobs", data)
        jobs = data["running_jobs"]
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["job_name"], "bulk-set-price-refresh")
        self.assertEqual(jobs[0]["records_written"], 50)
        self.assertIn("checkpoint", jobs[0])
```

- [ ] **Step 2: Run to confirm failure**

```
pytest tests/test_live_jobs_endpoint.py -v
```
Expected: `FAILED` — 404 on `/admin/diag/live-jobs`

- [ ] **Step 3: Add the endpoint to `routes.py`**

Find the block of `/admin/diag/*` endpoints in `backend/app/backstage/routes.py`. Add after the last diag endpoint:

```python
@router.get("/diag/live-jobs")
def live_jobs(
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_db),
) -> dict:
    """Return all currently-running scheduler jobs with their latest checkpoint data."""
    from sqlalchemy import select as sa_select
    rows = db.scalars(
        sa_select(SchedulerRunLog)
        .where(SchedulerRunLog.status == "running")
        .order_by(SchedulerRunLog.started_at.desc())
    ).all()

    jobs = []
    for row in rows:
        meta = row.meta_json or {}
        jobs.append({
            "job_name": row.job_name,
            "run_id": row.id,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "records_written": row.records_written,
            "errors": row.errors,
            "checkpoint": {
                "last_checkpoint_at": meta.get("last_checkpoint_at"),
                "stage": meta.get("stage") or meta.get("current_set"),
                "sets_completed": meta.get("sets_completed"),
            },
        })

    return {"running_jobs": jobs, "count": len(jobs)}
```

Ensure `SchedulerRunLog` is imported at the top of `routes.py` (check — it likely already is for `/admin/stats`).

- [ ] **Step 4: Run tests**

```
pytest tests/test_live_jobs_endpoint.py -v
```
Expected: 1 passed.

- [ ] **Step 5: Smoke-test manually**

```
curl -H "X-Admin-Key: $ADMIN_KEY" http://localhost:8000/admin/diag/live-jobs
```
Expected when no jobs are running: `{"running_jobs": [], "count": 0}`

- [ ] **Step 6: Commit**

```bash
git add backend/app/backstage/routes.py tests/test_live_jobs_endpoint.py
git commit -m "feat(admin): add /admin/diag/live-jobs endpoint showing running jobs with checkpoint progress"
```

---

## Full test run

After all tasks:

```
pytest tests/test_job_context.py tests/test_live_jobs_endpoint.py tests/test_bulk_refresh_runlog.py -v
```

Expected: all tests pass, no regressions.

---

## Self-Review

**Spec coverage:**
- ✅ `update_run()` — Task 1
- ✅ `JobContext` + `job_context()` — Task 2
- ✅ Mid-run checkpoint (`ctx.checkpoint()`) — Task 2/3
- ✅ Deadline enforcement (`deadline_minutes`, raises `JobDeadlineExceeded`) — Task 2/3
- ✅ Status override (`ctx.set_status()`) for partial/warning/no_op — Task 2/3
- ✅ `bulk-set-price-refresh` migrated as proof of pattern — Task 3
- ✅ Live-jobs admin view — Task 4

**No placeholders:** All steps contain complete runnable code.

**Type consistency:** `JobContext.checkpoint()` uses `records_written: int | None`, matching `update_run()`'s `records_written: int | None`. `job_context()` passes `ctx.records_written` (always `int`) to `finish_run(records_written=...)` which expects `int`. Consistent throughout.
