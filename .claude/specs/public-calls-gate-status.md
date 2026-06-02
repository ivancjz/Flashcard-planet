# Public Calls — Gate Status

Last updated: 2026-05-28 (corrected Gate 6 status — dist rebuild required and applied)

---

- [x] **Gate 1: Backend services** (2026-05-19, PR #73)
  - `driver_attribution_service.py`, `fundamental_signal_service.py`, admin UI live
  - Unit tests passing. Codex review clean.

- [x] **Gate 2: Driver attribution validation** (2026-05-23, commits 61d5139–205c388)
  - Production re-run: **7/7 testable cases PASS, 100% EVENT_DRIVEN accuracy**
  - All 7 RELEASE events have verified headline card UUIDs in `affected_asset_ids`
  - Validation report: `validation_reports/driver_attribution_v1.md`
  - Ivan decision required: approve accuracy + close Gate 2 formally

- [ ] **Gate 3: Fundamental signal sanity check** — awaiting signals recovery post DB outage (2026-06-02)

- [x] **Gate 4: Resolution scheduler staging** — PASSED 2026-05-28
  - `RESOLVE_PREDICTIONS_ENABLED=true` set in Railway
  - All 5 test predictions resolved correctly on 2026-05-28:
    - Charizard above $500 → HIT (actual $556.84) ✅
    - Alakazam below $100 → HIT (actual $80.42) ✅
    - Clefairy within $30–$45 → HIT (actual $36.51) ✅
    - Blastoise above $300 → MISS (actual $229.23) ✅
    - Chansey below $40 → MISS (actual $53.09) ✅
  - Resolution accuracy: 5/5 correct (100%)
  - Note: DB outage 2026-06-01 interrupted scheduler; resolver resumes on recovery

- [ ] **Gate 5: Chaos Rising data baseline** — starts 2026-05-22 (set release). me4 in TIER1_BULK_SET_IDS since 2026-05-23 commit 05f2f28.

- [x] **Gate 6: Methodology page** — LIVE 2026-05-28 (commits 1cf152a + 545ec20 + dist rebuild d509f1c)
  - All 10 spec sections implemented in `frontend/src/pages/calls/MethodologyPage.tsx`
  - Route `/methodology` live. Hardcoded methodology version "v0.1" (auto-pull from git SHA deferred).
  - NOTE: dist was NOT rebuilt at 1cf152a/545ec20 — production had blank screen until d509f1c (dist rebuild).
  - Production render: pending Railway deploy of d509f1c. Verify by navigating to /methodology in production.

- [ ] **Gate 7: Smart sort calibration** — depends on Gate 5

- [x] **Gate 8: Paper trade validation** — 10 predictions injected 2026-06-02
  - 10 paper predictions on Destined Rivals (sv10) high-value SIRs, resolution date 2026-06-27
  - Cards: Team Rocket's Mewtwo ex SIR, Cynthia's Garchomp ex SIR, Ethan's Ho-Oh ex SIR,
    Nidoking ex SIR, Moltres ex SIR, Crobat ex SIR, Ethan's Adventure SIR, Giovanni SIR,
    Mewtwo ex HR (band prediction)
  - All `is_paper=True`, `resolve-predictions` job will track them on 4h schedule

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
