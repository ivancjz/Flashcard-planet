# Bulk-Refresh 429 Fix + eBay Duration Canary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the 2026-05-04 throughput-collapse incident by applying PR #12's 60-second Retry-After cap to the bulk-refresh code path, add a forward-looking eBay fast-fail canary alert, and rename Issue B in CLAUDE.md.

**Architecture:** `cap_and_backoff` is extracted as a public function in `pokemon_tcg.py` — the module that already owns `MAX_FETCH_ATTEMPTS`, `RETRYABLE_STATUS_CODES`, and `_compute_retry_delay`. Both callers (`pokemon_tcg.py` itself via `_compute_retry_delay`, and `import_pokemon_cards.py` via `_sleep_for_retry`) import from this single location. The eBay canary is a new SQL check inside the existing `_send_heartbeat` function, matching the pattern of the existing `get_zero_output_jobs` alert.

**Tech Stack:** Python 3.13, SQLAlchemy 2, APScheduler, httpx (scheduled-ingest path), requests (bulk-refresh path), unittest + patch.

---

## Precondition evidence (must appear verbatim in PR description)

**PR #12 fix (scheduled-ingestion path — `pokemon_tcg.py`):**
```python
def _compute_retry_delay(response: httpx.Response | None, attempt: int) -> float:
    if response is not None:
        retry_after = _parse_retry_after(response)
        if retry_after is not None:
            return min(retry_after, 60.0)   # ← 60-second cap
    fallback = [2.0, 5.0, 15.0]
    return fallback[min(attempt - 1, len(fallback) - 1)]
```

**Bulk-refresh path (pre-fix — `import_pokemon_cards.py`):**
```python
def _sleep_for_retry(self, response: Response | None, attempt: int) -> None:
    retry_after = self._parse_retry_after_seconds(response)
    delay = retry_after if retry_after is not None else min(2 ** (attempt - 1), 8)
    # ← NO cap on retry_after; if API sends Retry-After: 3600 → sleeps 3600s
    time.sleep(delay)
```

Gap: no 60-second cap on Retry-After. With 25 sets × multiple pages × 3 retries × up to 3600s each = observed ~9,550s avg on 2026-05-04.

---

## File map

| File | Action | What changes |
|------|--------|--------------|
| `backend/app/ingestion/pokemon_tcg.py` | Modify | Add `cap_and_backoff` (public), update `_compute_retry_delay` to call it |
| `scripts/import_pokemon_cards.py` | Modify | Import `cap_and_backoff`, use it in `_sleep_for_retry` |
| `backend/app/backstage/scheduler.py` | Modify | Add eBay duration canary block in `_send_heartbeat` |
| `CLAUDE.md` | Modify | Rename Issue B, add two backlog notes |
| `tests/test_cap_and_backoff.py` | Create | Unit tests for `cap_and_backoff` (3 symmetric cases) |
| `tests/test_bulk_refresh_429.py` | Create | 429 cascade test for bulk-refresh path |
| `tests/test_ebay_duration_canary.py` | Create | Unit tests for eBay fast-fail canary (3 cases) |

---

## Task 1: CLAUDE.md — rename Issue B and add backlog notes

No tests. Single commit.

**Files:** `CLAUDE.md`

- [ ] **Step 1: Find and rename Issue B**

In `CLAUDE.md` §7 (Current state anchors) or §6 (Lessons), find the entry for Issue B. Replace:

```
"3 days no Pokémon data"
```

with:

```
"2026-05-04 throughput collapse from 429 storm in _run_bulk_set_price_refresh (PR #12 fix coverage gap)"
```

Mark it as resolved pending 48h post-merge SQL confirmation.

- [ ] **Step 2: Add two backlog notes**

In `CLAUDE.md` find the backlog section (or add to §7 Known open problems). Add:

```
- Backlog: Audit alert SQL that produced the original "3 days no data" wording 
  for Issue B — likely watching last_priced_at instead of records_written. 
  Do NOT conflate with the 429 fix. Separate PR.
- Backlog: PokemonTCGImporter lives in scripts/import_pokemon_cards.py but is 
  called by production scheduler. Move to backend/app/ingestion/ when convenient.
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): rename Issue B to 2026-05-04 429 storm; add two backlog notes"
```

