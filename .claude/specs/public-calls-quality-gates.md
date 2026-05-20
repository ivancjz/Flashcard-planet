# Public Calls — Quality Gates

**Status:** Active. No launch date.
**Companion to:** `.claude/specs/public-calls-spec.md`, `.claude/playbooks/public-calls-playbook.md`
**Philosophy lock (2026-05-19):** Quality first, no timeline pressure. Launch when ready. Pitch Black (July 17) and 30th Anniversary (September) are market events to observe, not launch deadlines.

---

## Why this exists

The compressed 9-day timeline considered on 2026-05-19 was rejected in favor of quality-first execution. Reason: Public Calls is a credibility-anchored product. Shipping with imperfect calibration, half-validated driver attribution, or rushed methodology damages the credibility moat permanently. A 2-week delay to ship correctly is invisible to users. A single bad calibration launch is not.

These 10 gates exist to enforce that discipline. Each gate is binary (pass / not pass) and Ivan-approved.

---

## Gate 1 — Backend services built & tested

**What:**
- `backend/app/services/driver_attribution_service.py` implemented per spec
- `backend/app/services/fundamental_signal_service.py` implemented per spec
- Internal admin UI `/admin/predictions/new` working (is_paper=TRUE by default)

**Verification:**
- Unit tests ≥80% coverage on both services
- Each service has dedicated test file with edge cases
- Admin UI accessible via authenticated route only
- Codex review clean (no P0/P1 issues)

**Pass criteria:** All tests pass + Ivan reads service code + approves architecture.

**Not pass means:** Iterate, do not advance to Gate 2.

---

## Gate 2 — Driver attribution validated against history

**What:**
- Test driver attribution rule engine against ≥10 historical market events (drawn from `market_events` table)
- Each historical event has expected primary driver + known outcome
- Produce written validation report: per-event attribution result + confidence + reasoning

**Verification:**
- Validation harness script in `scripts/validate_driver_attribution.py`
- Report output to `validation_reports/driver_attribution_v1.md`
- Each test case documented: event description, expected driver, actual driver, confidence, pass/fail

**Pass criteria:**
- Ivan reviews validation report
- Accuracy threshold: **TBD by Ivan based on initial results, not pre-set**
- If accuracy unsatisfactory → iterate rules, retest, repeat until Ivan trustworthy

**Not pass means:** Rule engine v1 inadequate. Iterate before advancing.

---

## Gate 3 — Fundamental signal sanity checked

**What:**
- Apply `compute_fundamental_signal(card_id)` to ≥20 cards across price tiers
- Distribution: ~5 cards each at $1, $10, $100, $1000+ price tiers
- Edge cases tested: card with no events, card with overlapping events, card with sparse data

**Verification:**
- Sanity check report `validation_reports/fundamental_signal_v1.md`
- Each card: actual_signal, fundamental_signal, delta, reasoning
- Ivan spot-checks ≥5 cards manually — do delta numbers make intuitive sense?

**Pass criteria:**
- No card shows >200% delta as a bug (must be explainable as legitimate hype premium)
- No NaN, no infinity, no negative-baseline edge case failures
- Ivan signs off on sample of 5+ cards

**Not pass means:** Fundamental signal logic flawed. Fix before advancing.

---

## Gate 4 — Resolution scheduler proven in staging

**What:**
- APScheduler interval job `resolve_predictions` deployed to staging
- Anchored at startup + 600s, interval 4 hours
- Logs to `scheduler_run_log` per repo convention
- Discord webhook integration on HIT/MISS

**Verification:**
- Run continuously for **≥7 consecutive days** in staging
- Inject ≥5 test predictions with resolution_date in past → confirm HIT/MISS detection correct
- Discord webhook tested end-to-end (manual fake call → see Discord embed)
- `scheduler_run_log` shows successful runs every 4 hours for 7 days

**Pass criteria:**
- 0 unexplained scheduler failures during 7-day observation window
- All 5+ test resolutions correctly classified
- Discord embeds render correctly

