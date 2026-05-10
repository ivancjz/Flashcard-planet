# Signal System Audit — Raw Findings
**Audit date:** 2026-05-01  
**Snapshot timestamp:** 2026-05-01 ~12:03 UTC  
**Auditor:** Claude Code (claude-sonnet-4-6)

---

## Evidence Collected

All queries ran against production Railway PostgreSQL via direct psycopg connection.

---

## Layer 0: Data Freshness

### 0.1 eBay Ingest Running?

**STATUS: FAIL — eBay has written 0 price_history rows since 2026-04-27**

SQL evidence (`scheduler_run_log` + `price_history`):

```
ebay price_history by day (last 7d):
  day         | rows_written | unique_cards
  2026-04-27  |     174      |     132
  2026-04-26  |     284      |     190
  2026-04-25  |     209      |     134
  2026-04-24  |     125      |     107
  (NO rows for 2026-04-28, 2026-04-29, 2026-04-30, 2026-05-01)
```

eBay ingest runs 2026-04-28 through 2026-04-29 — ALL wrote 0 records:
```
  meta_json pattern (14 consecutive runs):
  {'matched': 0, 'unmatched': 0, 'api_calls_used': 501, 
   'assets_processed': 250, 'match_status_counts': {}}
```

Root cause: eBay outage (Lesson 7) — API returning empty result sets. `match_status_counts: {}` means eBay returned no listings at all for any search query. NOT a code bug — upstream API failure.

Most recent eBay run (2026-04-30 15:42, 77 sec, 100 assets, 201 calls): same empty-result pattern. Run after that: `job_blocked_reason: disabled` and `job_blocked_reason: missing_credentials` (deploy cycling env vars).

**Next scheduled eBay run:** ~2026-05-01 15:43 UTC (24h after last run). Not yet executed at audit time.

Production `price_history` source summary:
```
source            | total_rows | latest                | last_24h | last_7d
pokemon_tcg_api   | 1,258,390  | 2026-05-01 11:46:26  | 111,382  | 788,384
ygoprodeck_api    | 4,824      | 2026-05-01 09:44:26  | 268      | 3,819
ebay_sold         | 1,380      | 2026-04-27 13:33:14  | 0        | 790
```

Only 1,380 total eBay rows ever. The entire eBay dataset is tiny relative to TCG API.

### 0.2 Pokemon TCG Ingest Health

**STATUS: PASS**

```
bulk-set-price-refresh: 24 runs in 24h, 94,296 records written
ingestion: 22 success + 2 error, 15,598 records written (errors = partial card failures, non-critical)
TCG freshness: 27,826 rows in 0-6h, 83,556 rows in 6-24h
```

The 2 ingestion error runs had error_message: "Pokemon TCG API/High-Activity v2: N card(s) failed" — these are per-card failures in otherwise-successful ingest runs. Status=error is logged but 700+ records still written per run.

### 0.3 Anchor Card Source Coverage

**STATUS: FAIL — eBay data stale/absent for all anchor cards**

```
name           | set          | ebay_total | ebay_7d | last_ebay            | tcg_24h
Lickitung      | Jungle       | 2          | 2       | 2026-04-27 01:02:01  | 24
Kangaskhan ex  | 151          | 5 (one asset) | 2    | 2026-04-27 06:02:39  | 24
Snorlax        | Crown Zenith | 0          | 0       | NULL                 | 24
Dark Jolteon   | Team Rocket  | 0          | 0       | NULL                 | 24
```

Note: Kangaskhan ex (151) has TWO separate asset rows — one with 5 eBay rows and one with 0. Potential duplicate asset issue.

For Lickitung: last_ebay = 2026-04-27. eBay rows ARE in the 7d window but NOT in the 24h current window (eBay has been dark since 2026-04-27 13:33 UTC).

**"—" on eBay column in UI**: For cards like Snorlax, Dark Jolteon — these have never had eBay data. The "—" is correct but the root cause is "eBay ingest never matched these cards," not "eBay ingest hasn't run."

---

## Layer 1: Signal Calculation Logic

