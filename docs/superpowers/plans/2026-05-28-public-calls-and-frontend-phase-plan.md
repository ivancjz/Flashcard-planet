# Public Calls Launch + Frontend Repositioning — Phased Execution Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Get Public Calls to soft launch (fresh cohort live on /calls) and complete the frontend repositioning to signal intelligence terminal grammar, in the correct dependency order.

**Architecture:** Quality gates 1–9 gate the Public Calls launch. Frontend repositioning runs in parallel where independent. Nothing in Phase 3+ starts until Phase 0 and Phase 1 are verified complete.

**Source:** Ivan's planning document (2026-05-27) + ideas ledger (2026-05-27). This plan supersedes the brainstorming session output from the same date.

**CRITICAL: Do not execute phases without Ivan's explicit per-phase approval. Present this plan, get approval, then execute wave by wave.**

---

## Dependency map

```
Phase 0 (now)
  └── Phase 1 (this week)
        ├── Phase 2 (parallel, no dependencies on Phase 1 completion)
        └── Phase 3 (requires Gate 5 data window, ~2026-05-29)
              └── Phase 4 (requires Gate 7 smart sort calibration)
                    └── Phase 5 (requires all gates 1-9)
```

---

## Phase 0 — Gate 6 Fix (BLOCKER — do now, nothing else proceeds)

**Trigger:** Immediate. Planning doc: "Fix Gate 6 production render (Section 1.1). Nothing else proceeds with a broken public-facing page."

**What's broken:** Methodology page (`/methodology`) renders a blank/black screen in production. Root cause confirmed: the committed frontend dist bundle (`index-Dl2GptGj.js`, from commit `d5999f4` on Phase 2 dist commit) was built **before** the methodology page commits (`1cf152a` + `545ec20`). The deployed JS bundle has no `/methodology` route. Working tree is also in a broken half-rebuilt state (old bundle deleted, new bundle not committed).

**Acceptance criteria:**
- [ ] `GET /methodology` in production renders the full 10-section methodology page
- [ ] No console errors in production
- [ ] `/calls` link to `/methodology` resolves correctly
- [ ] `gate-status.md` corrected (Gate 6 BROKEN → in-progress → verified DONE)

### Task 0.1 — Rebuild and commit frontend dist

**Files:**
- Modify: `frontend/dist/index.html`
- Modify: `frontend/dist/assets/index-*.js` (new hash)
- Modify: `frontend/dist/assets/index-*.css`

- [ ] **Step 1: Clean working tree state**

```powershell
git stash
```

Then verify git status shows only the `?? scripts/_tmp_b2_inject_predictions.py` untracked file.

- [ ] **Step 2: Install dependencies**

```powershell
cd frontend
npm ci
```

- [ ] **Step 3: Run production build**

```powershell
npm run build
```

Expected: `dist/assets/index-XXXXXXXX.js` created, `dist/index.html` updated to reference new hash.

- [ ] **Step 4: Verify MethodologyPage is in the bundle**

```powershell
grep -c "MethodologyPage\|methodology\|Brier\|Wilson" dist/assets/index-*.js
```

Expected: non-zero match count (confirms methodology content is in the bundle).

- [ ] **Step 5: Smoke test the build locally**

```powershell
npm run preview
```

Navigate to `http://localhost:4173/methodology` — confirm 10-section page renders with no console errors.
Navigate to `http://localhost:4173/calls` — confirm calls page still works (regression check).

- [ ] **Step 6: Stage and commit dist**

```powershell
git add frontend/dist/
git commit -m "build(frontend): rebuild dist — include MethodologyPage at /methodology

Route /methodology was implemented in commits 1cf152a + 545ec20 but dist
was never rebuilt. Production bundle lacked the route entirely (blank screen).

Verified:
- npm run build completed cleanly
- dist/assets/index-*.js contains Brier/methodology content
- Local preview: /methodology renders all 10 sections, /calls regression OK

Fixes Gate 6 production render."
```

- [ ] **Step 7: Push and verify Railway deployment**

```powershell
git push
railway logs --service backend
```

Wait for Railway to auto-deploy (typically 2–3 min). Confirm no build errors in logs.

- [ ] **Step 8: Production verification**

