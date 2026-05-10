# Signal System Audit — 2026-05-01

**Auditor:** Claude Code (claude-sonnet-4-6)  
**Codex reviewer:** Codex CLI (independent methodology review)  
**Codex outcome:** ACCEPT WITH CORRECTIONS  
**DB snapshot time:** 2026-05-01 ~12:03 UTC  

---

## Snapshot

- **Snapshot time:** 2026-05-01 12:03 UTC
- **Snapshot file:** `audits/2026-05-01/leaderboard-snapshot.json`
- **Method:** Direct production Railway PostgreSQL query via psycopg

**Top 10 cards by 24h delta (the actual leaderboard):**

| Card | Set | Label | Delta % | Confidence | Liquidity | eBay 24h | TCG $ | eBay $ |
|------|-----|-------|---------|------------|-----------|----------|-------|--------|
| Lickitung | Jungle | BREAKOUT | 282.5% | 83 | 98 | 0 | $2.18 | $1.66 |
| Kangaskhan ex | 151 | BREAKOUT | 140.5% | 83 | 98 | 0 | $7.19 | $8.50 |
| Snorlax | Crown Zenith | BREAKOUT | 118.5% | 86 | 95 | 0 | $2.01 | — |
| Dark Jolteon | Team Rocket | BREAKOUT | 114.7% | 86 | 95 | 0 | $13.59 | — |
| Marowak | Jungle | BREAKOUT | 94.9% | 83 | 98 | 0 | $2.69 | $9.99 |
| Mimikyu ex | Journey Together | MOVE | 80.4% | 86 | 95 | 0 | $1.93 | — |
| Parasect | Jungle | MOVE | 76.8% | 83 | 98 | 0 | $0.99 | $3.99 |
| Alakazam ex | 151 | BREAKOUT | 67.1% | 86 | 95 | 0 | $2.44 | — |
| Seaking | Jungle | MOVE | 66.0% | 83 | 98 | 0 | $1.61 | $11.00 |
| Rhydon | Jungle | MOVE | 64.1% | 83 | 98 | 0 | $1.92 | $4.99 |

**Anchor cards for deep-dive:** Lickitung (Jungle), Kangaskhan ex (151), Stoutland (White Flare)

---

## Verdict Summary

| Layer | Check | Status | Key Evidence |
|-------|-------|--------|--------------|
| 0.1 | eBay ingest running | **FAIL** | 0 eBay rows since 2026-04-27; 14 runs with empty API responses |
| 0.1b | eBay rows written daily | **FAIL** | No rows 2026-04-28 through 2026-05-01 |
| 0.2 | TCG ingest health | **WEAK PASS** | 94,296 bulk + 15,598 scheduled in 24h; coverage not per-card verified |
| 0.3 | Anchor card source coverage | **FAIL** | Lickitung: last eBay 2026-04-27; Snorlax/Dark Jolteon: never |
| 1.1 | Delta math reproduces displayed % | **PARTIAL PASS** | Arithmetic verified for 3 anchor cards; production row selection not fully traced |
| 1.2 | eBay data in current window | **FAIL** | 100% of current-window rows are pokemon_tcg_api; eBay excluded by 4-day gap |
| 1.3 | BREAKOUT label: no eBay volume gate | **FAIL (product req gap)** | 152/152 BREAKOUT, 330/330 MOVE have 0 eBay 24h rows |
| 1.4 | INSUFFICIENT_DATA accuracy | **WEAK PASS** | 2,356 bulk-floor + 37 no-data; downgrade semantics not per-card verified |
| 2.1 | Sort logic | **DESIGN CONCERN** | Naked price_delta_pct DESC; no confidence weighting |
| 2.2 | "0 sales" field semantics | **FAIL** | Field = eBay rows in 24h; signal uses TCG-based confidence |
| 2.3 | 24h % source attribution | **FAIL** | No source tag on price_delta_pct in API response |
| 2.4 | "24h change" label accuracy | **DESIGN CONCERN** | UI says "24h Change" but baseline is 7+ days old |
| 3.1 | Domain knowledge check | **MIXED** | High-value cards correctly IDLE; bulk cards dominate leaderboard top |
| 3.2 | High-liquidity sanity | **WEAK/ANECDOTAL** | Charizard/Mewtwo correctly IDLE; 5-card sample too small |

