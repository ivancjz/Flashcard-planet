# PR-B implementation packet — TASK-106: one-shot pre-fix repeat cleanup

Date: 2026-05-08 (pre-written; do not start until PR-A 24h verification gate passes)
Plan reference: `BACKLOG.md` §2 TASK-106 (to be added on PR-A merge); CLAUDE.md §7 Issue D
Locked decisions: (B) path; immediate ~2.5 GB recovery via batched DELETE, deletes only pre-fix repeat rows (`previous_label = label AND computed_at < <fix-deploy-time>`); transition rows preserved.

Pre-flight verification (sandbox-readable, HEAD `12668ef`):
- PR-A (TASK-105) merged: `99fc86f`, `12668ef` ✅
- 24h verification gate: **NOT YET CONFIRMED** at packet-write time. Do not execute PR-B until PR-A's second daily run shows clean.
- `_append_history` transition guard active in production (commit `78bd30b`).
- Existing `/admin/trigger/*` endpoints follow simple POST + `Depends(require_admin_key)` shape (e.g., `delete-future-timestamps` at `routes.py:993`).

Branch off main:
```
git checkout main && git pull
git checkout -b feat/task-106-prefix-history-cleanup
```

Two commits.

---

## Commit 1 — `feat(admin): one-shot pre-fix repeat cleanup endpoint (TASK-106)`

**Concern:** new admin trigger that DELETEs pre-fix repeat rows in batches. Caller-driven loop (one batch per call), avoiding HTTP timeout limits on Railway's edge.

### 1.1 — Endpoint at `backend/app/backstage/routes.py`

Add to the existing `/trigger/*` block. Place near `delete-future-timestamps` (line ~993) for grouping.

```python
@router.post("/trigger/cleanup-prefix-history")
def admin_cleanup_prefix_history(
    before: str = Query(..., description="ISO timestamp; rows older than this are eligible (use 78bd30b deploy time: 2026-05-06T10:00:00Z)"),
    dry_run: bool = Query(default=False, description="If true, return rows_matched without deleting"),
    batch_size: int = Query(default=100000, ge=1000, le=500000),
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_database),
):
    """One-shot DELETE of pre-fix repeat rows in asset_signal_history (TASK-106).

    Phase 2 of Issue D fix: the transition guard (PR-A, commit 78bd30b) stopped
    the bleeding, but the 5.7M pre-fix rows already in the table won't naturally
    age out for 75+ days under the 90-day retention. This endpoint deletes the
    99%-repeat-row subset of that pre-fix accumulation to reclaim ~2.5 GB
    immediately.

    Caller protocol:
      1. Call with dry_run=true to see rows_matched (full count).
      2. Loop calling without dry_run until rows_deleted=0.
      3. Final dry_run=true to confirm rows_matched=0.

    Filter (all three must hold for a row to be deleted):
      - previous_label IS NOT NULL  (don't touch first-write rows)
      - previous_label = label      (only repeats — true transitions stay)
      - computed_at < :before       (only pre-fix; defends against any
                                     post-fix repeat that shouldn't exist)

    Returns scheduler_run_log-shape JSON for ad-hoc operator audit; logger.info
    captures the same on each call for Railway log review.
    """
    import time as _time
    start = _time.monotonic()

    if dry_run:
        rows_matched = db.execute(
            text("""
                SELECT COUNT(*) FROM asset_signal_history
                WHERE previous_label IS NOT NULL
                  AND previous_label = label
                  AND computed_at < :before::timestamptz
            """),
            {"before": before},
        ).scalar()
        duration = round(_time.monotonic() - start, 2)
        logger.info(
            "cleanup-prefix-history dry-run: matched=%d before=%s duration=%.2fs",
            rows_matched, before, duration,
        )
        return {
            "ok": True,
            "dry_run": True,
            "rows_matched": rows_matched or 0,
            "before": before,
            "duration_seconds": duration,
        }

    result = db.execute(
        text("""
            DELETE FROM asset_signal_history
            WHERE id IN (
                SELECT id FROM asset_signal_history
                WHERE previous_label IS NOT NULL
                  AND previous_label = label
                  AND computed_at < :before::timestamptz
                LIMIT :batch
            )
        """),
        {"before": before, "batch": batch_size},
    )
    db.commit()
    rows_deleted = result.rowcount or 0
    duration = round(_time.monotonic() - start, 2)

    logger.info(
        "cleanup-prefix-history batch: deleted=%d batch_size=%d before=%s duration=%.2fs",
        rows_deleted, batch_size, before, duration,
    )

    return {
        "ok": True,
        "dry_run": False,
        "rows_deleted": rows_deleted,
        "batch_size": batch_size,
        "before": before,
        "duration_seconds": duration,
    }
```

