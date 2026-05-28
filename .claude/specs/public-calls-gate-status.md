# Public Calls — Gate Status

Last updated: 2026-05-28

---

- [x] **Gate 1: Backend services** (2026-05-19, PR #73)
  - `driver_attribution_service.py`, `fundamental_signal_service.py`, admin UI live
  - Unit tests passing. Codex review clean.

- [x] **Gate 2: Driver attribution validation** (2026-05-23, commits 61d5139–205c388)
  - Production re-run: **7/7 testable cases PASS, 100% EVENT_DRIVEN accuracy**
  - All 7 RELEASE events have verified headline card UUIDs in `affected_asset_ids`
  - Validation report: `validation_reports/driver_attribution_v1.md`
  - Ivan decision required: approve accuracy + close Gate 2 formally

- [ ] **Gate 3: Fundamental signal sanity check** — awaiting Gate 2 Ivan sign-off

- [ ] **Gate 4: Resolution scheduler staging** (test predictions injected 2026-05-23)
  - `_run_resolve_predictions()` implemented in `scheduler.py` (PR #73)
  - Kill switch: `RESOLVE_PREDICTIONS_ENABLED=false` (Category β, default off)
  - **5 test predictions injected** (`methodology_version='gate4-b2-test'`, all PENDING):
    - Charizard above $500 → expected HIT (actual $595.18)
    - Alakazam below $100 → expected HIT (actual $76.62)
    - Clefairy within $30–$45 → expected HIT (actual $36.51)
    - Blastoise above $300 → expected MISS (actual $220.81)
    - Chansey below $40 → expected MISS (actual $53.09)
  - **Ivan action needed:** set `RESOLVE_PREDICTIONS_ENABLED=true` in Railway to start 7-day window
  - Observation window: 7 consecutive days from when kill switch enabled

- [ ] **Gate 5: Chaos Rising data baseline** — starts 2026-05-22 (set release). me4 in TIER1_BULK_SET_IDS since 2026-05-23 commit 05f2f28.

- [x] **Gate 6: Methodology page** — LIVE 2026-05-28 (commits 1cf152a + 545ec20)
  - All 10 spec sections implemented in `frontend/src/pages/calls/MethodologyPage.tsx`
  - Route `/methodology` live. Hardcoded methodology version "v0.1" (auto-pull from git SHA deferred).

- [ ] **Gate 7: Smart sort calibration** — depends on Gate 5

- [ ] **Gate 8: Paper trade validation** — depends on Gates 2+3+5
  - Window opens ~2026-06-01. Minimum 10 paper predictions required.
  - Cards: Mega Greninja ex SIR, Mega Floette ex SIR, Mega Pyroar ex SIR, Mega Dragalge ex SIR, Chaos Rising ETB, booster box.

- [ ] **Gate 9: Fresh public calls cohort** — depends on Gates 1-8

- [ ] **Gate 10: Frontend changes** — depends on Gates 6+7+9

- [ ] **Gate 5: Chaos Rising data baseline** — T+7d check 2026-05-29 (TOMORROW)

- [ ] **Gate 7: Smart sort calibration** — depends on Gate 5

- [ ] **Gate 8: Paper trade validation** — depends on Gates 2+3+5

- [ ] **Gate 9: Fresh public calls cohort** — depends on Gates 1-8

- [ ] **Gate 10: Frontend changes** — depends on Gates 6+7+9

---

## Gate 4 staging decision

The spec says "deploy to staging (NOT production)" but the project runs on a Railway Hobby
plan with a single environment. Options:

**Option A (recommended):** Enable kill switch in production for 7 days of observation.
- Set `RESOLVE_PREDICTIONS_ENABLED=true` in Railway
- Inject ≥5 test predictions with `resolution_date` in the past
- Verify they resolve correctly within 4h
- Monitor `scheduler_run_log` for 7 days of clean runs
- Discord webhooks confirm embeds render correctly
- After 7 days: Gate 4 passes. Kill switch stays on.

**Option B:** Create a Railway staging project (requires manual setup, ~AUD 5/mo extra).

Ivan decides.
