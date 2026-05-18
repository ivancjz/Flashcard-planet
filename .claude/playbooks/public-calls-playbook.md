# Public Calls — Executable Playbook

**Companion to:** `.claude/specs/public-calls-spec.md` (read first for decisions and data model)
**Audience:** Fresh Claude Code session — self-contained execution guide
**Soft launch target:** June 14, 2026
**Full launch target:** July 17, 2026 (coupled to Pitch Black set + Pro tier TASK-301)

---

## Working principles (READ BEFORE STARTING ANY PHASE)

These are inviolable per repo CLAUDE.md and prior learnings. Re-read every session.

1. **Merge ≠ deploy ≠ verified.** Every production change is confirmed via:
   - SQL query against `scheduler_run_log` showing successful execution
   - Discord alert observation where applicable
   - Direct DB inspection of expected data
   Local fixes are NOT live until verified in production.

2. **Designed but never ran is the anti-pattern.** No phase is complete until production verification passes. New features must be observed running in production, not just code-reviewed.

3. **Scheduler conventions:**
   - Anchor to deploy startup + stagger seconds (NOT cron)
   - Use APScheduler interval triggers
   - Log every run to `scheduler_run_log` table
   - Use unique `job_name` per scheduler job
   - Set `_STARTUP_DELAY` to avoid startup contention

4. **Branch convention:**
   - `feat/public-calls-phase-N` per phase
   - All merges via PR
   - **Codex review gate mandatory** — wait for `## Codex Review` section before merge
   - Push to main allowed within project boundary trust

5. **File editing:** route through Claude Code tools, never paste multi-line content into PowerShell.

6. **Three-way disagreement protocol:** when Claude.ai (strategy) and Claude Code (execution) and Ivan disagree:
   - Each party states position once
   - Ivan decides
   - Log decision in `.claude/decisions.md`

---

## Phase 1 — Foundation (May 18-24)

**Branch:** `feat/public-calls-phase-1`
**Goal:** Database schema, immutability enforcement, basic services.

### Build checklist
- [ ] Alembic migration: create `predictions`, `predictions_audit`, `market_events` tables (schemas in spec)
- [ ] Apply audit trigger `predictions_immutable_check` on UPDATE
- [ ] SQLAlchemy 2 models for all three tables in `backend/app/models/predictions.py`
- [ ] Service module `backend/app/services/prediction_service.py` with:
  - `create_prediction(card_id, prediction_text, threshold_value, threshold_direction, stated_probability, resolution_date, driver_attribution, methodology_version, is_paper=True) -> UUID`
  - `resolve_prediction(prediction_id, actual_value, resolved_at) -> PredictionResolution`
  - `get_calibration_metrics(only_public=True) -> CalibrationMetrics`
- [ ] Seed `market_events` with last 12 months of curated Pokemon events:
  - Logan Paul box breaks (with dates from public sources)
  - Major reprint announcements (e.g., Destined Rivals reprint announcement)
  - PSA pop report shocks for high-value cards
  - Set release dates with affected `set_id` arrays
  - Aim for n=20-30 events to enable attribution rules in Phase 3

### Production verification gate (must pass before merge)
- [ ] Run `psql` on Railway staging: `\d predictions` shows all columns + constraints
- [ ] Test immutability: attempt `UPDATE predictions SET predicted_at = NOW() WHERE id = ?` — expect exception "predicted_at is immutable"
- [ ] Insert test prediction, resolve it, verify `predictions_audit` has both events
- [ ] `SELECT COUNT(*) FROM market_events` returns ≥ 20

### Codex review focus
- Schema constraints (CHECK clauses, NOT NULL discipline)
- Audit trigger completeness (all 4 immutable columns blocked)
- Service-level test coverage

---

## Phase 2 — Calibration Page Shell (May 25-31)

**Branch:** `feat/public-calls-phase-2`
**Goal:** Public `/calls` page deployed with empty state. No predictions yet visible.

### Build checklist

**Backend:**
- [ ] Endpoint `GET /api/v1/calls/list?status=pending|resolved|all` — returns only `is_paper=false`
- [ ] Endpoint `GET /api/v1/calls/calibration` — returns:
  ```json
  {
    "total_calls": N,
    "total_resolved": N,
    "brier_score": 0.XX,
    "brier_baseline": 0.25,
    "reliability_bins": [
      {"prob_bin_low": 0.0, "prob_bin_high": 0.1, "n": N, "hit_rate": 0.X, "ci_low": 0.X, "ci_high": 0.X},
      ...
    ],
    "methodology_version": "v0.1-{commit_hash}"
  }
  ```
- [ ] Endpoint `GET /api/v1/calls/{prediction_id}` — single call detail