---

## Confirmed Bugs (with evidence)

### Bug 1 (HIGH): Liquidity Score Inflated by TCG API Polling

**Root cause:** `liquidity_service.py:265-278` counts ALL non-sample `price_history` rows as "sales," including pokemon_tcg_api hourly bulk-refresh updates (~180 rows/card/7d for bulk-refreshed cards). This is not sales activity — it is scheduled API polling.

**Evidence:**

Top 10 BREAKOUT cards liquidity breakdown:
```
name           | set          | liquidity | confidence | ebay_7d | tcg_7d
Lickitung      | Jungle       | 98        | 83         | 2       | 181
Kangaskhan ex  | 151          | 98        | 83         | 2       | 158
Snorlax        | Crown Zenith | 95        | 86         | 0       | 177
Dark Jolteon   | Team Rocket  | 95        | 86         | 0       | 180
Marowak        | Jungle       | 98        | 83         | 1       | 181
```

Formula verification:
- `score_sales_count_7d(180)` = 100 (bulk-refresh rows treated as sales)
- `score_days_since_last_sale(0)` = 100 (last TCG update was <1h ago)
- Computed liquidity = 0.30×100 + 0.25×100 + 0.20×100 + 0.15×100 + 0.10×(50 or 80) = **95 or 98** ✓

**Impact:** Every card in the bulk-refresh pool achieves liquidity_score=95-98. Combined with any TCGPlayer price change ≥10%, the `alert_confidence` formula produces 83-86, clearing the BREAKOUT threshold (≥70). Cards can achieve BREAKOUT labels with **zero eBay sales evidence**.

**Files:** `backend/app/services/liquidity_service.py:265-278` (query), `:148-155` (score formula)

---

### Bug 2 (HIGH): eBay Ingest Dark Since 2026-04-27 — Cause Unresolved

**Root cause:** Unknown. eBay ingest ran 20+ times from 2026-04-28 to 2026-04-30 but wrote 0 records. All runs returned `matched: 0, unmatched: 0, match_status_counts: {}` despite 201-501 API calls. This means the eBay API was called but produced no parseable listings in any query. Consistent with the documented eBay outage (Lesson 7) but a code-level cause cannot be ruled out from this evidence alone.

**Evidence:**
```
price_history eBay rows by day:
  2026-04-27: 174 rows (last productive day)
  2026-04-28: 0 rows (8 runs, all empty)
  2026-04-29: 0 rows (6 runs, all empty)
  2026-04-30: 0 rows (18 runs: mix of disabled/credentials/empty API)
  2026-05-01: 0 rows (no run yet — next scheduled ~15:43 UTC)

Sample run meta (2026-04-30 15:42, 77s, 100 assets, 201 calls):
  {'matched': 0, 'unmatched': 0, 'api_calls_used': 201,
   'assets_processed': 100, 'assets_remaining': 0,
   'match_status_counts': {}}
```

**Additional context:** Total eBay data ever written = 1,380 rows vs 1,258,390 TCG rows. Even when healthy, eBay provides <0.1% of price data. The signal system is structurally TCG-API-dominant.

**Recommended diagnostic:** Monitor the next scheduled eBay run (~15:43 UTC today). If it still produces `match_status_counts: {}`, the cause is NOT the outage — investigate the eBay search query construction and response parsing.

**Files:** `backend/app/backstage/scheduler.py` (eBay job), eBay ingest pipeline

---

### Bug 3 (MEDIUM): Signal Delta Measures TCGPlayer Listed Prices, Not Sold Prices

**Root cause:** The delta algorithm (`signal_service.py:320-454`) takes the weighted median of ALL price_history rows in each window. With eBay dark for 4+ days, ALL current-window rows are `pokemon_tcg_api`. The baseline also predominantly contains `pokemon_tcg_api` rows (392 baseline rows for Lickitung vs 0 eBay baseline rows). The delta measures TCGPlayer market price change, not eBay sold price change.

**Evidence:**