Navigate to production `/methodology`. Confirm:
1. Page renders (not blank)
2. All 10 sections visible
3. No console errors
4. `/calls` → "Methodology →" link works

### Task 0.2 — Correct gate-status.md

**Files:**
- Modify: `c:\Flashcard-planet\.claude\specs\public-calls-gate-status.md`

- [ ] **Step 1: Update gate status**

Change Gate 6 entry from `[x]` (incorrectly marked done) to reflect verified production state. After Task 0.1 is verified, mark `[x]` with correct evidence:

```
- [x] **Gate 6: Methodology page** — LIVE 2026-05-28 (commits 1cf152a + 545ec20 + dist rebuild)
  - All 10 spec sections implemented in `frontend/src/pages/calls/MethodologyPage.tsx`
  - Route `/methodology` live in production (verified after dist rebuild)
  - Hardcoded methodology version "v0.1" (auto-pull from git SHA deferred)
```

Note: if Task 0.1 is still in-progress, mark Gate 6 as `[ ]` with status: "DIST REBUILD PENDING — route missing from production bundle."

- [ ] **Step 2: Commit**

```powershell
git add .claude/specs/public-calls-gate-status.md
git commit -m "chore(gates): correct Gate 6 status — dist rebuild required, not complete

Gate 6 was prematurely marked done. Route existed in source but not in
committed dist bundle. Correcting to reflect actual production state."
```

**Phase 0 done when:** Ivan confirms `/methodology` renders in production without blank screen.

---

## Phase 1 — Infrastructure + Gate Activation (This week)

**Trigger:** Phase 0 complete and verified by Ivan.

**Parallel tracks within Phase 1:** All four infrastructure tasks (1.1–1.4) are independent of each other. Gate 4 activation is independent of Gate 3. Execute in any order, or in parallel.

### Task 1.1 — Gate 4: Verify guardrails, then enable RESOLVE_PREDICTIONS_ENABLED

**Context:** 5 test predictions injected with `methodology_version='gate4-b2-test'`, all PENDING. Kill switch `RESOLVE_PREDICTIONS_ENABLED=false` (Category β, default off). Ivan action needed to enable for the 7-day observation window.

**Pre-check required before enabling kill switch:**

- [ ] **Step 1: Verify Discord webhook goes to DEV/private channel**

```powershell
railway variables | grep DISCORD
```

Confirm `DISCORD_WEBHOOK_URL` points to a private/dev channel, NOT the production public channel. If it points to production, STOP — do not enable until webhook is routed correctly.

- [ ] **Step 2: Verify /calls page filters test predictions**

Check `frontend/src/pages/calls/CallsPage.tsx` for filter logic that excludes `methodology_version='gate4-b2-test'` from the public-facing calls table.

If no filter exists, add it before enabling. Test predictions must not appear on `/calls`.

- [ ] **Step 3: Verify PUBLIC_PREDICTIONS_ENABLED=false**

```powershell
railway variables | grep PUBLIC_PREDICTIONS_ENABLED
```

Confirm it's false (or unset, which defaults to false per public-calls-decisions.md Phase 3 decision).

- [ ] **Step 4: Enable kill switch in Railway (Ivan action)**

Ivan sets `RESOLVE_PREDICTIONS_ENABLED=true` in Railway dashboard.

This starts the 7-day observation window.

- [ ] **Step 5: Verify first resolution run**

Wait for next scheduler tick (4h interval). Check `scheduler_run_log`:

```sql
SELECT job_name, status, records_written, finished_at, meta_json
FROM scheduler_run_log
WHERE job_name = 'resolve-predictions'
ORDER BY finished_at DESC
LIMIT 5;
```

Expected: at least one `status='success'` row within 4 hours of enabling.

- [ ] **Step 6: Verify test predictions resolved correctly**

```sql
SELECT asset_id, threshold_direction, threshold_value, stated_probability,
       outcome, resolved_at, methodology_version
FROM predictions
WHERE methodology_version = 'gate4-b2-test'
ORDER BY resolved_at DESC;
```