**Why batched + caller-driven loop instead of one big DELETE:**
- Railway's HTTP edge has a request timeout (~30-60s typical). A single DELETE on 5.7M rows on a Hobby Postgres without index on `computed_at` would take minutes — connection drops, work continues server-side, but operator loses visibility.
- One transaction over 5.7M rows holds locks long enough to stall concurrent signal-sweep INSERTs. Batches of 100k commit fast, lock briefly.
- The caller loop pattern is the simplest fit for the existing `/admin/trigger/*` shape (synchronous endpoints, no background tasks, no SSE).

**Why required `before` query param (no default):**
- Forces the operator to pass the exact fix-deploy timestamp explicitly; no risk of the default drifting and accidentally deleting post-fix data later.
- Recommended value: `2026-05-06T10:00:00Z` (78bd30b deploy was 2026-05-06 09:58 UTC + small buffer).

**Why `batch_size` capped at 500k:**
- 500k DELETE in one batch on Hobby Postgres ≈ 60-90s with no `computed_at` index. Beyond that risks timeout. Operator can override down to 1k for ultra-conservative; 100k is a tested middle ground.

### 1.2 — No `_STARTUP_DELAY` / `_monitored_jobs` entries

This is a one-shot, NOT a scheduled job. Doesn't go in scheduler.py. Doesn't write `scheduler_run_log` (per existing trigger pattern at routes.py:993). Audit comes from `logger.info` calls captured in Railway logs + the operator's terminal output during the loop.

### 1.3 — No new env var

Hard-coded knobs (batch_size default 100k, the timestamp passed per-invocation) — no production-time configuration needed.

### Verified by

- `pytest tests/test_admin_routes.py -k cleanup_prefix -v` (will work after commit 2 adds tests).
- Manual curl with `dry_run=true` on production: returns `rows_matched: ~5500000`. Compare against `SELECT COUNT(*) FROM asset_signal_history WHERE previous_label IS NOT NULL AND previous_label = label AND computed_at < '2026-05-06 10:00:00 UTC'` directly via `railway run psql` — should match.
- Running once with `dry_run=false` and `batch_size=1000` deletes exactly 1000 rows (sample run before the full loop).

**Commit message:**

```
feat(admin): one-shot pre-fix repeat cleanup endpoint (TASK-106)

PR-B Phase 2 of Issue D fix. Phase 1 (transition guard, commit 78bd30b)
stopped the bleeding at 1500 rows/day; PR-A (TASK-105 retention prune)
caps growth via daily DELETE > 90d. But the 5.7M pre-fix rows
accumulated 2026-04-19 through 2026-05-06 won't naturally age out for
75 days — this endpoint deletes them now.

POST /admin/trigger/cleanup-prefix-history
  Required: before (ISO ts of fix-deploy: 2026-05-06T10:00:00Z)
  Optional: dry_run=true|false (default false)
            batch_size=1000..500000 (default 100000)

Filter (all three must hold for delete):
  - previous_label IS NOT NULL
  - previous_label = label
  - computed_at < :before

This filter defends against ever touching post-fix data: any row
written after 78bd30b deploy by definition has previous_label != label
(the guard early-returns on equality), so the second filter
exclude-by-design any post-fix row even if the timestamp filter were
broken.

Caller-driven loop pattern (rather than one large DELETE) keeps each
HTTP call under Railway's edge timeout. logger.info per call captures
audit trail in Railway logs; no scheduler_run_log entry (matches
existing /admin/trigger/* pattern at routes.py:993 — these are manual
triggers, not scheduled jobs).

Verified:
- Build: pytest tests/test_admin_routes.py -k cleanup_prefix => pass
- Production dry-run on /admin/trigger/cleanup-prefix-history?dry_run=true:
  returns rows_matched ~= SQL SELECT COUNT verification
- Sample real run with batch_size=1000: deletes exactly 1000 rows
```