**Frontend:**
- [ ] New route `/calls` in router, NOT under main app shell — independent layout
- [ ] `CallsPage.tsx` — headline, metrics row, calibration plot, calls table
- [ ] `ReliabilityDiagram.tsx` — SVG component following `frontend/docs/svg-conventions.md`:
  - Use `xScale`, `yOf` patterns from existing chart components
  - CSS vars: `var(--gold)` for hits, `var(--breakout)` for pending, `var(--text-secondary)` for misses
  - Diagonal reference line (y=x = perfect calibration)
  - Bin dots sized by n in bin
  - Wilson CI bars
- [ ] `CallsTable.tsx` — sortable table of predictions
- [ ] `HonestNWarning.tsx` — visible when `total_resolved < 30`
- [ ] Empty state: "First calibration cohort launches June 14, 2026. Watch this space."

### Production verification gate
- [ ] Visit `https://flashcardplanet.com/calls` in production browser
- [ ] Empty state renders correctly, looks intentional
- [ ] API endpoints return valid empty-state JSON
- [ ] No console errors in browser

### Codex review focus
- Route isolation from main app (independent layout)
- Frontend follows `svg-conventions.md` patterns
- API responses match documented schema

---

## Phase 3 — Driver Attribution + Internal Validation (June 1-7)

**Branch:** `feat/public-calls-phase-3`
**Goal:** Driver attribution rule engine v1. Internal paper trades on Chaos Rising for model validation. **PAPER CALLS ARE NOT SHOWN PUBLICLY AND ARE NEVER CONVERTED TO PUBLIC CALLS.**

### Build checklist

- [ ] `backend/app/services/driver_attribution_service.py`:
  - `attribute_signal(card_id, signal_move_pct, signal_window_days) -> DriverAttribution`
  - Rule-based v1 logic:
    1. Check `market_events` for events within `signal_window_days` window touching this `card_id` → `EVENT_DRIVEN` with confidence proportional to event recency
    2. Check set-wide breadth (% of cards in same set showing similar signal direction) → if > 60%, `MACRO`
    3. Check supply events (reprint announcements, pop changes) → `SUPPLY_SHOCK`
    4. Default: `UNKNOWN` with low confidence

- [ ] `backend/app/services/fundamental_signal_service.py`:
  - `compute_fundamental_signal(card_id) -> SignalEstimate`
  - Remove price data points within ±7d of any `market_event` touching this card
  - Recompute signal on cleaned data
  - Return both `actual_signal` and `fundamental_signal` + delta

- [ ] Internal admin UI: `/admin/predictions/new` — only accessible to authenticated admin
  - Form to create predictions with `is_paper=TRUE` default
  - Show driver attribution suggestion from service

- [ ] Test driver attribution against 5+ historical events with known outcomes (e.g., past Logan Paul box break → cards in event should attribute as EVENT_DRIVEN)

- [ ] **Generate 8-10 paper predictions on Chaos Rising chase cards** (set released May 22, paper window opens ~10 days post-release):
  - Mega Greninja ex SIR (variants: PSA 10, raw)
  - Mega Floette ex SIR
  - Mega Pyroar ex SIR
  - Mega Dragalge ex SIR
  - Chaos Rising ETB sealed
  - Chaos Rising booster box sealed
  - Mix bullish/bearish, mix time windows (30d / 60d / 90d), mix probability levels (40% / 60% / 75%)
  - All marked `is_paper=TRUE`

### Production verification gate
- [ ] `SELECT COUNT(*) FROM predictions WHERE is_paper=TRUE` returns ≥ 8
- [ ] Driver attribution service tested against ≥ 5 historical cases, accuracy logged
- [ ] Fundamental signal service computes ex-event baseline for ≥ 3 sample cards, results sanity-checked

### Codex review focus
- Driver attribution rule logic (edge cases, confidence calibration)
- Paper-only enforcement (no code path that promotes paper to public)
- Service test coverage

---

## Phase 4 — Soft Launch (June 8-14)

**Branch:** `feat/public-calls-phase-4`
**Goal:** First public calls live on June 14.

### CRITICAL: cherry-picking prevention
Paper predictions from Phase 3 are for **model validation only**. Public calls in Phase 4 are made **fresh**, not selected from paper pool. This is non-negotiable — selecting paper calls to go public is cherry-picking and undermines calibration credibility.

### Build checklist

- [ ] Resolution scheduler: APScheduler interval job
  - `job_name = "resolve_predictions"`
  - Anchor: `startup + 600s`, interval `4 hours`
  - Logs to `scheduler_run_log`
  - For each PENDING with `resolution_date <= NOW()`: fetch latest market price for card, compare to threshold per direction, write HIT/MISS, update `resolved_at`, `actual_value`

- [ ] Resolution Discord webhook integration
  - On each HIT/MISS: post embed with call summary, predicted prob, actual value, status
  - Use existing Discord alerts module