Expected outcomes per gate-status.md:
- Charizard above $500 → HIT (actual $595.18)
- Alakazam below $100 → HIT (actual $76.62)
- Clefairy within $30–$45 → HIT (actual $36.51)
- Blastoise above $300 → MISS (actual $220.81)
- Chansey below $40 → MISS (actual $53.09)

**Gate 4 passes when:** All 5 resolve correctly AND scheduler shows 7 consecutive days of clean `scheduler_run_log` rows.

### Task 1.2 — Gate 3: Fundamental signal sanity check

**Context:** No dependency on Gate 2 sign-off. Can start anytime. Gate 3 verifies the fundamental signal pipeline is producing sensible outputs.

- [ ] **Step 1: Query fundamental signals for a sample of cards**

```sql
SELECT a.name, a.set_name,
       s.label,
       s.price_delta_pct AS actual_delta_pct,
       fs.fundamental_delta_pct,
       fs.hype_premium_pct,
       fs.contamination_window_used
FROM asset_signals s
JOIN assets a ON a.id = s.asset_id
JOIN fundamental_signals fs ON fs.asset_id = s.asset_id
WHERE s.label IN ('BREAKOUT', 'MOVE')
  AND a.game = 'pokemon'
ORDER BY ABS(fs.hype_premium_pct) DESC
LIMIT 20;
```

- [ ] **Step 2: Sanity checks**

For each row, verify:
1. `fundamental_delta_pct` is within ±2pp of `actual_delta_pct` for cards with no contamination events → this is the "no hype = no premium" baseline
2. Cards with `EVENT_DRIVEN` driver have `hype_premium_pct > 2pp` (the dead-band)
3. No cards show `hype_premium_pct > 100pp` (would indicate algorithmic divergence bug)
4. `contamination_window_used` is non-null for EVENT_DRIVEN cards

- [ ] **Step 3: Report findings to Ivan**

Document pass/fail for each sanity check. If any check fails, file a specific bug before marking Gate 3 DONE.

**Gate 3 passes when:** All 4 sanity checks pass across the sample.

### Task 1.3 — Infrastructure: PUBLIC_PREDICTIONS_ENABLED guard in prediction_service.py

**Context:** From public-calls-decisions.md: "Add PUBLIC_PREDICTIONS_ENABLED env var check — defaults False. is_paper=False raises ValueError unless flag is True."

**Files:**
- Modify: `backend/app/services/prediction_service.py`
- Modify: `backend/app/core/config.py` (add env var)

- [ ] **Step 1: Write failing test**

```python
# tests/services/test_prediction_service.py
def test_create_public_prediction_blocked_when_flag_off(db_session, monkeypatch):
    monkeypatch.setenv("PUBLIC_PREDICTIONS_ENABLED", "false")
    with pytest.raises(ValueError, match="PUBLIC_PREDICTIONS_ENABLED"):
        create_prediction(db_session, asset_id=..., is_paper=False, ...)

def test_create_paper_prediction_always_allowed(db_session, monkeypatch):
    monkeypatch.setenv("PUBLIC_PREDICTIONS_ENABLED", "false")
    # should not raise
    result = create_prediction(db_session, asset_id=..., is_paper=True, ...)
    assert result is not None
```

- [ ] **Step 2: Verify test fails**

```powershell
pytest tests/services/test_prediction_service.py -v -k "public_prediction"
```

Expected: FAIL (guard not implemented yet).

- [ ] **Step 3: Add env var to config**

In `backend/app/core/config.py`:
```python
PUBLIC_PREDICTIONS_ENABLED: bool = Field(default=False)
```

- [ ] **Step 4: Add guard in prediction_service.py**

In `create_prediction()`:
```python
if not is_paper and not settings.PUBLIC_PREDICTIONS_ENABLED:
    raise ValueError(
        "PUBLIC_PREDICTIONS_ENABLED is False. "
        "Set this flag in Railway after Gate 9 fresh cohort approved."
    )
```

- [ ] **Step 5: Run tests**

```powershell
pytest tests/services/test_prediction_service.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add backend/app/services/prediction_service.py backend/app/core/config.py
git commit -m "feat(predictions): add PUBLIC_PREDICTIONS_ENABLED guard

is_paper=False raises ValueError unless PUBLIC_PREDICTIONS_ENABLED=true.
Default false. Set in Railway after Gate 9 fresh cohort approved.

Per public-calls-decisions.md 2026-05-19 decision."
```