---

## Commit 2 — `test(admin): coverage for cleanup-prefix-history endpoint`

**Concern:** test the filter precision (only delete pre-fix repeats), batch behaviour, dry-run mode, idempotency.

**File:** `tests/test_cleanup_prefix_history.py` (new). Mirror the conftest fixture conventions used in existing `tests/test_signal_history_prune.py` (created in PR-A).

```python
"""Tests for /admin/trigger/cleanup-prefix-history (TASK-106)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.main import app
from backend.app.models.asset_signal_history import AssetSignalHistory


FIX_DEPLOY_TIME = "2026-05-06T10:00:00Z"
PRE_FIX = datetime(2026, 4, 25, tzinfo=timezone.utc)
POST_FIX = datetime(2026, 5, 7, tzinfo=timezone.utc)


def _seed(db, *, asset_id, prev, label, computed_at):
    """Helper: insert one signal_history row with explicit attrs."""
    db.add(AssetSignalHistory(
        asset_id=asset_id,
        label=label,
        previous_label=prev,
        confidence=0.9,
        price_delta_pct=0.0,
        liquidity_score=0.5,
        prediction=None,
        computed_at=computed_at,
        signal_context={},
    ))
    db.commit()


@pytest.fixture
def admin_client():
    """TestClient with admin auth header pre-set."""
    client = TestClient(app)
    client.headers.update({"X-Admin-Key": "test-admin-key"})  # set ADMIN_KEY env in conftest
    return client


def test_dry_run_returns_count_without_deleting(admin_client, db_session):
    _seed(db_session, asset_id="aaaa-1", prev="IDLE",  label="IDLE",  computed_at=PRE_FIX)  # repeat, pre-fix → eligible
    _seed(db_session, asset_id="aaaa-2", prev="MOVE",  label="WATCH", computed_at=PRE_FIX)  # transition, pre-fix → keep
    _seed(db_session, asset_id="aaaa-3", prev=None,    label="IDLE",  computed_at=PRE_FIX)  # first-write, pre-fix → keep

    r = admin_client.post(
        "/admin/trigger/cleanup-prefix-history",
        params={"before": FIX_DEPLOY_TIME, "dry_run": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["dry_run"] is True
    assert body["rows_matched"] == 1   # only the IDLE→IDLE repeat

    # All 3 rows still present
    remaining = db_session.execute(select(AssetSignalHistory.asset_id)).scalars().all()
    assert set(remaining) == {"aaaa-1", "aaaa-2", "aaaa-3"}


def test_non_dry_run_deletes_only_pre_fix_repeats(admin_client, db_session):
    # Three categories of "should keep"
    _seed(db_session, asset_id="bbbb-1", prev="MOVE",  label="WATCH", computed_at=PRE_FIX)   # transition, pre-fix
    _seed(db_session, asset_id="bbbb-2", prev=None,    label="IDLE",  computed_at=PRE_FIX)   # first-write, pre-fix
    _seed(db_session, asset_id="bbbb-3", prev="IDLE",  label="IDLE",  computed_at=POST_FIX)  # repeat but post-fix
    # One "should delete"
    _seed(db_session, asset_id="bbbb-4", prev="IDLE",  label="IDLE",  computed_at=PRE_FIX)   # repeat, pre-fix → delete

    r = admin_client.post(
        "/admin/trigger/cleanup-prefix-history",
        params={"before": FIX_DEPLOY_TIME},
    )
    assert r.status_code == 200
    assert r.json()["rows_deleted"] == 1

    remaining = db_session.execute(select(AssetSignalHistory.asset_id)).scalars().all()
    assert set(remaining) == {"bbbb-1", "bbbb-2", "bbbb-3"}


def test_batch_size_caps_per_call_deletes(admin_client, db_session):
    """Five eligible rows + batch_size=2 → 2 deleted per call, takes 3 calls to drain."""
    for i in range(5):
        _seed(db_session, asset_id=f"cccc-{i}", prev="IDLE", label="IDLE", computed_at=PRE_FIX)

    deletes = []
    for _ in range(4):  # one extra call to confirm zero
        r = admin_client.post(
            "/admin/trigger/cleanup-prefix-history",
            params={"before": FIX_DEPLOY_TIME, "batch_size": 2},
        )
        deletes.append(r.json()["rows_deleted"])

    assert deletes == [2, 2, 1, 0]


def test_idempotent_after_drain(admin_client, db_session):
    """Calling once empty matches returns rows_deleted=0 cleanly."""
    _seed(db_session, asset_id="dddd-1", prev="MOVE", label="WATCH", computed_at=PRE_FIX)  # not eligible

    r = admin_client.post(
        "/admin/trigger/cleanup-prefix-history",
        params={"before": FIX_DEPLOY_TIME},
    )
    assert r.status_code == 200
    assert r.json()["rows_deleted"] == 0


def test_before_param_required(admin_client):
    """Missing 'before' returns 422."""
    r = admin_client.post("/admin/trigger/cleanup-prefix-history")
    assert r.status_code == 422


def test_admin_key_required(db_session):
    """Endpoint rejects without X-Admin-Key."""
    client = TestClient(app)
    r = client.post(
        "/admin/trigger/cleanup-prefix-history",
        params={"before": FIX_DEPLOY_TIME},
    )
    assert r.status_code in (401, 403)
```