### 1.1 Reproduce Displayed % Change for Anchor Cards

**STATUS: PASS (calculation is accurate; but it measures the wrong thing)**

**Lickitung (Jungle) — displayed +282.46%:**

Baseline rows (before 2026-04-24 cutoff, top 5 by recency):
```
source          | price | captured_at
pokemon_tcg_api | 0.57  | 2026-04-24 11:19:16
pokemon_tcg_api | 0.57  | 2026-04-24 10:48:49
pokemon_tcg_api | 0.57  | 2026-04-24 09:45:55
pokemon_tcg_api | 0.57  | 2026-04-24 09:02:24
pokemon_tcg_api | 0.57  | 2026-04-24 08:21:36
```
Weighted median baseline = $0.57 (all identical weights, all $0.57)

Current rows (last 24h, top 10):
```
source          | price | captured_at
pokemon_tcg_api | 2.18  | 2026-05-01 11:46:26
pokemon_tcg_api | 2.18  | 2026-05-01 10:46:26
... (6 × $2.18, then 4 × $1.97)
```
Weighted median current = $2.18

Manual computation: (2.18 - 0.57) / 0.57 × 100 = 282.46% ✓ **MATCHES displayed value**

**Kangaskhan ex (151) — displayed +140.47%:**
- signal_context confirms: baseline_price=2.99, current_price=7.19
- (7.19 - 2.99) / 2.99 × 100 = 140.47% ✓

**Stoutland (White Flare) — displayed +42.31%:**
- signal_context: baseline_price=31.39, current_price=44.67
- (44.67 - 31.39) / 31.39 × 100 = 42.31% ✓

**All three delta computations are arithmetically correct.** The issue is not the math — it's what the math is measuring (see Bug 1 and Bug 3 below).

### 1.2 Cross-Source Contamination

**STATUS: FAIL — signals are purely TCG-API-based, no eBay in current window**

Source breakdown for top 5 BREAKOUT cards:
```
name            | source          | win      | row_count
Dark Jolteon    | pokemon_tcg_api | baseline | 219
Dark Jolteon    | pokemon_tcg_api | current  | 24
Kangaskhan ex   | ebay_sold       | baseline | 3
Kangaskhan ex   | pokemon_tcg_api | baseline | 172
Kangaskhan ex   | pokemon_tcg_api | current  | 24
Lickitung       | pokemon_tcg_api | baseline | 392
Lickitung       | pokemon_tcg_api | current  | 24
Lickitung       | ebay_sold       | middle   | 2
Marowak         | pokemon_tcg_api | baseline | 392
Marowak         | pokemon_tcg_api | current  | 24
Snorlax         | pokemon_tcg_api | baseline | 94
Snorlax         | pokemon_tcg_api | current  | 24
```

**Finding:** The `current` window (last 24h) contains ONLY `pokemon_tcg_api` rows for ALL 5 top BREAKOUT cards. eBay data (where it exists) falls entirely outside the current window because eBay has been dark since 2026-04-27 (4+ days ago).

**The delta for ALL top BREAKOUT cards is comparing:**
- TCGPlayer market price from 7+ days ago (baseline) 
- vs TCGPlayer market price from today (current)

This is a TCGPlayer-to-TCGPlayer price delta. There is no eBay data in the calculation. TCGPlayer "market price" is a listing-weighted average, not actual sold prices.

### 1.3 BREAKOUT Label Gating — No Volume Gate

**STATUS: FAIL — 100% of BREAKOUT/MOVE cards have 0 eBay 24h sales**

```
label    | ebay_24h_sales | card_count
BREAKOUT | 0              | 152
MOVE     | 0              | 330
```

This is not a coincidence — it is structural. There are zero eBay rows in price_history for the last 24h period. Since `volume_24h` is computed as COUNT(ebay_sold rows in last 24h), every card shows "0 sales."

Code confirms: there is NO `ebay_volume > 0` gate before assigning BREAKOUT/MOVE labels. The `classify_signal()` function at `backend/app/services/signal_service.py:129` only checks:
- `alert_confidence >= 70`
- `price_delta_pct >= 10.0`  
- `liquidity_score >= 60`