### Task 1.4 — Infrastructure: Scheduler observability for resolve-predictions

**Context:** resolve-predictions job must write to `scheduler_run_log` on every run.

- [ ] **Step 1: Check current state**

```powershell
grep -n "resolve_predictions\|scheduler_run_log\|start_run\|finish_run" backend/app/backstage/scheduler.py | head -40
```

If `_run_resolve_predictions()` already has `start_run`/`finish_run` in a `finally` clause → skip this task (already done, mark N/A).

- [ ] **Step 2: If missing, add scheduler_run_log writes**

Pattern (from CLAUDE.md §2, all jobs use unconditional start_run + finish_run):

```python
async def _run_resolve_predictions():
    run_id = start_run(db, "resolve-predictions")
    records_written = 0
    errors = 0
    try:
        if not settings.RESOLVE_PREDICTIONS_ENABLED:
            finish_run(db, run_id, status="success",
                       records_written=0, meta_json={"skipped": "kill_switch_off"})
            return
        # ... existing resolution logic ...
        records_written = resolved_count
    except Exception as e:
        errors += 1
        finish_run(db, run_id, status="error", errors=errors,
                   error_message=str(e))
        raise
    finally:
        if not errors:
            finish_run(db, run_id, status="success", records_written=records_written)
```

- [ ] **Step 3: Add to heartbeat _monitored_jobs list**

In `scheduler.py`, find `_monitored_jobs` list and add `"resolve-predictions"`.

- [ ] **Step 4: Commit**

```powershell
git commit -m "feat(scheduler): add scheduler_run_log writes to resolve-predictions job

Every job must write scheduler_run_log on every exit path including
kill-switch-off path. Added to _monitored_jobs for heartbeat coverage.

Per CLAUDE.md §6 Lesson 9."
```

### Task 1.5 — Infrastructure: Add production verification discipline to CLAUDE.md

**Context:** Gate 6 was marked done without production verification. CLAUDE.md needs a section preventing recurrence.

**Files:**
- Modify: `c:\Flashcard-planet\CLAUDE.md`

- [ ] **Step 1: Add §5.3 Frontend Production Verification Discipline**

Add after the existing section on feature flag defaults, or create a new section §13:

```markdown
## 13. Frontend production verification discipline

Frontend changes that introduce new routes or components are NOT complete
until production verification, not just local testing.

**Required for any frontend commit that:**
- Adds a new route to `main.tsx`
- Modifies `frontend/dist/` (or should trigger a dist rebuild)

**Verification sequence:**
1. Run `npm run build` in `frontend/`
2. Smoke test with `npm run preview` at the new route
3. Commit the new `dist/` files (with the new hash) in the SAME commit as the source changes, or in an immediate follow-up commit clearly marked `build(frontend): rebuild dist for <feature>`
4. After Railway deploy, verify the route renders in production with no console errors

**Anti-pattern (what caused Gate 6 failure):** Committing source changes that add a route, marking the gate as done, and never rebuilding and committing the dist. The committed bundle continues serving the old app; the new route is unreachable in production.

**Rule:** If `git log --oneline -5 -- frontend/dist/` does not show a dist commit AFTER the most recent source change commit, the feature is not deployed.
```

- [ ] **Step 2: Commit**

```powershell
git add CLAUDE.md
git commit -m "docs(CLAUDE.md): add §13 frontend production verification discipline

Gate 6 was marked done without verifying production (blank screen).
Adding explicit rule: dist must be rebuilt and committed after any
route/component addition. Production render must be verified."
```

**Phase 1 done when:** Gate 4 kill switch enabled, Gate 3 sanity checks passed, tasks 1.3–1.5 committed and deployed.

---

## Phase 2 — Frontend Repositioning Quick Wins (Parallel, Independent)

**Trigger:** Phase 0 complete. Can run in parallel with Phase 1. No dependency on Gates.

### Task 2.1 — FE-1: Replace landing hero with live calibration metrics

**Context:** Current hero shows "0 Breakout" etc. (static or disconnected). Replace with live metrics that reinforce credibility: current signal counts, Brier score (if predictions exist), honest n warning.