Cross-source breakdown for top 5 BREAKOUT cards:
```
card         | win      | source          | rows
Lickitung    | current  | pokemon_tcg_api | 24  (all current rows are TCG)
Lickitung    | current  | ebay_sold       | 0
Dark Jolteon | current  | pokemon_tcg_api | 24
Dark Jolteon | current  | ebay_sold       | 0  (no eBay data ever)
...
```

**Delta reproduction for Lickitung Jungle:**
- Baseline (5 most recent rows before 2026-04-24): all `pokemon_tcg_api`, $0.57
- Current (10 most recent rows in 24h): all `pokemon_tcg_api`, $1.97-$2.18
- Delta = (2.18 - 0.57) / 0.57 × 100 = **282.46%** — correct arithmetic, but measuring a TCGPlayer listing price change

**Impact:** TCGPlayer "market price" is a listing-weighted average. A card's TCGPlayer price can change 200%+ without a single eBay sold listing. The system is currently measuring TCGPlayer price arbitrage opportunities, which may not correlate with actual investment signal activity.

**Note:** Whether this is acceptable depends on product intent. If the intent is "eBay market signal," this is a design bug. If the intent is "multi-source price change signal," the eBay weight (2.0 vs TCG 1.0) was designed to preference eBay data when available — but with eBay dark, this preference has no effect.

**Files:** `backend/app/services/signal_service.py:319-454`, `backend/app/core/config.py:110` (`signal_delta_source_weights`)

---

### Bug 4 (LOW): Duplicate Asset Rows

**Evidence:** Query 0.3 found two `assets` rows for "Kangaskhan ex" in set "151" — one with 5 eBay history rows and one with 0. Both have identical `tcg_total=330`.

**Impact:** On the leaderboard, one Kangaskhan ex appears at position #2 (delta=140.5%). It's unclear which asset row backs the displayed signal. The duplicate creates data quality noise. The non-dominant duplicate row exists silently with no signal coverage.

**Files:** `assets` table (data quality), `backend/app/ingestion/` (ingest dedup logic)

---

## Design Concerns (Require Ivan's Decision)

### DC-1: No eBay Volume Gate for BREAKOUT

**Current behavior:** BREAKOUT is assigned when `confidence ≥ 70 AND delta ≥ 10% AND liquidity ≥ 60`. No eBay activity requirement.

**Question:** Should BREAKOUT require `ebay_sales_7d > 0` or similar? If yes, none of the 152 current BREAKOUT cards would qualify (all have 0 eBay 24h rows, most have 0 eBay 7d rows). This would effectively disable BREAKOUT until eBay ingest is healthy AND liquidity scoring is fixed.

**Implication:** Fix Bug 1 (liquidity scoring) and Bug 2 (eBay ingest) first, then decide whether to add the gate.

### DC-2: "24h Change" UI Label Mislabels the Baseline Window

**Current behavior:** The UI shows "24h Change %" but the delta algorithm compares the current 24h window against a baseline from 7+ days ago. The column name implies a 24-hour period-over-period comparison but delivers a 7-day lookback change.

**Codex raised this; I agree.** The label is misleading. Consider "7d Change %" or "7-Day Price Change" as a more accurate label.

### DC-3: Sort by Naked % Change

**Current behavior:** Default "Change" sort = `price_delta_pct DESC NULLS LAST`. No confidence, price floor, or volume weighting.

**Effect:** Lickitung at $2.18 (+282%) ranks above Stoutland (White Flare) at $44.67 (+42%). Low-priced bulk cards with large % moves from small absolute changes dominate the top of the leaderboard.

**Design choice needed:** Sort by confidence-weighted delta? Minimum price threshold? Current behavior may be intentional for "pure % change" view.

### DC-4: Signal Source Opacity

**Current behavior:** `price_delta_pct` in the API response has no source tag. Consumer cannot distinguish "TCGPlayer rose 282%" from "eBay sold price rose 282%."

**Recommendation:** Add `delta_source_dominant` field (e.g., "tcg_api" or "ebay") to the leaderboard API response. Low-cost addition that gives users critical context.

---

## Codex Review Summary

**Outcome: ACCEPT WITH CORRECTIONS** (29,641 tokens)

