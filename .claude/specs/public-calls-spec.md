# Public Calls — System Spec

**Status:** Active. Compressed timeline.
**Soft launch:** June 14, 2026 (Chaos Rising cohort)
**Full launch:** July 17, 2026 (Pitch Black cohort + Pro tier)
**Showtime:** September 16-18, 2026 (30th Anniversary set)

---

## Mission

Public Calls is the AI narrative center of Flashcard Planet. It is a publicly auditable forecast system that makes our signal model accountable — predictions are locked at creation, resolved automatically against market data, and aggregated into a public calibration record.

**Positioning statement:**
> Flashcard Planet — the only TCG intelligence platform that publicly forecasts and grades its own accuracy.

This is unfakeable credibility. Competitors can't replicate without the discipline to be wrong publicly.

---

## Why this exists

Three converging insights from strategic conversation:

1. **Driver attribution** — every signal move has a cause (event-driven, supply shock, meta shift, macro, influencer provenance, unknown). Tier (BREAKOUT→COOLING) is direction; driver is cause. They are orthogonal dimensions.

2. **Fundamental delta** — for any card we can compute `actual_signal` vs `fundamental_signal` (ex-event baseline). The gap is hype premium. This is the killer Pro tier feature: "this card is X% above fundamental, driven by [event]".

3. **Polymarket-style calibration** — predictions with locked thresholds and resolution dates accumulate into Brier scores and reliability diagrams. The discipline is the product.

Reference inspirations:
- **Polymarket** — calibrated public forecasts; track record as media primitive
- **Logan Paul market influence** — proof that hype-driven price divergence from fundamentals exists and is exploitable
- **TradingView** — chrome, rigor, ownership of "the place serious people go"

---

## Architecture decisions (locked)

| Decision | Choice | Why |
|---|---|---|
| Driver attribution shape | Orthogonal dimension to tier (NOT a 6th tier) | Tier is direction; driver is cause. They are independent axes. |
| Calibration from Day 1 | Mandatory | No "we'll add it later." The discipline IS the credibility. |
| Public Calls URL | Independent at `/calls` | Top-of-funnel acquisition. Free to view; per-card attribution/fundamental delta Pro-gated. |
| First TCG | Pokemon only | YGO upside magnitude insufficient for first calibration cohort. Revisit Q4 2026. |
| Launch staging | Rehearsal → showtime | Chaos Rising soft launch builds track record before Pitch Black + Anniversary spotlight. |
| Prediction mutability | Immutable | Once `predicted_at` set, threshold + probability cannot change. DB-level audit trigger enforces. |
| Paper vs public calls | Cannot cherry-pick | Paper trades validate model only. Public calls are made fresh, not selected from paper pool. |

---

## Driver taxonomy (v0.1)

- `MACRO` — overall market or set-level trend
- `META_SHIFT` — competitive meta change (primarily YGO/MTG; rare for Pokemon)
- `SUPPLY_SHOCK` — reprint announcement, grading population update, sealed product release dilution
- `EVENT_DRIVEN` — influencer activity, YouTube videos, tournament results within explicit event windows
- `INFLUENCER_PROVENANCE` — celebrity-owned card premium (Logan Paul touched, etc.)
- `UNKNOWN` — model detected abnormal move but attribution unclear (this itself is honest signal)

Each prediction has one primary driver + confidence (0.0–1.0). Secondary drivers possible in future versions.

---

## Data model

```sql
CREATE TABLE predictions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    predicted_at TIMESTAMPTZ NOT NULL,           -- immutable after insert
    resolution_date TIMESTAMPTZ NOT NULL,         -- immutable after insert
    card_id INTEGER NOT NULL REFERENCES cards(id),
    prediction_text TEXT NOT NULL,                -- public-facing call statement
    threshold_value NUMERIC NOT NULL,
    threshold_currency TEXT NOT NULL DEFAULT 'USD',
    threshold_direction TEXT NOT NULL
        CHECK (threshold_direction IN ('above','below','within_band')),
    threshold_band_high NUMERIC,                  -- only used when direction='within_band'
    stated_probability NUMERIC NOT NULL
        CHECK (stated_probability BETWEEN 0 AND 1),
    driver_attribution TEXT,
    driver_confidence NUMERIC,
    methodology_version TEXT NOT NULL,            -- git commit hash or semver
    is_paper BOOLEAN NOT NULL DEFAULT TRUE,        -- only is_paper=FALSE shown publicly
    resolution_status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (resolution_status IN ('PENDING','HIT','MISS','AMBIGUOUS','VOIDED')),
    resolved_at TIMESTAMPTZ,
    actual_value NUMERIC,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Audit table for all changes to immutable columns
CREATE TABLE predictions_audit (
    audit_id BIGSERIAL PRIMARY KEY,
    prediction_id UUID NOT NULL,
    action TEXT NOT NULL,                          -- 'INSERT','UPDATE_BLOCKED','RESOLVE'
    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    changed_by TEXT,
    old_state JSONB,
    new_state JSONB
);

-- Trigger: block UPDATE on immutable columns
CREATE OR REPLACE FUNCTION predictions_immutable_check() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.predicted_at != OLD.predicted_at THEN
        RAISE EXCEPTION 'predicted_at is immutable';
    END IF;
    IF NEW.resolution_date != OLD.resolution_date THEN
        RAISE EXCEPTION 'resolution_date is immutable';
    END IF;
    IF NEW.threshold_value != OLD.threshold_value THEN
        RAISE EXCEPTION 'threshold_value is immutable';
    END IF;
    IF NEW.stated_probability != OLD.stated_probability THEN
        RAISE EXCEPTION 'stated_probability is immutable';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER predictions_block_immutable
    BEFORE UPDATE ON predictions
    FOR EACH ROW EXECUTE FUNCTION predictions_immutable_check();

-- Event registry for driver attribution
CREATE TABLE market_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_date TIMESTAMPTZ NOT NULL,
    event_type TEXT NOT NULL,                      -- INFLUENCER, SUPPLY, TOURNAMENT, RELEASE
    description TEXT NOT NULL,
    source_url TEXT,
    affected_card_ids INTEGER[],
    affected_set_ids TEXT[],
    expected_window_days INTEGER,                  -- expected price impact window
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_market_events_date ON market_events(event_date DESC);
CREATE INDEX idx_predictions_resolution ON predictions(resolution_date)
    WHERE resolution_status = 'PENDING';
```