**Files:**
- Modify: `frontend/src/pages/LandingPage.tsx`
- Possibly modify: `backend/app/api/routes/` (new stats endpoint if needed)

- [ ] **Step 1: Check current hero component**

Read `frontend/src/pages/LandingPage.tsx` — identify the hero section and what data it currently displays.

- [ ] **Step 2: Check if stats endpoint exists**

```powershell
grep -n "breakout_count\|signal_count\|brier\|stats" backend/app/api/routes/*.py | head -20
```

If a public stats endpoint exists, use it. If not, add a minimal `/api/v1/stats/public` endpoint returning:
```json
{
  "breakout_count": N,
  "move_count": N,
  "watch_count": N,
  "prediction_count": N,
  "brier_score": null | float,
  "honest_n_warning": "n<10 — pre-calibration, directional only"
}
```

- [ ] **Step 3: Update hero copy to program grammar**

Replace current copy with signal intelligence terminal framing:
- Remove: "0 Breakout cards" styled as a badge
- Add: Live signal counts as terminal-style readouts
- Add: If predictions exist, Brier score with honest n warning
- Copy anchor: "Market signals updated every 15 minutes"

- [ ] **Step 4: Build, test, commit**

```powershell
cd frontend && npm run build
# smoke test at localhost:4173
git add frontend/src/ frontend/dist/
git commit -m "feat(landing): replace static hero with live calibration metrics

Signal counts and honest-n warning. Program grammar (terminal readout
style, not marketing badge style)."
```

### Task 2.2 — FE-3: Pro tier copy rewrite

**Context:** Planning doc specifies Pro tier at $30/mo (not $24.99). Plus tier at $9.99. Founders locks: Plus $7 first 100, Pro $20 first 50. Update `PricingPage.tsx` to reflect correct pricing and positioning.

**Note:** This is a copy change only. LemonSqueezy integration is deferred — do NOT wire payment logic here.

**Files:**
- Modify: `frontend/src/pages/PricingPage.tsx`

- [ ] **Step 1: Read current PricingPage**

Confirm current tier names (FREE/PLUS/PRO vs Free/Signal/Pro), prices, and feature lists.

- [ ] **Step 2: Update to correct pricing**

```
Free:   $0    — IDLE/WATCH signals, 24h delay, 1 game, 1 watchlist
Plus:   $9.99/mo — real-time BREAKOUT/MOVE, all games, Discord DMs, AI explanation
Pro:    $30/mo   — all Plus + full AI analysis, JP lead signals, grading ROI, portfolio, API
```

Founders lock callout:
```
First 100 Plus subscribers: $7/mo locked for life
First 50 Pro subscribers: $20/mo locked for life
```

- [ ] **Step 3: Align tier names**

If codebase uses "PLUS" enum value already, keep it. If "SIGNAL", decide: rename to PLUS or keep. Check `backend/app/core/permissions.py` Tier enum before changing frontend copy — frontend display names can differ from enum values.

- [ ] **Step 4: Build, test, commit**

```powershell
cd frontend && npm run build
git add frontend/src/pages/PricingPage.tsx frontend/dist/
git commit -m "feat(pricing): update Pro/Plus pricing to correct rates

Plus $9.99, Pro $30. Founders lock callout added.
Copy-only change — no payment logic wired.

Per planning doc 2026-05-27."
```

**Phase 2 done when:** FE-1 and FE-3 deployed and rendering correctly in production.

---

## Phase 3 — Gate 5 Confirmation + Gate 7 Smart Sort + Gate 8 Paper Trades

**Trigger:** Gate 5 T+7d check (2026-05-29). Phase 1 complete.

### Task 3.1 — Gate 5: Chaos Rising data completeness check

**Context:** me4 (Chaos Rising) in TIER1_BULK_SET_IDS since 2026-05-23. T+7d data window closes 2026-05-30. Need to verify ≥80% data completeness before Gate 5 passes.

- [ ] **Step 1: Run data completeness SQL**