None of these require actual eBay sales.

### 1.4 INSUFFICIENT_DATA Classification

**STATUS: PASS (for INSUFFICIENT_DATA accuracy)**

```
reason                | downgrade_reason   | count
NULL                  | bulk_baseline_price| 2,356
no_current_data       | NULL               | 30
no_baseline_data      | NULL               | 7
```

INSUFFICIENT_DATA cards with BREAKOUT/MOVE label: zero (confirmed — no such rows exist; the downgrade logic applies bulk_baseline_price → INSUFFICIENT_DATA correctly).

However, note: `average confidence = 79` for INSUFFICIENT_DATA rows — these cards have a computed confidence stored even though they're labeled INSUFFICIENT_DATA. This is because the signal_context stores the computed delta.

---

## Layer 2: Sort and Display Layer

### 2.1 Sort Logic

**STATUS: FAIL by design — naked percentage sort, no volume/confidence weighting**

Code at `backend/app/api/routes/web.py:239`:
```sql
ORDER BY s.price_delta_pct DESC NULLS LAST
```

No confidence, volume, or price-floor weighting in the sort. The sort is a pure descending percentage sort.

Effect: Low-priced cards with large % changes dominate. Lickitung at $2.18 (+282%) ranks above Stoutland (White Flare) at $44.67 (+42%). The system's most prominent signal is a $0.57→$2.18 TCGPlayer price movement on a common Jungle card.

The code comment notes `_PRO_ONLY_SORTS` is defined but currently unused (TEMP flag). The sort behavior was explicitly chosen, but no documentation of the design decision exists.

### 2.2 "0 sales" Field Semantics

**STATUS: FAIL — field semantics don't match user expectation**

The `volume_24h` field in the API (and displayed as "sales" in UI) is:
```sql
SELECT COUNT(*) AS cnt FROM price_history
WHERE asset_id = sub.asset_id AND source = 'ebay_sold'
  AND captured_at >= NOW() - INTERVAL '24 hours'
```

This counts `price_history` rows written by the eBay ingest job in the last 24h. It is NOT a count of distinct eBay transactions — one eBay ingest run can write multiple rows per card if the same listing appears in multiple lookback windows.

With eBay dark since 2026-04-27, this count is always 0 for every card.

### 2.3 24h % Column Source Attribution

**STATUS: FAIL — no source tag on delta**

`price_delta_pct` in `asset_signals` has no source attribution. The API response includes the number but not which source(s) produced it.

A consumer cannot distinguish "TCGPlayer rose 282%" from "eBay sold price rose 282%" from the API response alone. The `signal_context` JSONB field has `baseline_price` and `current_price` but is not exposed in the leaderboard API response.

---

## Layer 3: Sanity Cross-validation

### 3.1 Domain Knowledge Check (High-value base set)

**STATUS: MIXED — high-value cards are correctly IDLE, but the system is not showing meaningful activity signals**

```
name       | set      | label   | delta_pct | confidence | ebay_7d | tcg_price
Charizard  | Base     | IDLE    | 0.0       | 61         | 20      | 555.88
Mewtwo     | Base     | IDLE    | 1.5       | 61         | 9       | 77.79
Blastoise  | Base     | IDLE    | -3.5      | 66         | 9       | 206.42
Venusaur   | Base     | IDLE    | 1.6       | 61         | 6       | 151.01
Pikachu    | Base     | BREAKOUT| 19.7      | 80         | 6       | 6.56
```

Popular base set cards show IDLE (stable TCGPlayer prices, which is correct). Pikachu shows BREAKOUT with 6 eBay sales in 7 days and a 19.7% TCG price change — this signal has the most eBay backing of any BREAKOUT card and is the most credible of the bunch.

Charizard has 20 eBay sales in 7 days but shows IDLE — because its TCGPlayer price didn't change. This is correct behavior: the signal system is price-movement-based, not volume-based.

**Implication**: The system is correctly identifying TCGPlayer price changes. The problem is that TCGPlayer price changes for bulk/uncommon cards are NOT investment signals — they're listing artifacts.

