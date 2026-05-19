# Methodology Page Spec

**Status:** Draft for implementation
**URL:** `/methodology`
**Purpose:** Credibility anchor for Public Calls. Single source of truth for how Flashcard Planet generates, locks, resolves, and grades predictions.
**Companion to:** `.claude/specs/public-calls-spec.md`, `.claude/specs/public-calls-quality-gates.md`

---

## Why this page exists

Without methodology, "AI-powered predictions" are vibes. Methodology is what transforms a forecast into a calibrated signal. This page is the credibility moat — readable by a critical user with a finance/data background who will judge whether the math actually checks out.

Three audiences:
1. **Serious investors** evaluating whether to trust Flashcard Planet's signals
2. **Journalists / media** considering citing Flashcard Planet's probability numbers
3. **Future Flashcard Planet team / partners** needing canonical reference

If any of these three reads this page and finds it shallow, marketing-y, or full of unsubstantiated claims — the page failed. Better to be technically dense than aspirationally vague.

---

## Voice & tone

**Do:**
- Plain technical English. Treat reader as competent.
- State limitations openly. "We don't know" is more credible than overclaim.
- Show math. Brier score formula. Wilson CI formula. Driver attribution rules.
- Cite sources. Polymarket calibration methodology. Brier (1950). Wilson (1927).
- Acknowledge "honest n" — when statistical significance hasn't been reached.

**Don't:**
- Marketing language. "Cutting-edge", "industry-leading", "AI-powered" — none of these appear.
- Vague qualifiers. "Significantly", "highly accurate", "robust" — replace with numbers.
- Vibes claims without backing math.
- Hide methodology behind "trade secret" hand-waving. If we can't explain it, we don't trust it ourselves.

---

## Page structure

```
1. Header
2. What this page is (1 paragraph)
3. The four parts of a Flashcard Planet prediction
4. Driver attribution
5. Brier score & calibration
6. Reliability diagram
7. Honest n discipline
8. Methodology version log
9. Known limitations
10. Sources & references
```

---

## Section content

### 1. Header

```
Methodology

Flashcard Planet publishes forecasts and grades its own accuracy.
This page documents how. No claims are made here that aren't backed
by math, citations, or explicit limitations.

Last updated: [auto-stamped]
Current methodology version: [auto-pulled from RAILWAY_GIT_COMMIT_SHA]
```

### 2. What this page is

One paragraph. Plain English.

> Every prediction on flashcardplanet.com/calls is locked at creation, resolved automatically against market data, and aggregated into a public Brier score. This page documents the system in enough detail that a competent reader can independently verify our calibration. If anything below is unclear, we'd consider that a documentation bug.

### 3. The four parts of a Flashcard Planet prediction

A prediction has four locked components:

1. **Target** — a specific card variant (e.g. "Charizard 1st Edition Base Set PSA 10")
2. **Threshold** — a specific price level + direction (e.g. "below $X" or "above $X" or "within band [low, high]")
3. **Resolution date** — exact UTC timestamp when the prediction resolves
4. **Stated probability** — our model's probability that the threshold condition will be met by the resolution date (0.0 to 1.0)

**Immutability:**
Once created, none of these four components can be modified. This is enforced at the database level via triggers — not policy, architecture. If we wanted to change a prediction after creation, we couldn't, even by mistake.

(Link to GitHub for the immutability trigger source code — optional, post-launch)

### 4. Driver attribution

For every signal we observe, we attempt to attribute the move to a primary driver. This creates a second dimension orthogonal to the signal tier (BREAKOUT/MOVE/WATCH/IDLE).

**Driver taxonomy:**

| Driver | Definition |
|---|---|
| `MACRO` | Overall market or set-level trend affecting the card |
| `META_SHIFT` | Competitive meta change (relevant primarily for play-driven TCGs) |
| `SUPPLY_SHOCK` | Reprint announcement, grading population update, sealed product release dilution |
| `EVENT_DRIVEN` | Influencer activity, content publication, tournament result within explicit event windows |
| `INFLUENCER_PROVENANCE` | Celebrity-owned card premium (e.g. Logan Paul "Break" pedigree) |
| `UNKNOWN` | Abnormal move detected, attribution unclear |