```sql
-- Check Chaos Rising asset coverage
SELECT
    COUNT(*) AS total_assets,
    COUNT(DISTINCT ph.asset_id) AS assets_with_price_data,
    ROUND(COUNT(DISTINCT ph.asset_id)::numeric / COUNT(*)::numeric * 100, 1) AS coverage_pct,
    MIN(ph.captured_at) AS earliest_price,
    MAX(ph.captured_at) AS latest_price,
    COUNT(ph.id) FILTER (WHERE ph.captured_at >= NOW() - INTERVAL '7 days') AS rows_last_7d
FROM assets a
LEFT JOIN price_history ph ON ph.asset_id = a.id
    AND ph.source = 'pokemon_tcg_api'
    AND ph.captured_at >= '2026-05-23'
WHERE a.set_name ILIKE '%chaos rising%'
  AND a.game = 'pokemon';
```

- [ ] **Step 2: Run signal graduation check**

```sql
SELECT label, COUNT(*) AS count
FROM asset_signals s
JOIN assets a ON a.id = s.asset_id
WHERE a.set_name ILIKE '%chaos rising%'
GROUP BY label;
```

Expected: at least some IDLE/WATCH cards graduated from INSUFFICIENT_DATA.

- [ ] **Step 3: Report findings**

Gate 5 passes if:
- Coverage ≥ 80% of expected Chaos Rising assets
- At least 1 signal-producing asset (non-INSUFFICIENT_DATA)
- 7 consecutive days of `bulk-set-price-refresh` logs for Chaos Rising

### Task 3.2 — Gate 7: Smart sort calibration

**Context:** Depends on Gate 5 data. Smart sort needs enough signal distribution across Chaos Rising to confirm the sort order is meaningful (BREAKOUT first, then MOVE, then WATCH, then IDLE).

- [ ] **Step 1: Check current sort logic**

```powershell
grep -n "sort\|order_by\|BREAKOUT\|signal_label" backend/app/api/routes/*.py | grep -i sort | head -20
```

Identify where market page sort is implemented.

- [ ] **Step 2: Verify smart sort produces sensible ordering**

Sample the market page API response for Chaos Rising cards. Confirm:
- BREAKOUT cards appear before MOVE
- MOVE before WATCH
- WATCH before IDLE
- INSUFFICIENT_DATA at bottom

- [ ] **Step 3: Calibration check**

If BREAKOUT threshold is too tight (no Chaos Rising BREAKOUT cards after 7 days) OR too loose (>30% of Chaos Rising is BREAKOUT), flag for Ivan threshold review.

Expected healthy distribution: ~2–10% BREAKOUT, ~10–25% MOVE, ~30–50% WATCH, ~20–40% IDLE.

**Gate 7 passes when:** Smart sort confirmed sensible on Chaos Rising data, distribution within expected range.

### Task 3.3 — Gate 8: Paper trade predictions start

**Context:** From gate-status.md: window opens ~2026-06-01. Minimum 10 paper predictions required. Target cards: Mega Greninja ex SIR, Mega Floette ex SIR, Mega Pyroar ex SIR, Mega Dragalge ex SIR, Chaos Rising ETB, booster box.

**Note:** This task is Ivan-driven. Claude Code's role is to provide the prediction injection tool and verify the scheduler picks them up.

- [ ] **Step 1: Verify paper prediction injection script**

Check if a script or admin endpoint exists for injecting paper predictions:

```powershell
grep -rn "is_paper\|inject_prediction\|create_prediction" scripts/ backend/app/backstage/ | head -20
```

- [ ] **Step 2: If no tool, create admin endpoint**

Add `POST /admin/trigger/inject-paper-prediction` that accepts:
```json
{
  "asset_id": "uuid",
  "threshold_direction": "above|below|within",
  "threshold_value": 500.00,
  "threshold_value_high": null,
  "resolution_date": "2026-07-01T00:00:00Z",
  "stated_probability": 0.72
}
```

Calls `create_prediction(is_paper=True)` — always allowed regardless of `PUBLIC_PREDICTIONS_ENABLED`.

- [ ] **Step 3: Inject target predictions (Ivan action)**

Ivan uses the endpoint to inject ≥10 paper predictions for the target cards. Claude Code documents the injection with verification SQL.

- [ ] **Step 4: Verify in scheduler**