**Not pass means:** Scheduler not reliable enough for production credibility-anchored use. Fix before advancing.

---

## Gate 5 — Chaos Rising data baseline collected

**What:**
- After 2026-05-22 release, collect ≥2 weeks of price data on chase cards
- Cards required: Mega Greninja ex (SIR + Mega Hyper Rare), Mega Floette ex (SIR), Mega Pyroar ex (SIR), Mega Dragalge ex (SIR), Chaos Rising ETB sealed, Chaos Rising booster box sealed

**Verification:**
- SQL query showing daily price points for each card across 14+ days
- Data sources: TCGPlayer market price + CardMarket avg7/avg30 (if applicable)
- No card with <50% data completeness over the 14-day window

**Pass criteria:**
- All 6+ chase cards have ≥14 consecutive days of price data
- Data completeness ≥80% across all cards
- No suspicious gaps or anomalies in ingestion

**Not pass means:** Insufficient data foundation for confident calls. Extend collection window.

---

## Gate 6 — Methodology page written & reviewed

**What:**
- Spec drafted by claude.ai session (`.claude/specs/methodology-page-spec.md`)
- Implementation by Claude Code per spec
- Methodology page live at `/methodology`
- Linked from `/calls` and from landing page footer

**Verification:**
- Page renders correctly in staging
- All internal links work
- Codex review clean
- Ivan reads end-to-end **at least twice** (separated by ≥24h to catch issues fresh)
- Every claim has math/citation backing (no naked claims)

**Pass criteria:**
- Methodology page is a document Ivan would be comfortable being publicly judged on
- Contains: driver taxonomy, Brier score formula, reliability diagram explanation, methodology version log, known limitations, honest n discipline
- No marketing copy. No vibes. Just methodology.

**Not pass means:** Page not credibility-anchor-grade. Rewrite.

---

## Gate 7 — Smart sort calibrated on real data

**What:**
- After Gate 5 passes (≥2 weeks Chaos Rising data accumulated)
- Apply smart sort formula to full Pokemon card universe
- Generate top-50 sorted list

**Verification:**
- Top-50 list written to `validation_reports/smart_sort_top50_v1.md`
- Includes card name, set, price floor, signal tier, sort score
- Side-by-side comparison: smart sort top-50 vs current % Change top-50

**Pass criteria:**
- Ivan reviews top-50 list
- Ivan confirms: "these are the cards a serious investor would want to see first"
- If feedback like "too much weight on price" or "BREAKOUT not strong enough" → adjust weights, regenerate, repeat until Ivan approval

**Default formula (subject to calibration):**
```
score = signal_weight × log10(max(price_floor, 1)) × data_quality × freshness

signal_weight: BREAKOUT=8, MOVE=3, WATCH=1, IDLE=0.3
data_quality:  1.0 (full) / 0.6 (partial) / 0.2 (sparse)
freshness:     1.2 (<3d) / 1.0 (3-7d) / 0.7 (7-14d) / 0.3 (>14d)
```

**Not pass means:** Default formula inadequate for visible universe. Iterate.

---

## Gate 8 — Paper trade validation

**What:**
- ≥10 paper predictions made on Chaos Rising chase cards (is_paper=TRUE)
- Run for ≥30 days, allowing calls to resolve naturally
- Compute paper-trade Brier score

**Verification:**
- Paper predictions cover: bullish/bearish mix, 7d/14d/30d/60d window mix, 40%/60%/75% probability levels
- Brier score computed across all resolved paper trades
- Per-window accuracy breakdown
- Per-driver accuracy breakdown (if drivers diverse enough)

**Pass criteria:**
- Paper Brier score **< 0.25 baseline** (model adds value vs always-50%)
- **≥60% of high-confidence (>70%) paper calls hit**
- No systematic bias detected (e.g. always-bearish, always-MOVE driver)

**Not pass means:** Model not yet trustworthy enough for public calls. Iterate driver attribution and reversion modeling. Run another paper cohort.

---

## Gate 9 — Fresh public calls cohort generated