**Attribution method (v1):**
Rule-based engine. For each significant price move, check in order:
1. Is there a `market_event` within the move's time window touching this card? → `EVENT_DRIVEN` with confidence proportional to event recency
2. Is >60% of the card's set showing similar signal direction? → `MACRO`
3. Was a supply event recorded within ±14 days? → `SUPPLY_SHOCK`
4. None of the above → `UNKNOWN` with low confidence

Each attribution carries confidence (0.0-1.0). `UNKNOWN` is a valid output — we'd rather report honest uncertainty than fabricate a driver.

**Why this matters for predictions:**
Driver attribution makes the prediction reasoning transparent. A `BREAKOUT` tier card driven by `EVENT_DRIVEN` (e.g. a one-off YouTube video) should be expected to revert. A `BREAKOUT` driven by `SUPPLY_SHOCK` (e.g. confirmed reprint cancellation) is structural.

### 5. Brier score & calibration

**Brier score formula:**

For a single prediction with stated probability `p` and actual outcome `o ∈ {0, 1}`:
```
BS = (p - o)²
```

Across `N` resolved predictions:
```
Mean Brier = (1/N) × Σ (pᵢ - oᵢ)²
```

**Interpretation:**
- Perfect prediction (p=1.0, hits; or p=0.0, misses): BS = 0.0
- Coin flip (always predict 50%): BS = 0.25
- Worst case (p=1.0, misses; or p=0.0, hits): BS = 1.0

**Baseline:**
A model that always predicts 50% on every binary outcome achieves Mean Brier = 0.25. Any model claiming forecasting value must beat this baseline. Models with Mean Brier > 0.25 are worse than coin flips.

**Reference:** Brier, G. W. (1950). "Verification of Forecasts Expressed in Terms of Probability." *Monthly Weather Review*, 78(1), 1-3.

### 6. Reliability diagram

Brier score is a single number. The reliability diagram shows whether the model is calibrated *at all probability levels*, not just on average.

**Construction:**
1. Bin all resolved predictions by stated probability into deciles: `[0, 10%)`, `[10%, 20%)`, ..., `[90%, 100%]`
2. For each bin: compute mean stated probability, actual hit rate, and 95% Wilson confidence interval on hit rate
3. Plot (mean stated probability, actual hit rate) per bin
4. Overlay diagonal reference line `y = x`

**Interpretation:**
- Points on the diagonal = perfectly calibrated at that probability level
- Points above diagonal = under-confident (we said 60% but actually hit 75% of the time)
- Points below diagonal = over-confident (we said 80% but only hit 55% of the time)
- Wilson CI bars show statistical uncertainty per bin

**Wilson 95% CI formula:**
For `k` hits out of `n` trials at probability bin `p̂ = k/n`:
```
center = (p̂ + z²/2n) / (1 + z²/n)
margin = z × sqrt(p̂(1-p̂)/n + z²/4n²) / (1 + z²/n)
where z = 1.96 for 95% confidence
```

**Reference:** Wilson, E. B. (1927). "Probable inference, the law of succession, and statistical inference." *Journal of the American Statistical Association*, 22(158), 209-212.

### 7. Honest n discipline

Calibration is meaningless at small sample sizes. We display calibration plots from `n=1` onward but accompany them with explicit warnings:

- `n < 10` — "Pre-calibration. Treat all numbers as directional only."
- `10 ≤ n < 30` — "Below statistical significance threshold. Indicative but not conclusive."
- `30 ≤ n < 100` — "Above minimum threshold. Calibration is meaningful but noisy."
- `n ≥ 100` — Full confidence in calibration interpretation.

We never hide the calibration plot. We never wait until "calibration looks good" to publish. The honesty *is* the methodology.

### 8. Methodology version log

Every time we change driver attribution rules, fundamental signal computation, or scheduler logic, we increment methodology version. Each prediction carries the methodology version that generated it.

**Why this matters:**
A reader can verify "this prediction was made by methodology version v0.1-abc123, which used rule set X." Reproducibility is non-negotiable.

**Version log:**
| Version | Date | Changes |
|---|---|---|
| v0.1-{hash} | YYYY-MM-DD | Initial public launch |
| (future versions auto-appended) | | |

### 9. Known limitations

Stated openly. This section will grow over time.

**Current limitations:**

1. **Driver attribution is rule-based, not learned.** No ML model. Confidence numbers come from rule heuristics, not statistical estimation.

2. **Event registry is human-curated.** We maintain `market_events` table manually for high-impact events. Real-time event detection from social media, news, or content platforms is not yet implemented.