After `RESOLVE_PREDICTIONS_ENABLED=true` (from Task 1.1), confirm paper predictions appear in resolution queue on their target dates.

**Gate 8 passes when:** ≥10 paper predictions injected and resolution scheduler confirmed tracking them.

**Phase 3 done when:** Gates 5, 7, 8 all confirmed by Ivan.

---

## Phase 4 — Frontend Intelligence Terminal Features (Post-Gate 7)

**Trigger:** Gate 7 smart sort calibration approved by Ivan.

### Task 4.1 — FE-2: Market page smart default sort

**Context:** Market page currently uses default sort. After Gate 7 confirms sort order is sensible, expose it as the default user-facing sort.

**Files:**
- Modify: `frontend/src/pages/DashboardPage.tsx`
- Possibly: `frontend/src/components/` (sort control component)

- [ ] **Step 1: Identify current sort default**

Read `DashboardPage.tsx` — find the API call and default sort parameter.

- [ ] **Step 2: Set smart sort as default**

Update the market page default sort to `?sort=signal_desc` (or whatever the API parameter is for BREAKOUT-first ordering).

- [ ] **Step 3: Add sort control (if not present)**

User-facing sort selector: Signal (default) | Price | % Change | Name.

- [ ] **Step 4: Build, test, commit**

### Task 4.2 — FE-5: Market workspace investment-tier curation

**Context:** "Curate market page to investment-tier first." Surface cards with BREAKOUT/MOVE signals prominently. Reduce visual noise from IDLE/INSUFFICIENT_DATA cards.

**Files:**
- Modify: `frontend/src/pages/DashboardPage.tsx`
- Possibly: filter controls, tier badges

- [ ] **Step 1: Add signal-tier filter control**

Add filter pills: "All" | "Investment signals" (BREAKOUT+MOVE) | "Watch" | "Idle".

Default: "Investment signals" for Plus/Pro users; "All" for Free users.

- [ ] **Step 2: Apply program grammar vocabulary**

Replace any remaining "Dashboard" → "Market workspace" or similar in page headers. "Card Detail" → visible as "Card Inspector" in breadcrumbs.

### Task 4.3 — FE-6: Card inspector driver surface

**Context:** Surface driver attribution and fundamental delta on card detail pages.

**Files:**
- Modify: `frontend/src/pages/CardDetailPage.tsx`
- Possibly: new `DriverAttributionPanel.tsx` component

- [ ] **Step 1: Check what driver data is already in the API response**

```powershell
grep -n "driver\|attribution\|fundamental\|hype_premium" backend/app/api/routes/signals.py
```

- [ ] **Step 2: Expose fundamental delta and hype premium**

On the card inspector, below the signal badge:
```
Signal: BREAKOUT  +$X.XX (+YY%)
Driver: EVENT_DRIVEN — Chaos Rising release (2026-05-23)
Fundamental delta: +8%  Hype premium: +32pp
```

Hype premium dead-band: show "No meaningful hype" for |premium| < 2pp. Show value for ≥5pp.

- [ ] **Step 3: Signal display fix (absolute + relative)**

Add `price_delta_abs` field to `SignalResponse` schema. Update display to show both:
- `+$1.50 (+300%)` format
- Suppress % if absolute delta < $0.50 (show `+$0.35` only)

This is the fix for Ivan's "340% is too high, sometimes only $1–2" feedback.

**Files for signal display fix:**
- `backend/app/api/routes/signals.py` — add `price_delta_abs: Decimal` to `SignalResponse`
- `backend/app/services/signal_service.py` — compute `price_delta_abs` in sweep
- `frontend/src/utils/format.ts` — add `formatDeltaDisplay(delta_pct, current_price, baseline_price)` helper
- `frontend/src/components/SignalBadge.tsx` — use `formatDeltaDisplay`
- `frontend/src/pages/CardDetailPage.tsx` — use `formatDeltaDisplay`

**Phase 4 done when:** FE-2, FE-5, FE-6 (including signal display fix) deployed and verified.

---

## Phase 5 — Gate 9 + Public Calls Soft Launch

**Trigger:** Gates 1–8 all confirmed by Ivan.

### Task 5.1 — Gate 9: Fresh public calls cohort