---

## Calibration infrastructure

**Resolution scheduler:** APScheduler interval trigger, anchored at startup + 600s, every 4 hours. Logs to `scheduler_run_log` per convention.

**Brier score formula:**
- Per prediction: `BS_i = (stated_probability - actual_outcome)²` where actual ∈ {0, 1}
- Aggregate Brier: `mean(BS_i)` across all resolved
- Baseline Brier: 0.25 (always predict 50%)
- Lower is better; below 0.25 means model adds value

**Reliability diagram:**
- Bin predictions by `stated_probability` into deciles: [0,10%), [10,20%), ..., [90,100%]
- For each bin: plot (mean stated probability, actual hit rate)
- Perfect calibration: points lie on diagonal y=x
- Confidence intervals: Wilson 95% CI on hit rate per bin

**Honest n discipline:**
- Show calibration plot from n=1 (don't hide)
- Show "n=X resolved. Statistical significance at n≥30. Treat early calibration as directional only." when total resolved < 30
- This warning is a credibility asset, not a liability

---

## Public surface (/calls page)

Layout (top to bottom):

1. **Headline:** "We forecast. We grade ourselves. Here's the receipts."
2. **Running metrics row:**
   - Total calls made
   - Resolved hit rate
   - Brier score (with comparison to 0.25 baseline)
   - Methodology version
3. **Calibration plot** — reliability diagram with Wilson CI bars
4. **Live calls table** — sortable by status (PENDING/HIT/MISS), resolution_date, card
5. **Per-driver breakdown** — once n≥20 per driver category
6. **Methodology link** — to `/methodology` page with full documentation
7. **Honest n warning** — when total_resolved < 30

Design conventions:
- Follow `frontend/docs/svg-conventions.md` for `ReliabilityDiagram.tsx` (use `xScale`, `yOf`, `buildAreaPath` patterns)
- CSS vars: `var(--gold)` for hits, `var(--breakout)` for pending, neutral text for misses
- Space Mono for numbers, Syne for headlines
- Dark trading-desk aesthetic consistent with main app

Free vs Pro:
- **Free:** all of /calls page (calls table, calibration plot, Brier score)
- **Pro:** per-card driver attribution detail page, fundamental delta visualization, custom alerts on prediction resolutions

---

## Decisions deferred

- User-submitted prediction challenges (community feature — revisit Q4 2026)
- Confidence intervals on predictions (vs point probabilities only) — start with point estimates
- Cross-TCG calls — YGO eligible after Phase 2 production validation; MTG never (not in product scope)
- Multi-card index calls (e.g., "Pokemon market cap above $X") — Phase 2 of Public Calls

---

## Out of scope

- Betting / financial transactions on predictions (regulatory complexity; not the product)
- Fractional ownership of predicted cards (Liquid Marketplace lesson: retail doesn't buy that)
- Social voting / community sentiment on predictions (not signal-first; not founder-led)
- Automated trading signal generation for users to act on (out of scope; intelligence not execution)

---

## References

- Strategic conversation: claude.ai session 2026-05-18 (Logan Paul + Polymarket + driver attribution synthesis)
- Polymarket calibration methodology: public reliability diagrams
- Existing platform: `signal_service.py`, `liquidity_service.py`, `scheduler_run_log` convention
- Frontend conventions: `frontend/docs/svg-conventions.md`
- Related TASK: TASK-301 Pro tier launch (coupled to Pitch Black July 17)