---

## Task 2: Add `cap_and_backoff` to `pokemon_tcg.py` (TDD)

**Files:**
- Modify: `backend/app/ingestion/pokemon_tcg.py`
- Create: `tests/test_cap_and_backoff.py`

- [ ] **Step 1: Write three failing unit tests**

Create `tests/test_cap_and_backoff.py`:

```python
"""
Unit tests for cap_and_backoff — the shared retry-delay helper in pokemon_tcg.py.

Three symmetric cases matching PR #12's original helper tests:
  (i)  Retry-After present and within cap → use it directly
  (ii) Retry-After present but exceeds cap → clamp to 60.0
  (iii) No Retry-After → exponential fallback
"""
import unittest
from backend.app.ingestion.pokemon_tcg import cap_and_backoff


class CapAndBackoffTests(unittest.TestCase):

    def test_retry_after_within_cap_returned_as_is(self):
        """Retry-After of 30s is below the 60s cap — return it unchanged."""
        self.assertEqual(cap_and_backoff(30.0, attempt=1), 30.0)

    def test_retry_after_exceeds_cap_clamped_to_60(self):
        """Retry-After of 3600s (1h) must be clamped to 60.0."""
        self.assertEqual(cap_and_backoff(3600.0, attempt=1), 60.0)

    def test_no_retry_after_uses_fallback_sequence(self):
        """No Retry-After → fallback delays [2.0, 5.0, 15.0] indexed by attempt."""
        self.assertEqual(cap_and_backoff(None, attempt=1), 2.0)
        self.assertEqual(cap_and_backoff(None, attempt=2), 5.0)
        self.assertEqual(cap_and_backoff(None, attempt=3), 15.0)

    def test_attempt_zero_clamped_to_first_fallback(self):
        """attempt=0 is invalid but must not raise or return a garbage index."""
        self.assertEqual(cap_and_backoff(None, attempt=0), 2.0)

    def test_attempt_beyond_range_clamped_to_last_fallback(self):
        """attempt=99 must not raise — clamp to last fallback (15.0)."""
        self.assertEqual(cap_and_backoff(None, attempt=99), 15.0)
```