**Context:** 4–6 predictions, `is_paper=FALSE`. Requires `PUBLIC_PREDICTIONS_ENABLED=true` set in Railway by Ivan.

**Ivan actions:**
1. Set `PUBLIC_PREDICTIONS_ENABLED=true` in Railway
2. Inject 4–6 public predictions for high-conviction signals

**Claude Code role:**
- Verify predictions appear in `/calls` feed (not filtered as test predictions)
- Verify Brier score and honest-n warning update correctly
- Verify methodology_version is correctly set (short git SHA, not "gate4-b2-test")

- [ ] **Step 1: Ivan sets PUBLIC_PREDICTIONS_ENABLED=true**

```powershell
# Ivan confirms in Railway dashboard
railway variables | grep PUBLIC_PREDICTIONS_ENABLED
```

Expected: `PUBLIC_PREDICTIONS_ENABLED=true`.

- [ ] **Step 2: Ivan injects 4–6 public predictions**

Using `/admin/trigger/inject-paper-prediction` endpoint but with `is_paper=False`.

- [ ] **Step 3: Verify public display**

Navigate to `/calls` in production. Confirm:
- Predictions appear in the table
- `methodology_version` shows `v0.1-{hash}` format
- `n=4` (or appropriate count) and honest-n warning visible
- Brier score shows (will be null until first resolution)

- [ ] **Step 4: Update gate-status.md**

Mark Gate 9 complete with evidence.

### Task 5.2 — Soft launch announcement prep

**Context:** From ideas ledger: "First public call bound to high-profile event for launch visibility (5d) — UNACTIONED." Consider timing if a high-profile Pokemon event is imminent.

- [ ] **Step 1: Check event calendar**

Review `market_events` table for upcoming events in the next 4–8 weeks that could serve as a launch anchor.

- [ ] **Step 2: Report to Ivan**

If a high-profile event exists in the window, flag it as a potential launch anchor. Ivan decides.

**Phase 5 done when:** Fresh cohort live on `/calls`, Ivan confirms soft launch.

---

## Deferred (do not start)

These are explicitly out of scope for this execution plan:

| Item | Reason | When |
|------|---------|------|
| One Piece TCG integration | ROADMAPPED Track B, after Pokemon Public Calls stable ≥2 weeks | Q4 2026 |
| LemonSqueezy payment integration | TASK-301, separate plan needed | After Public Calls soft launch |
| YGO expansion | Maintenance mode only; no feature work | Never (until source confirmed) |
| Scan-card feature | Phase 9+, post Public Calls launch | Phase 9+ |
| Custom domain (TASK-501) | Ops task, Ivan decision before public launch | Before Gate 9 |
| Discord bot v2 slash commands | Phase 3 roadmap (months 4–7) | Post Public Calls |
| Japanese lead-signal detection | Phase 3 roadmap | Post Public Calls |
| Pre-grading ROI calculator | Phase 3 roadmap | Post Public Calls |

---

## Acceptance criteria summary

| Phase | Done when |
|-------|-----------|
| 0 | Ivan confirms `/methodology` renders in production |
| 1 | Gate 4 running (7-day observation), Gate 3 sanity checks pass, infra tasks committed |
| 2 | FE-1 live (live metrics hero), FE-3 live (correct pricing) |
| 3 | Ivan confirms Gates 5, 7, 8 |
| 4 | FE-2, FE-5, FE-6 + signal display fix deployed |
| 5 | Fresh cohort on `/calls`, Ivan declares soft launch |

---

## Known risks and mitigations

| Risk | Mitigation |
|------|-----------|
| Gate 5 Chaos Rising data incomplete (<80%) | T+7d check tomorrow (2026-05-29); if <80%, extend window 3–7 days before Gate 7 |
| Gate 4 test predictions don't resolve correctly | Check scheduler_run_log + debug resolution logic before 7-day window expires |
| Smart sort threshold too tight/loose (Gate 7) | Threshold is configurable env var; flag distribution to Ivan for review |
| Paper predictions don't accumulate to 10 before June window | Widen target card list (Gate 8 spec says target cards — add more if needed) |
| Public dist rebuild breaks existing routes | Smoke test all routes (/calls, /market, /account, /pricing) after every dist rebuild |