- [ ] Methodology page draft at `/methodology`
  - Driver taxonomy explained
  - Brier score formula
  - Reliability diagram interpretation
  - Honest about limitations and model version history
  - Linked from `/calls`

- [ ] **First public call cohort generated June 13** (day before launch):
  - 4-6 fresh public predictions on Chaos Rising cards
  - Each call: clear prediction_text, threshold, probability, driver, methodology_version (git commit hash)
  - Resolution dates: all within next 60 days for fast feedback loop
  - Diversity: at least 1 bullish, at least 1 bearish, range of probability levels

- [ ] Pre-launch checklist:
  - [ ] All public calls have valid driver_attribution + methodology_version
  - [ ] All resolution dates ≥ 14 days out, ≤ 60 days out
  - [ ] /calls page displays calls correctly in staging
  - [ ] Discord webhook tested with manual resolution trigger

### Production verification gate (LAUNCH DAY June 14)
- [ ] `SELECT * FROM predictions WHERE is_paper=FALSE` returns 4-6 rows
- [ ] `SELECT * FROM scheduler_run_log WHERE job_name='resolve_predictions' ORDER BY started_at DESC LIMIT 5` shows scheduled future runs
- [ ] Visit `/calls` in production browser, confirm all calls render
- [ ] Manually trigger resolution job in staging with a fake PENDING call whose `resolution_date` is in the past — confirm Discord alert fires + DB updates correctly
- [ ] Methodology page accessible at `/methodology` and linked from `/calls`

### Launch announcement
- Twitter / X post: link to /calls, posture is "first cohort, honest about n, watch us evolve"
- Email digest insert for next weekly digest
- Posture: NOT "AI predicts!" but "We forecast. We grade ourselves. Here's the receipts."

---

## Phase 5-7 — Iterate (June 15 – July 12)

**Branches:** `feat/public-calls-phase-N` per significant change

Continuous activities:
- [ ] Monitor resolution outcomes daily via /calls page
- [ ] Add 2-4 new public calls per week as opportunities emerge (signal model flags + manual review)
- [ ] Refine driver attribution rules based on observed hit/miss patterns
- [ ] Bump `methodology_version` for any rule change — log in `.claude/methodology-changelog.md`
- [ ] Target: n ≥ 15 resolved calls by July 12

Weekly review checkpoint (Mondays):
- Review resolved calls — were misses due to bad model or bad event windowing?
- Review pending calls — anything looking like it will resolve incorrectly?
- Update methodology if rule change needed
- Codex review on any methodology change

---

## Phase 8 — Pitch Black Full Launch + Pro Tier (July 6-17)

**Branch:** `feat/public-calls-phase-8`
**Coupling:** TASK-301 (Pro tier launch) coupled to this phase.

### Build checklist
- [ ] Pre-release call cohort: 6-8 fresh public calls on Pitch Black chase cards (set drops July 17)
  - Mega Darkrai-ex
  - Mega Zeraora-ex
  - Mega Chandelure-ex
  - Mega Excadrill-ex
  - Pitch Black ETB sealed
  - Pitch Black booster box sealed
  - Generated July 14-16 before set drop

- [ ] Pro tier features deployed:
  - Per-card driver attribution detail pages (Pro-gated)
  - Fundamental delta visualization on card detail (Pro-gated)
  - Custom alerts on prediction resolutions (Pro-gated)

- [ ] Pricing page references calibration track record
- [ ] PR push: methodology page polished, calibration plot now shows Chaos Rising track record + Pitch Black launch cohort

### Production verification gate
- [ ] All pre-release Pitch Black calls live on /calls by July 16 EOD
- [ ] Pro tier feature flags enabled in production
- [ ] Pricing page reflects new positioning
- [ ] At least 12+ resolved calls visible in calibration plot

---

## Decision log discipline

For every meaningful decision made during execution (e.g., driver attribution edge case rules, calibration display tweaks), append to `.claude/public-calls-decisions.md` with format:

```markdown
## 2026-MM-DD: [Decision title]
- Context: ...
- Options considered: ...
- Choice: ...
- Rationale: ...
```

This creates an audit trail for future Claude sessions and for Ivan to review.

---

## What to do if a verification gate fails

1. **Do not merge.** No exceptions.
2. Document failure in PR description:
   - What was expected
   - What happened
   - Hypothesis on cause
   - Proposed next step
3. Surface to Ivan with explicit ask
4. If three-way disagreement on resolution — invoke protocol

---

## Reference materials

- Spec doc: `.claude/specs/public-calls-spec.md`
- Repo conventions: `CLAUDE.md` (root)
- Frontend conventions: `frontend/docs/svg-conventions.md`
- Scheduler patterns: existing jobs in `backend/app/scheduler/`
- Related: TASK-301 (Pro tier), `signal_service.py`, `liquidity_service.py`
- Existing audit pattern: `scheduler_run_log` table