Six tests covering the meaningful behaviours: dry-run / filter precision / batching / idempotency / param validation / auth.

**Verified by:**
- `pytest tests/test_cleanup_prefix_history.py -v` — 6/6 pass.
- `pytest tests/` — no regressions.

**Commit message:**

```
test(admin): coverage for cleanup-prefix-history endpoint

6 tests covering:
  1. dry_run=true returns rows_matched without DELETE
  2. Filter precision: only pre-fix repeat rows deleted (transitions
     kept, first-writes kept, post-fix repeats kept-by-date-filter)
  3. batch_size correctly caps per-call deletions
  4. Idempotent after drain (rows_deleted=0 returns cleanly)
  5. before query param required (422 without it)
  6. require_admin_key gate (401/403 without X-Admin-Key)

Mirrors test pattern from tests/test_signal_history_prune.py (PR-A).

Verified:
- pytest tests/test_cleanup_prefix_history.py: 6 passed
- pytest tests/: no regressions
```

---

## Operator runbook (PR description body)

**This goes in the PR description, NOT in the codebase.** The runbook is the operational protocol; codex reviews the implementation, the operator follows the runbook to actually run it on production after merge.

```markdown
## Production runbook

After PR-B is merged and Railway deploy is green:

### Step 1: Capture baseline

```bash
KEY="$ADMIN_KEY"  # from password manager
URL="https://flashcard-planet.up.railway.app"

# Pre-cleanup baseline
curl -s -H "X-Admin-Key: $KEY" "$URL/admin/diag/signal-history-stats?days=14" | jq
# Note: total rows in asset_signal_history before cleanup

railway run psql $DATABASE_URL -c "
  SELECT
    COUNT(*) AS total_rows,
    pg_size_pretty(pg_total_relation_size('asset_signal_history')) AS table_size,
    MIN(computed_at) AS oldest, MAX(computed_at) AS newest
  FROM asset_signal_history;
"
# Expected baseline: ~5,700,000 rows, ~2,600 MB, oldest 2026-04-19, newest 2026-05-08
```

### Step 2: Dry-run

```bash
curl -s -X POST -H "X-Admin-Key: $KEY" \
  "$URL/admin/trigger/cleanup-prefix-history?dry_run=true&before=2026-05-06T10:00:00Z" | jq