- [ ] **Step 2: Run tests — confirm ImportError (function doesn't exist yet)**

```bash
cd c:\Flashcard-planet
python -m pytest tests/test_cap_and_backoff.py -v 2>&1 | head -20
```
Expected: `ImportError: cannot import name 'cap_and_backoff'`

- [ ] **Step 3: Add `cap_and_backoff` to `pokemon_tcg.py`**

In `backend/app/ingestion/pokemon_tcg.py`, add this function immediately before `_parse_retry_after` (keep related helpers together):

```python
def cap_and_backoff(retry_after_secs: float | None, attempt: int) -> float:
    """Return seconds to sleep before a retry of a Pokemon TCG API call.

    Caps Retry-After at 60 s — prevents a single bad header from stalling a run
    for hours. The 60 s and [2.0, 5.0, 15.0] values were tuned in PR #12 against
    observed Pokemon TCG API behaviour. Do not import this for other APIs without
    verifying their rate-limit semantics match.

    Args:
        retry_after_secs: parsed value of the Retry-After header, or None.
        attempt: 1-based retry attempt number (1 = first retry).
    """
    if retry_after_secs is not None:
        return min(retry_after_secs, 60.0)
    idx = min(max(attempt - 1, 0), 2)
    return [2.0, 5.0, 15.0][idx]
```

- [ ] **Step 4: Update `_compute_retry_delay` to delegate to `cap_and_backoff`**

In the same file, replace the body of `_compute_retry_delay`:

```python
def _compute_retry_delay(response: httpx.Response | None, attempt: int) -> float:
    """Prefer Retry-After header if present, otherwise exponential backoff."""
    retry_after_secs: float | None = None
    if response is not None:
        retry_after_secs = _parse_retry_after(response)
    return cap_and_backoff(retry_after_secs, attempt)
```

- [ ] **Step 5: Run tests — confirm all pass**

```bash
python -m pytest tests/test_cap_and_backoff.py -v
```
Expected: 5 tests PASS.

- [ ] **Step 6: Run full test suite — confirm no regressions**

```bash
python -m pytest tests/ -x -q 2>&1 | tail -20
```
Expected: existing tests pass. Note any pre-existing failures.

- [ ] **Step 7: Commit**

```bash
git add backend/app/ingestion/pokemon_tcg.py tests/test_cap_and_backoff.py
git commit -m "refactor(pokemon-tcg): extract cap_and_backoff as shared public helper

cap_and_backoff centralises the 60-second Retry-After cap and [2.0, 5.0, 15.0]
fallback sequence from PR #12. _compute_retry_delay now delegates to it.
Enables import_pokemon_cards.py to reuse the same logic without duplication.

Verified: 5 unit tests added and passing."
```

---

## Task 3: Apply `cap_and_backoff` to bulk-refresh path (TDD)

**Files:**
- Modify: `scripts/import_pokemon_cards.py`
- Create: `tests/test_bulk_refresh_429.py`

- [ ] **Step 1: Write failing test — 429 cascade terminates cleanly**

Create `tests/test_bulk_refresh_429.py`:

```python
"""
tests/test_bulk_refresh_429.py

Regression test for 2026-05-04: _run_bulk_set_price_refresh must not retry
a Retry-After: 3600 header for the full 3600s. The cap must limit each delay
to ≤ 60s and the job must write status='error' (not retry-exhaust for hours).

Tests the _sleep_for_retry behaviour directly — avoids spinning up the full
scheduler or hitting the real API.
"""
import unittest
from unittest.mock import MagicMock, patch


class BulkRefreshCapTests(unittest.TestCase):

    def _make_response(self, retry_after: str | None) -> MagicMock:
        r = MagicMock()
        r.headers = {"Retry-After": retry_after} if retry_after else {}
        return r

    def test_retry_after_3600_capped_at_60(self):
        """_sleep_for_retry must not sleep longer than 60s even with Retry-After: 3600."""
        from scripts.import_pokemon_cards import PokemonTCGImporter

        importer = PokemonTCGImporter.__new__(PokemonTCGImporter)
        response = self._make_response("3600")

        with patch("scripts.import_pokemon_cards.time") as mock_time:
            importer._sleep_for_retry(response, attempt=1)
            slept = mock_time.sleep.call_args[0][0]

        self.assertLessEqual(slept, 60.0, f"sleep was {slept}s — Retry-After cap not applied")

    def test_retry_after_30_passed_through(self):
        """Retry-After: 30 is within the cap — sleep exactly 30s."""
        from scripts.import_pokemon_cards import PokemonTCGImporter

        importer = PokemonTCGImporter.__new__(PokemonTCGImporter)
        response = self._make_response("30")

        with patch("scripts.import_pokemon_cards.time") as mock_time:
            importer._sleep_for_retry(response, attempt=1)
            slept = mock_time.sleep.call_args[0][0]

        self.assertAlmostEqual(slept, 30.0)

    def test_no_retry_after_uses_fallback(self):
        """Without Retry-After header, use the [2.0, 5.0, 15.0] fallback sequence."""
        from scripts.import_pokemon_cards import PokemonTCGImporter

        importer = PokemonTCGImporter.__new__(PokemonTCGImporter)
        response = self._make_response(None)

        with patch("scripts.import_pokemon_cards.time") as mock_time:
            importer._sleep_for_retry(response, attempt=2)
            slept = mock_time.sleep.call_args[0][0]

        self.assertAlmostEqual(slept, 5.0)
```

- [ ] **Step 2: Run tests — confirm failure**

```bash
python -m pytest tests/test_bulk_refresh_429.py::BulkRefreshCapTests::test_retry_after_3600_capped_at_60 -v
```
Expected: FAIL — `slept` is 3600.0, not ≤ 60.0.

- [ ] **Step 3: Update imports in `import_pokemon_cards.py`**

Near the top of `scripts/import_pokemon_cards.py`, find the existing import block that imports from `pokemon_tcg`:

```python
from backend.app.ingestion.pokemon_tcg import (
    MAX_FETCH_ATTEMPTS,
    RETRYABLE_STATUS_CODES,
)
```

Add `cap_and_backoff`:

```python
from backend.app.ingestion.pokemon_tcg import (
    MAX_FETCH_ATTEMPTS,
    RETRYABLE_STATUS_CODES,
    cap_and_backoff,
)
```

- [ ] **Step 4: Update `_sleep_for_retry` to use `cap_and_backoff`**

In `scripts/import_pokemon_cards.py`, replace the `_sleep_for_retry` method body:

```python
def _sleep_for_retry(self, response: Response | None, attempt: int) -> None:
    retry_after_secs = self._parse_retry_after_seconds(response)
    delay = cap_and_backoff(retry_after_secs, attempt)
    logger.warning(
        "Pokemon TCG API rate-limited or transiently failed; sleeping %.2fs before retry %s/%s.",
        delay,
        attempt + 1,
        MAX_FETCH_ATTEMPTS,
    )
    time.sleep(delay)
```

- [ ] **Step 5: Run tests — confirm all three pass**

```bash
python -m pytest tests/test_bulk_refresh_429.py -v
```
Expected: 3 tests PASS.

- [ ] **Step 6: Run full suite**

```bash
python -m pytest tests/ -x -q 2>&1 | tail -20
```
Expected: no new failures.

- [ ] **Step 7: Commit**

```bash
git add scripts/import_pokemon_cards.py tests/test_bulk_refresh_429.py
git commit -m "fix(bulk-refresh): apply 60s Retry-After cap to _sleep_for_retry

PR #12 fixed 429 handling in pokemon_tcg.py (scheduled-ingestion path) but
missed _run_bulk_set_price_refresh which calls PokemonTCGImporter._sleep_for_retry.
That path had no cap on Retry-After — a Retry-After: 3600 header caused each
retry to sleep 3600s, producing the ~9,550s avg run duration on 2026-05-04.

Fix: import cap_and_backoff from pokemon_tcg.py (same helper that powers the
scheduled-ingestion fix). _sleep_for_retry now caps at 60s and uses the same
[2.0, 5.0, 15.0] fallback sequence.

Paths audited for this external service (Pokemon TCG API):
  - scheduled-ingestion: pokemon_tcg.fetch_card → _compute_retry_delay (PR #12, covered)
  - bulk-set-price-refresh: import_pokemon_cards.PokemonTCGImporter._sleep_for_retry (this PR)

Verified: 3 regression tests added and passing."
```

---

## Task 4: eBay duration canary alert (TDD)

**Files:**
- Modify: `backend/app/backstage/scheduler.py`
- Create: `tests/test_ebay_duration_canary.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_ebay_duration_canary.py`:

```python
"""
tests/test_ebay_duration_canary.py

Forward-looking canary: warns when ALL completed ebay-ingestion runs in the
past 24h finished in < 60s.

Sub-60s duration = fast-failing (currently: Finding API 10001 rejection fires
before Browse API fallback is attempted). A healthy Browse-based run should
take minutes. The alert is WARNING level — Browse fallback / listing_snapshot
integration does not exist yet.
"""
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, call, patch


def _make_settings(*, ebay_enabled=True, ebay_app_id="app-id", ebay_cert_id="cert-id",
                   heartbeat_enabled=True, zero_output_window=24):
    s = MagicMock()
    s.alert_heartbeat_enabled = heartbeat_enabled
    s.deploy_observation_mode_until = None
    s.ebay_scheduled_ingest_enabled = ebay_enabled
    s.ebay_app_id = ebay_app_id
    s.ebay_cert_id = ebay_cert_id
    s.zero_output_alert_window_hours = zero_output_window
    return s


def _sl_returning(sql_results):
    """Return a SessionLocal mock whose execute().fetchone() returns sql_results."""
    session = MagicMock()
    session.execute.return_value.fetchone.return_value = sql_results
    session.execute.return_value.fetchall.return_value = []
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=session)
    ctx.__exit__ = MagicMock(return_value=False)
    sl = MagicMock(return_value=ctx)
    return sl, session


class EbayDurationCanaryTests(unittest.TestCase):

    def _run_heartbeat_in_send_window(self, sl_mock):
        """Run _send_heartbeat patched into the hourly send window (minute=0)."""
        fixed_now = datetime(2026, 5, 6, 10, 0, 0, tzinfo=UTC)
        with (
            patch("backend.app.backstage.scheduler.SessionLocal", sl_mock),
            patch("backend.app.backstage.scheduler.get_settings",
                  return_value=_make_settings()),
            patch("backend.app.backstage.scheduler.datetime") as mock_dt,
            patch("backend.app.backstage.scheduler.start_run", return_value=1),
            patch("backend.app.backstage.scheduler.finish_run"),
            patch("backend.app.backstage.scheduler.prune_old_runs"),
            patch("backend.app.backstage.scheduler.get_last_run",
                  return_value=MagicMock(started_at=fixed_now - timedelta(hours=1))),
            patch("backend.app.backstage.scheduler.get_zero_output_jobs",
                  return_value=[]),
            patch("backend.app.backstage.scheduler.send_discord_alert") as mock_alert,
        ):
            mock_dt.now.return_value = fixed_now
            from backend.app.backstage.scheduler import _send_heartbeat
            _send_heartbeat()
        return mock_alert

    def test_canary_fires_when_all_runs_under_60s(self):
        """All 3 completed runs took 20s → warning alert must fire."""
        duration_row = MagicMock()
        duration_row.total_runs = 3
        duration_row.fast_runs = 3

        sl, _ = _sl_returning(duration_row)
        mock_alert = self._run_heartbeat_in_send_window(sl)

        alert_titles = [c.args[1] for c in mock_alert.call_args_list
                        if c.args[0] == "warning"]
        self.assertTrue(
            any("eBay" in t and "60s" in t for t in alert_titles),
            f"Duration canary alert not found. Alerts fired: {alert_titles}",
        )

    def test_canary_does_not_fire_when_some_runs_over_60s(self):
        """2 fast runs + 1 slow run → canary must NOT fire."""
        duration_row = MagicMock()
        duration_row.total_runs = 3
        duration_row.fast_runs = 2  # not all fast

        sl, _ = _sl_returning(duration_row)
        mock_alert = self._run_heartbeat_in_send_window(sl)

        alert_titles = [c.args[1] for c in mock_alert.call_args_list
                        if c.args[0] == "warning"]
        self.assertFalse(
            any("eBay" in t and "60s" in t for t in alert_titles),
            f"Canary fired unexpectedly when not all runs were fast: {alert_titles}",
        )

    def test_canary_does_not_fire_when_no_runs(self):
        """Zero runs in 24h → no duration canary (absence covered by 25h alert)."""
        duration_row = MagicMock()
        duration_row.total_runs = 0
        duration_row.fast_runs = 0

        sl, _ = _sl_returning(duration_row)
        mock_alert = self._run_heartbeat_in_send_window(sl)

        alert_titles = [c.args[1] for c in mock_alert.call_args_list
                        if c.args[0] == "warning"]
        self.assertFalse(
            any("eBay" in t and "60s" in t for t in alert_titles),
        )
```

- [ ] **Step 2: Run tests — confirm failure**

```bash
python -m pytest tests/test_ebay_duration_canary.py -v 2>&1 | head -30
```
Expected: tests fail because the canary block doesn't exist yet.

- [ ] **Step 3: Add canary block to `_send_heartbeat` in `scheduler.py`**

In `backend/app/backstage/scheduler.py`, inside `_send_heartbeat`, after the existing zero-output alert block (around line 371), add:

```python
        # eBay duration canary: warn when ALL completed runs in 24h finished in < 60s.
        # Sub-60s means fast-failing — currently: Finding API (svcs.ebay.com,
        # decommissioned 2025-02-05) rejects on the first call before Browse fallback.
        # WARNING level only. Browse fallback / listing_snapshot not yet wired.
        if settings.ebay_scheduled_ingest_enabled and settings.ebay_app_id and settings.ebay_cert_id:
            with SessionLocal() as _dur_session:
                _ebay_dur = _dur_session.execute(sa_text("""
                    SELECT
                        COUNT(*) AS total_runs,
                        COUNT(*) FILTER (
                            WHERE finished_at IS NOT NULL
                              AND EXTRACT(EPOCH FROM (finished_at - started_at)) < 60
                        ) AS fast_runs
                    FROM scheduler_run_log
                    WHERE job_name = 'ebay-ingestion'
                      AND status IN ('success', 'partial', 'warning', 'error')
                      AND started_at > NOW() - INTERVAL '24 hours'
                """)).fetchone()
            if (_ebay_dur and _ebay_dur.total_runs > 0
                    and _ebay_dur.total_runs == _ebay_dur.fast_runs):
                send_discord_alert(
                    "warning",
                    f"eBay ingestion 快速失败警告: 过去 24h 所有 {_ebay_dur.total_runs} 次运行 < 60s",
                    "Finding API (svcs.ebay.com) 已于 2025-02-05 下线，首次调用即返回拒绝 (10001)。\n"
                    "Browse API fallback / listing_snapshot 尚未建立。\n"
                    "此为前瞻性告警，不阻塞当前运行。参见 CLAUDE.md eBay API status 节。",
                )
```

- [ ] **Step 4: Run tests — confirm all three pass**

```bash
python -m pytest tests/test_ebay_duration_canary.py -v
```
Expected: 3 tests PASS.

- [ ] **Step 5: Run full suite**

```bash
python -m pytest tests/ -x -q 2>&1 | tail -20
```
Expected: no new failures.

- [ ] **Step 6: Commit**

```bash
git add backend/app/backstage/scheduler.py tests/test_ebay_duration_canary.py
git commit -m "feat(heartbeat): add eBay fast-fail duration canary alert

Fires when ALL completed ebay-ingestion runs in 24h finished in < 60s.
Sub-60s = Finding API (svcs.ebay.com, decommissioned 2025-02-05) rejecting
on first call before Browse fallback. WARNING level — Browse fallback /
listing_snapshot not yet wired.

2026-05-04 data: avg_duration_ms=18,400 (10 runs) → would have fired.
2026-05-05 data: avg_duration_ms=88,500 (2 runs) → would NOT fire (correct).

Verified: 3 unit tests added and passing."
```

---

## Task 5: Open PR

- [ ] **Step 1: Confirm branch is clean**

```bash
git status
git log --oneline main..HEAD
```
Expected: 4 commits ahead of main, no uncommitted changes.

- [ ] **Step 2: Push and create PR**

```bash
git push origin HEAD
gh pr create \
  --title "fix(bulk-refresh): apply PR #12 429 cap to bulk-refresh path + eBay duration canary" \
  --body "$(cat <<'PREOF'
## Precondition

PR #12 fixed 429 handling in `pokemon_tcg.py` (scheduled-ingestion path) by adding
`_compute_retry_delay` with a 60-second Retry-After cap. The `_run_bulk_set_price_refresh`
path calls `PokemonTCGImporter._sleep_for_retry` in `scripts/import_pokemon_cards.py`,
which had its own retry logic with **no Retry-After cap**.

**Code evidence — bulk-refresh before this PR:**
\`\`\`python
# scripts/import_pokemon_cards.py _sleep_for_retry (pre-fix)
delay = retry_after if retry_after is not None else min(2 ** (attempt - 1), 8)
# NO cap — Retry-After: 3600 → sleeps 3600s per retry
\`\`\`

**Code evidence — PR #12 (scheduled-ingestion path):**
\`\`\`python
# pokemon_tcg.py _compute_retry_delay (PR #12)
return min(retry_after, 60.0)   # capped at 60s
\`\`\`

**Impact:** 2026-05-04 scheduler history shows bulk-refresh avg_duration_ms ≈ 9,550s
(8 failed runs out of 19). With Retry-After: 3600, a single exhausted retry-budget
per set × 25 sets produces that duration. Scheduled-ingest was protected by the cap;
bulk-refresh was not.

## Changes

### Part 1 — Issue B rename (CLAUDE.md)
Renamed from "3 days no Pokémon data" (misdiagnosed) to the accurate incident
description. Added two backlog notes: alert SQL audit and PokemonTCGImporter location.

### Part 2 — `cap_and_backoff` shared helper (separate commit)
Extracted from `_compute_retry_delay` into a public `cap_and_backoff` function in
`pokemon_tcg.py`. `_compute_retry_delay` now delegates to it. `_sleep_for_retry` in
`import_pokemon_cards.py` imports and uses it — same 60s cap and [2.0, 5.0, 15.0]
fallback, no new semantics introduced.

**Paths audited — Pokemon TCG API:**
- `scheduled-ingestion`: `pokemon_tcg.fetch_card` → `_compute_retry_delay` (PR #12, already covered)
- `bulk-set-price-refresh`: `import_pokemon_cards.PokemonTCGImporter._sleep_for_retry` (this PR)

### Part 3 — eBay fast-fail canary
Added to `_send_heartbeat`: warns when ALL completed `ebay-ingestion` runs in 24h
finished in < 60s. Finding API (decommissioned 2025-02-05) rejects on first call;
Browse fallback is not yet wired. WARNING level only.

## Diff — `_run_bulk_set_price_refresh` before/after
[Paste the diff of `_sleep_for_retry` here before merging]

## Tests added
- `tests/test_cap_and_backoff.py` — 5 tests (Retry-After within cap, exceeds cap, no header, attempt clamp low, attempt clamp high)
- `tests/test_bulk_refresh_429.py` — 3 tests (3600s capped, 30s passed through, no-header fallback)
- `tests/test_ebay_duration_canary.py` — 3 tests (all fast → fires, mixed → no fire, zero runs → no fire)

Total test delta: +11 tests

## Codex review checklist
- [ ] `cap_and_backoff` reuses PR #12's helper, not a reimplementation
- [ ] No new backoff semantics introduced
- [ ] eBay canary is WARNING level, not error
- [ ] `_sleep_for_retry` diff confirms cap applied

## Verification after merge (48h)
Run `/admin/diag/scheduler-history?days=2` and check:
- `bulk-set-price-refresh` failure count < 2/day
- `ebay-ingestion` avg_duration_ms consistent (expectation: ~80s while Browse-only)
- `ingestion` failure rate < 10%

Issue B remains open until this report is acknowledged.
PREOF
)"
```

---

## Self-review checklist

**Spec coverage:**
- Part 1 (Issue B rename + backlog): Task 1 ✓
- Part 2 precondition paste in PR: Task 5 Step 2 (body) ✓
- Part 2 shared helper, same semantics: Tasks 2-3 ✓
- Part 2 "Paths audited" in PR description: Task 5 Step 2 ✓
- Part 2 test: 429 cascade terminates cleanly with correct log status: Task 3 ✓
- Part 3 eBay canary warning (not error): Task 4 ✓
- Part 3 canary rationale in code comment: Task 4 Step 3 ✓
- Part 3 test: fires on 20s series, not on mixed: Task 4 Step 1 ✓
- Codex review section in PR: Task 5 Step 2 ✓
- Test count delta reported: Task 5 Step 2 ("+11 tests") ✓
- Diff of _run_bulk_set_price_refresh in PR: Task 5 Step 2 ("Paste here before merging") ✓

**Exclusions confirmed not touched:**
- Browse API parser (reverted, stays reverted) ✓
- `listing_snapshot` table ✓
- `ebay_sold.py` dead code ✓
- YGO Phase 2 gates ✓
- Alert SQL for "3 days no data" (added to backlog only) ✓

**No placeholders found.**

**Type consistency:** `cap_and_backoff(retry_after_secs: float | None, attempt: int) -> float` is consistent across Task 2 (definition), Task 3 (import), and test files.
