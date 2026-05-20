# Public Calls — Gate Status

Last updated: 2026-05-21

---

- [x] **Gate 1: Backend services** (2026-05-19, PR #73)
  - `driver_attribution_service.py`, `fundamental_signal_service.py`, admin UI live
  - Unit tests passing. Codex review clean.

- [ ] **Gate 2: Driver attribution validation** (started 2026-05-21)
  - Harness: `scripts/validate_driver_attribution.py`
  - Report: `validation_reports/driver_attribution_v1.md`
  - **Local DB result: 35.3% strict accuracy (12/34 cases)**
  - SUPPLY_SHOCK: 83%. EVENT_DRIVEN: 40%. MACRO: 0% (local DB gap, not production result).
  - **Blocker:** Railway CLI needs re-login. Re-run on production for authoritative MACRO numbers.
  - **Ivan to decide:** accuracy threshold after reviewing report + production re-run.

- [ ] **Gate 3: Fundamental signal sanity check** — awaiting Gate 2 pass

- [ ] **Gate 4: Resolution scheduler staging** (started 2026-05-21)
  - `_run_resolve_predictions()` implemented in `scheduler.py`
  - Kill switch: `RESOLVE_PREDICTIONS_ENABLED=false` (default off, Category β)
  - **Staging blocker:** Project is Railway Hobby plan — no separate staging environment.
  - **Ivan to decide:** staging strategy (see note below).
  - Observation window: 7 consecutive days once enabled.

- [ ] **Gate 5: Chaos Rising data baseline** — starts 2026-05-22 (set release)

- [ ] **Gate 6: Methodology page** — awaiting spec finalization

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