**Corrections applied in this report:**
- Bug 2 root cause downgraded from "confirmed eBay outage" to "cause unresolved"
- Check 1.2 renamed from "cross-source contamination" to "eBay-absent current window"
- Check 1.3 recategorized from pure FAIL to "FAIL if product requires eBay-backed signals"
- Check 2.1 recategorized from FAIL to design concern
- Added DC-2 "24h change label mislabeling" per Codex's D6 coverage gap finding

**Disagreements remaining for Ivan:**
- None — all Codex corrections were accepted or incorporated. One clarification added: Codex questioned whether "24h Change" label is a bug or design choice. My position: it's a design concern (misleading label), not a code bug, which matches how I've categorized it in DC-2.

**Codex's additional coverage gaps (not addressed in this audit):**
- Frontend field mapping bugs (API returns correct value but frontend may display wrong field)
- API/UI caching staleness
- Timezone/window boundary edge cases in the delta algorithm
- Duplicate asset join nondeterminism (which row wins when two assets share a name?)

These gaps exist and would require frontend access to verify. Not addressed in this audit.

---

## Recommended Fix Order

Ranked by: severity × actionability. One PR per bug.

### Priority 1 — Fix Liquidity Scoring (Bug 1)
**Effort:** Low (filter one query in liquidity_service.py)  
**Impact:** HIGH — eliminates the root cause of inflated confidence scores  
**Fix:** In `liquidity_service.py:265-278`, add `PriceHistory.source == 'ebay_sold'` filter to the liquidity query so `sales_count_7d/30d` only counts actual eBay rows, not TCG API polling events.  
**Risk:** This will cause most BREAKOUT/MOVE signals to drop to WATCH/IDLE until eBay data recovers. This is the correct behavior but will make the leaderboard look emptier.  
**Prerequisite:** Bug 2 (eBay ingest) should also be investigated so that when liquidity scoring is fixed, eBay data is flowing again.

### Priority 2 — Diagnose and Fix eBay Ingest (Bug 2)
**Effort:** Unknown (root cause unresolved)  
**Impact:** HIGH — without eBay data, the signal system has no real market activity evidence  
**Action:** Monitor the next eBay run (~15:43 UTC today). If it returns `match_status_counts: {}` again, investigate the eBay search query construction (`backend/app/ingestion/ebay/`) and what eBay is actually returning. Add logging of raw eBay API response body for a single query before any parsing.  
**Pre-check (Lesson 7 gating):** Before diagnosing, confirm eBay Down Detector is operational and last cycle duration was <15 min.

### Priority 3 — Fix "24h Change" Label (DC-2)
**Effort:** Very Low (UI label change)  
**Impact:** MEDIUM — eliminates user confusion about what the percentage represents  
**Fix:** Rename "24h Change" column in the frontend to "7d Change" or "Price Change (7d)" to accurately describe the baseline window.

### Priority 4 — Add Source Attribution to API (DC-4)
**Effort:** Low (add field to leaderboard SQL query)  
**Impact:** MEDIUM — gives users and monitoring tools ability to distinguish TCG vs eBay signals  
**Fix:** Add `signal_context->>'baseline_window_days'` or a derived `delta_source` field to the `/api/v1/web/cards` response.

### Priority 5 — Investigate Duplicate Asset Rows (Bug 4)
**Effort:** Low (audit + dedup)  
**Impact:** LOW (one known duplicate)  
**Action:** Query `SELECT name, set_name, COUNT(*) FROM assets GROUP BY 1,2 HAVING COUNT(*) > 1` to enumerate all duplicates. Then investigate the ingest dedup logic.

---

## Audit Files

```
audits/2026-05-01/
├── leaderboard-snapshot.json   — Top 15 cards at audit time
├── findings-raw.md             — Pre-Codex evidence collection
├── codex-prompt.md             — Codex review instructions
├── codex-review.md             — Full Codex review output
├── REPORT.md                   — This file (final)
├── db_query.py                 — Step 0 snapshot query
├── db_query2.py                — Layer 0-1.1 queries
├── db_query3.py                — Layer 1.2-3.2 queries
└── db_query4.py                — eBay ingest deep-dive queries
```