# Expected: { "rows_matched": ~5500000, "duration_seconds": ~30 }
```

If `rows_matched` is wildly different from ~5.5M (>10x off either way), STOP and investigate before proceeding. Likely cause: `before` timestamp wrong, or PR-A's transition guard isn't working as believed.

### Step 3: Drain loop

```bash
TOTAL=0
START=$(date +%s)
while true; do
  R=$(curl -s -X POST -H "X-Admin-Key: $KEY" \
    "$URL/admin/trigger/cleanup-prefix-history?before=2026-05-06T10:00:00Z&batch_size=100000")
  D=$(echo "$R" | jq -r '.rows_deleted')
  T=$(echo "$R" | jq -r '.duration_seconds')
  TOTAL=$((TOTAL + D))
  echo "$(date -u +%H:%M:%S) deleted=$D in ${T}s total=$TOTAL"
  if [ "$D" = "0" ]; then break; fi
  sleep 1
done
END=$(date +%s)
echo "Drain complete: $TOTAL rows in $((END - START))s"
# Expected: ~5,500,000 rows in ~15-30 minutes
```

### Step 4: Verify drained

```bash
curl -s -X POST -H "X-Admin-Key: $KEY" \
  "$URL/admin/trigger/cleanup-prefix-history?dry_run=true&before=2026-05-06T10:00:00Z" | jq
# Expected: { "rows_matched": 0, ... }
```

### Step 5: Confirm space reclaimed

```bash
railway run psql $DATABASE_URL -c "
  SELECT
    COUNT(*) AS total_rows,
    pg_size_pretty(pg_total_relation_size('asset_signal_history')) AS table_size
  FROM asset_signal_history;
"
# Expected: row count drops from ~5.7M to ~200k; size drops from ~2.6 GB to ~150 MB
```

Railway → Postgres → Storage tab should show DB total drop from ~3.3 GB to ~750 MB within minutes.

If size doesn't drop: Postgres needs `VACUUM FULL` or autovacuum to reclaim disk after a large DELETE. Run:

```bash
railway run psql $DATABASE_URL -c "VACUUM (ANALYZE, VERBOSE) asset_signal_history;"
```

(Note: `VACUUM FULL` rewrites the table and locks it briefly; only run if regular `VACUUM` doesn't reclaim space within ~10 minutes.)
```

---

## Sequencing constraint

**DO NOT MERGE PR-B until PR-A's 24h verification gate passes.** Specifically:
- PR-A's 2026-05-09 ~15:41 UTC scheduled run must show `status: success, rows_deleted: 0` (matching first-run pattern).
- If second run shows anything different (errors, unexpected delete count, missing run-log row), pause PR-B and investigate.

This sequencing protects against Phase 2's effectiveness depending on Phase 1's correctness — if Phase 1 has a hidden bug, doing one-shot cleanup first masks it.

---

## After PR-B merges + runbook completes

1. Update `BACKLOG.md`:
   - Move TASK-105 → §3 Completed
   - Move TASK-106 → §3 Completed
2. Update `CLAUDE.md` §7:
   - Issue D paragraph → "**Resolved 2026-05-09 (Phase 2 PR-B `<hash>`):** ..."
   - Move from active-problems list to a "**Lesson:** transition-only history writes are the canonical pattern" entry, OR retire entirely if the lesson lives in PR-A's commit message
3. Optional follow-up TASK-107 (low priority): add an index on `asset_signal_history(computed_at)` to speed future prune runs from 12s → <100ms. Becomes meaningful once table re-grows past ~1M rows; for now (~200k post-cleanup) the seq scan is trivial.

---

## Open questions for the operator

**(Q1) Default `batch_size`: 100,000 the right floor?**
- Lower (e.g., 50k) → more batches, slower wall-clock, less pressure per batch.
- Higher (e.g., 250k) → fewer batches, faster wall-clock, longer per-batch lock.
- Default 100k is a defensible middle ground; operator can override per call. Default if you don't answer: 100k.

**(Q2) `VACUUM FULL` plan if disk doesn't auto-reclaim?**
- After a 5.5M-row DELETE, Postgres may not return disk to the OS until autovacuum runs. Default autovacuum on Railway should handle this within hours.
- If immediate space recovery is needed: `VACUUM FULL asset_signal_history` rewrites the table compactly. Locks the table for the duration (~minutes for a 200k-row table after cleanup).
- Safe to run during maintenance window; signal-sweep job INSERTs would block briefly but not fail.
- Default if you don't answer: skip VACUUM FULL; trust autovacuum; revisit if storage tab doesn't drop within 24h.