3. **Fundamental signal assumes event windows have known duration.** We use a default ±7d window around events. Cards with overlapping events from multiple sources may have noisy fundamental signals.

4. **Resolution scheduler runs every 4 hours.** A prediction resolving at 14:00 may show as resolved at 14:00, 18:00, 22:00, or later — never earlier. Maximum 4-hour delay.

5. **Single-source TCGs.** YGO uses CardMarket EUR data converted via fixed USD rate (`CARDMARKET_EUR_TO_USD`). Pokemon uses TCGPlayer market price. Cross-source reconciliation is a future improvement.

6. **No backtesting on historical Public Calls.** Calibration is forward-only from launch. We cannot retroactively claim historical accuracy.

7. **Sample size grows slowly.** We don't generate predictions on every card — only on cards where our model has confidence the prediction is meaningful. This means `n` grows at maybe 5-20 predictions per month, not hundreds. Calibration significance takes time.

### 10. Sources & references

**Statistical methods:**
- Brier, G. W. (1950). *Verification of Forecasts.*
- Wilson, E. B. (1927). *Probable Inference.*

**Calibration design inspiration:**
- Polymarket public reliability methodology
- Tetlock, P. E. (2005). *Expert Political Judgment* — long-horizon forecasting calibration

**Pokemon TCG market structure references:**
- TCGPlayer market data methodology (link to TCGPlayer's published methodology if available)
- CardMarket public price guide documentation
- (Future) Flashcard Planet event registry sources page

**Internal references:**
- Our prediction system spec: link to GitHub if open-sourced post-launch
- Our quality gates documentation: not public, internal only

---

## Implementation notes for Claude Code

**Tech:**
- Frontend route: `/methodology` (independent route, follows `PublicCallsLayout` pattern from `/calls`)
- Content: MDX or plain TSX with section components
- Math rendering: KaTeX (lightweight, no external deps if loaded from cdnjs)
- Tables: Plain HTML tables with Tailwind classes
- Code blocks: Plain `<pre><code>` with syntax highlighting via Prism if needed

**Styling:**
- Follow `frontend/docs/svg-conventions.md` typography (Space Mono for math/numbers, Syne for headings)
- Dark trading-desk aesthetic consistent with rest of platform
- Generous whitespace — this is meant to be read, not scanned
- Methodology version auto-pulled from `import.meta.env.VITE_GIT_COMMIT_SHA` (or equivalent build-time injection)

**Auto-updated fields:**
- "Last updated" timestamp: page generation time at build, OR live-fetched from `/api/v1/methodology/version`
- Current methodology version: same source as `predictions.methodology_version`

**Cross-linking:**
- Footer on every Flashcard Planet page links to `/methodology`
- `/calls` page links to `/methodology` prominently above the calls table
- Card detail pages with active predictions link to `/methodology` from the prediction widget

**SEO meta tags:**
```html
<title>Methodology — Flashcard Planet</title>
<meta name="description" content="How Flashcard Planet generates, locks, resolves, and grades its predictions. Brier scores, reliability diagrams, driver attribution.">
<meta property="og:title" content="Flashcard Planet Methodology">
<meta property="og:description" content="Public forecasts, publicly graded. The math behind our calibrated TCG predictions.">
```

---

## Open questions for Ivan

1. **Should this page be public from Day 1 (even before first calls)?** Default: yes, publish at Gate 6.

2. **Should we include sample predictions / worked examples?** My recommendation: include 1-2 anonymized examples in section 3 only after Gate 9 has fresh calls.

3. **GitHub link for source code?** If repo eventually goes public, linking to immutability trigger code adds massive credibility. Defer this decision — link is optional in v1.

4. **Chinese translation (闪卡星球 methodology)?** If your audience includes Chinese-language Pokemon collectors (likely), a `/methodology/zh` mirror is high-leverage. Defer to v2.

5. **Methodology page changelog visibility?** My recommendation: section 8 above expands with each version, showing diff summary.

---

## Done criteria (Gate 6)

- [ ] All 10 sections implemented per spec
- [ ] Math formulas render correctly via KaTeX
- [ ] All citations have working links (where possible)
- [ ] Ivan reads end-to-end twice, ≥24h apart, signs off
- [ ] Codex review clean
- [ ] No marketing copy
- [ ] No naked claims (every assertion has math/citation/explicit limitation)
- [ ] Mobile rendering tested (collectors browse on phones)
- [ ] Page accessible without authentication