**What:**
- Only after Gates 1-8 all pass
- 4-6 fresh predictions made on Chaos Rising chase cards
- Marked is_paper=FALSE
- **Not selected from paper pool** — generated fresh

**Verification:**
- Each call independently reviewed by Ivan before going public
- methodology_version locked at current git commit hash
- Each call has: clear prediction_text, threshold, direction, probability, driver, resolution_date
- Mix of bullish/bearish, mix of windows, mix of probability levels

**Pass criteria:**
- Ivan approves each call individually
- All calls pass Codex review on prediction text quality
- Resolution dates spread across 14-90 day windows

**Not pass means:** Cohort not ready. Iterate or wait.

---

## Gate 10 — Frontend changes shipped & verified

**What:**
- FE-1: Landing hero metric replacement (replaces "0 Breakout signals")
- FE-2: Market page smart default sort (depends on Gate 7)
- FE-3: Pro tier copy rewrite
- FE-4: Methodology page (depends on Gate 6)

**Verification:**
- All 4 PRs merged with Codex review
- Production verification screenshots
- Live tested by Ivan on production URL
- No regressions on existing pages

**Pass criteria:**
- FE-1, FE-3 can ship independently (don't depend on calibration data)
- FE-2 ships after Gate 7 passes
- FE-4 ships after Gate 6 passes
- All 4 must be live before public launch

**Not pass means:** Frontend not ready. Iterate.

---

## Launch day

**Launch day = the day all 10 gates pass + Ivan says "go".**

Possible scenarios:
- Earliest realistic: late June if everything passes first try
- Realistic: July or later if iteration needed on any gate
- Latest acceptable: whenever quality bar is met

Pitch Black (July 17) is a market event to observe regardless of launch state:
- If launched before Pitch Black → Pitch Black becomes showcase
- If not yet launched → observe Pitch Black market dynamics as additional calibration data

30th Anniversary (September) is the real "showtime" anchor.

---

## Gate dependency graph

```
Gate 1 (services built) ──┬─→ Gate 2 (driver attr validated)
                          └─→ Gate 3 (fundamental signal sanity)

Gate 4 (scheduler in staging) — independent, can run parallel

Gate 5 (Chaos Rising data, after May 22) ──→ Gate 7 (smart sort calibration)
                                        └──→ Gate 8 (paper trades)

Gate 6 (methodology page) — depends on claude.ai spec delivery

Gates 1-8 all pass ──→ Gate 9 (fresh public calls)

Gates 6, 7 pass ──→ FE-2, FE-4 ship
Gate 9 pass     ──→ public launch

Gate 10 (all FE merged) ──→ ready for launch
```

---

## Anti-patterns this prevents

1. **"Designed but never ran"** — every gate requires verification, not just code review
2. **"Confident first-pass conclusions"** — Gate 2 and 3 require explicit Ivan sign-off on results
3. **"Date-driven shipping"** — no gate references a date; only readiness
4. **"Cherry-picking paper calls"** — Gate 9 explicitly requires fresh calls, not paper pool selection
5. **"Vibes-based AI claims"** — Gate 6 methodology page requires math/citation for every claim
6. **"Calibration retrofit"** — Gate 8 paper validation must happen before public calls, not after

---

## Tracking

Maintain a checklist in `.claude/public-calls-gate-status.md` updated after each gate review:

```markdown
- [x] Gate 1: Backend services (2026-05-XX, PR #XX)
- [ ] Gate 2: Driver attribution validation
- [ ] Gate 3: Fundamental signal sanity
- [ ] Gate 4: Scheduler in staging (started 2026-05-XX)
- [ ] Gate 5: Chaos Rising data (started 2026-05-22)
- [ ] Gate 6: Methodology page
- [ ] Gate 7: Smart sort calibration
- [ ] Gate 8: Paper trade validation
- [ ] Gate 9: Fresh public calls cohort
- [ ] Gate 10: Frontend changes shipped
```

Each completed gate gets a brief summary and link to verification artifact.