### 3.2 High-Liquidity Sanity

**STATUS: PASS (popular cards work correctly, but expose the design flaw)**

Cards with genuine eBay activity (Charmander: 11 eBay 7d, Squirtle: 6, Pikachu: 6) DO have BREAKOUT labels. But their signals are driven by TCG price change, not eBay volume — Charizard with 20 eBay 7d sales shows IDLE because its TCGPlayer price is flat.

---

## Additional Findings

### AF-1: eBay Ingest Matching Failure (Not Just Outage)

All 14 runs on 2026-04-28/29 returned `match_status_counts: {}` — the eBay API was returning responses (201/501 calls completed) but zero listing results. This is consistent with eBay outage behavior (Lesson 7: "eBay returned empty results").

However, even when eBay was working (2026-04-27), the maximum records written per day was 174, producing 1,380 total rows across all time. With 1,258,390 TCG rows, eBay provides <0.1% of price data. The signal system is structurally TCG-API-dominant regardless of outage.

### AF-2: Duplicate Kangaskhan ex Asset

Query 0.3 found TWO asset rows for "Kangaskhan ex" in set "151":
- Asset A: ebay_total=5, last_ebay=2026-04-27, tcg_total=330
- Asset B: ebay_total=0, tcg_total=330

Both have identical tcg_total, suggesting they may be duplicate records from two separate ingest runs. The leaderboard shows one Kangaskhan ex (delta=140.47%, confidence=83) — this must be Asset A (has eBay data). Asset B exists silently.

### AF-3: Orphaned 'running' Scheduler Row

```
job_name  | started_at              | hours_ago
ingestion | 2026-04-30 15:29:50+00  | 20.7
```

The ingestion job has a row stuck at `status='running'` for 20+ hours. This was likely from a deploy that interrupted the job (error_message in another row confirms: "Orphaned: container restart — finish_run never called"). The `cleanup_stale_runs` function should have caught this at startup. Not causing active issues (24 successful ingestion runs in 24h), but it's a data quality concern in the run log.

### AF-4: INSUFFICIENT_DATA Cards Have Stored Confidence Values

2,393 INSUFFICIENT_DATA cards have `avg_confidence = 79` and `avg_liquidity_score = 95`. The confidence is computed but the label is INSUFFICIENT_DATA because the delta was NULL (no baseline or current data) OR because of bulk_baseline_price downgrade. The confidence values for bulk-downgraded cards are stored in asset_signals even though the card is suppressed — this is correct behavior (the confidence reflects the computation at the time, before downgrade).

---

## Verdict Summary

| Layer | Check | Status | Evidence |
|-------|-------|--------|----------|
| 0.1 | eBay ingest running | **FAIL** | 0 eBay rows since 2026-04-27; 14 runs with empty eBay API responses |
| 0.1b | eBay rows written daily | **FAIL** | No rows on 2026-04-28 to 2026-05-01 |
| 0.2 | TCG ingest health | **PASS** | 94,296 bulk rows + 15,598 ingest rows in 24h |
| 0.3 | Anchor card source coverage | **FAIL** | Lickitung: last eBay 2026-04-27; Snorlax/Dark Jolteon: no eBay ever |
| 1.1 | Delta math reproduces displayed % | **PASS** | Manual arithmetic matches ±0.01% for all 3 anchor cards |
| 1.2 | Cross-source contamination | **FAIL** | 100% of current-window rows are pokemon_tcg_api; eBay excluded by 4-day gap |
| 1.3 | BREAKOUT gating: no sales_count gate | **FAIL** | 152/152 BREAKOUT and 330/330 MOVE have 0 eBay 24h sales |
| 1.4 | INSUFFICIENT_DATA accuracy | **PASS** | 2,356 bulk-floor + 37 no-data correctly labeled |
| 2.1 | Sort logic | **DESIGN CONCERN** | Naked price_delta_pct DESC; no confidence/volume weighting |
| 2.2 | "0 sales" field semantics | **FAIL** | Field = eBay rows in 24h; signal uses TCG-based confidence |
| 2.3 | 24h % source attribution | **FAIL** | No source tag on price_delta_pct in API response |
| 3.1 | Domain knowledge reverse check | **MIXED** | High-value cards correctly IDLE; bulk cards dominate top |
| 3.2 | High-liquidity sanity | **PASS** | Charizard/Mewtwo/Blastoise correctly IDLE; Pikachu BREAKOUT with 6 eBay 7d |

---

## Confirmed Bugs

### Bug 1 (HIGH): Liquidity Score Counts TCG API Polling as "Sales"

**File:** `backend/app/services/liquidity_service.py:265-278`  
**Mechanism:** `sales_count_7d` = ALL non-sample `price_history` rows in 7d, including `pokemon_tcg_api` hourly updates (~180 rows/card/7d for bulk-refreshed cards). This makes `liquidity_score = 95-98` for every card in the bulk-refresh pool regardless of actual eBay activity.

Evidence:
- Top 10 BREAKOUT cards: ebay_7d = 0-2, tcg_7d = 158-181, liquidity_score = 95-98
- Formula verification: 0.30×100 + 0.25×100 + 0.20×100 + 0.15×100 + 0.10×(50 or 80) = 95 or 98 ✓

**Impact:** `alert_confidence` formula (25% price_magnitude + 35% liquidity + 20% source_agreement + 20% outlier_handling) produces confidence=83-86 for any card with a large TCG price change. This passes the BREAKOUT threshold (≥70) without any eBay sales evidence.

### Bug 2 (HIGH): eBay Ingest Dark Since 2026-04-27 (Upstream Outage Residual)

**Root cause:** eBay outage (Lesson 7) made API return empty result sets. The last substantive run (2026-04-30 15:42) also returned `matched=0, unmatched=0, match_status_counts={}`. 

**Status at audit time:** Unknown if resolved — next eBay run scheduled ~2026-05-01 15:43 UTC, has not executed yet.

**Impact:** `volume_24h = 0` for every card on leaderboard. eBay price data is 4+ days stale. All "0 sales" on the leaderboard is a direct consequence.

**Note:** Even when eBay is healthy, total eBay data is 1,380 rows (vs 1,258,390 TCG rows). eBay is structurally a very sparse data source.

### Bug 3 (MEDIUM): Signal Delta Uses TCGPlayer Listed Prices, Not Actual Sold Prices

**Mechanism:** The delta algorithm compares `pokemon_tcg_api` price from 7+ days ago vs today. TCGPlayer "market price" is a listing-weighted average (not sold prices). A card's TCGPlayer price can change 200%+ without a single eBay sale occurring.

**Evidence:** Lickitung (Jungle): $0.57 → $2.18 TCGPlayer price change is real. But with 0 eBay sales in 7 days, there is no sold-price evidence for this "BREAKOUT" signal.

**Impact:** The system currently measures TCGPlayer price arbitrage, not real eBay market activity. Whether this is acceptable depends on product intent.

### Bug 4 (LOW): Duplicate Asset Rows

Kangaskhan ex (151) has two asset rows in production. One has eBay data coverage, one doesn't. The signal for the card shown on the leaderboard comes from whichever asset row the join resolves. This is a data quality issue.

---

## Design Concerns (Not Bugs — Require Ivan's Decision)

### DC-1: No eBay Volume Gate for BREAKOUT
Currently a card can be BREAKOUT with 0 eBay sales ever. Should BREAKOUT require `ebay_sales_7d > 0` or similar?

### DC-2: Sort by Naked % Change
The default "Change" sort surfaces low-priced bulk cards with large % moves. Consider confidence-weighted sort or minimum absolute price floor for the default view.

### DC-3: "Sales" vs "Listing Observations" Labeling
`volume_24h` counts price_history rows written by eBay ingest. This is at best "listings observed" not "sales." The UI label "sales" is technically inaccurate.

### DC-4: Signal Source Opacity
The leaderboard API returns `price_delta_pct` with no indication of whether it was driven by TCG, eBay, or a mix. Consider adding a `price_source` or `delta_sources` field.
