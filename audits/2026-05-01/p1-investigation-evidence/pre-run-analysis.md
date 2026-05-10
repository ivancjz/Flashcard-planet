# P1 Pre-Run Analysis
Captured: 2026-05-01 ~13:00 UTC (before next eBay run at ~15:43 UTC)

## What `match_status_counts: {}` means (code analysis)

`observation_match_status_counts` is populated inside `ingest_ebay_sold_cards`
(backend/app/ingestion/ebay_sold.py) in the per-listing for-loop. It only gets
populated when a listing is actually processed through the matching pipeline.

`match_status_counts: {}` + `api_calls_used > 0` means: the API was called successfully,
but every response had zero listings. The per-listing loop never executed.

## Call count analysis

For the 2026-04-30 15:42 run: `api_calls_used=201, assets_processed=100`
- 1 OAuth token call
- 100 × Finding API call = 100
- 100 × Browse API fallback call = 100 (Browse triggered when Finding returns None/empty)
Total = 201 ✓

`cards_failed=0` (error_message=None in DB): Browse API did NOT raise HTTP exceptions.
Browse API returned valid JSON with `{"itemSummaries": []}` for every asset.

## Hypothesis matrix (pre-run)

| Hypothesis | Pre-run verdict | Evidence |
|---|---|---|
| H1: eBay outage continues | **LIKELY** | Both Finding+Browse returned empty for ALL 100 assets. No HTTP errors. Pattern matches eBay outage behavior from Lesson 7. Last eBay data: April 27. |
| H2: Search query construction broken | **UNLIKELY** | git log shows no changes to `_build_search_query` or any ebay_sold.py matching logic since April 26. The last productive run (April 27, 47 records) used the same code. |
| H3: Match algorithm 0% hit rate | **RULED OUT** | `unmatched=0` AND `match_status_counts={}`. If listings were returned but rejected, we'd see `unmatched > 0`. Empty match_status_counts means NO listings were processed. |
| H4: eBay API schema changed | **UNLIKELY** | If Browse API changed field names, `_parse_browse_items` would return `[]` but only from a populated response. Browse API returning `{"itemSummaries": []}` is not a schema change. |
| H5: Auth/credential issue | **RULED OUT** | OAuth token request succeeded (api_calls_used includes 1 OAuth call, `cards_failed=0`). If OAuth failed, `ingest_ebay_sold_cards` returns early with 0 API calls. |
| H6: Rate limit/throttling | **UNLIKELY** | HTTP 429 would trigger the exception handler → `cards_failed > 0`. We see `cards_failed=0`. |

## Git log summary (last 14 days)

No changes to core eBay matching logic:
- `_fetch_finding_completed`, `_parse_browse_items`, `_build_search_query` unchanged
- `_is_single_card`, `_card_number_matches`, `preflight_observation` unchanged
- Only changes: wall-clock deadline (scheduler), loop index fix (assets_remaining)

Last code change that touched eBay query logic was before April 26.

## eBay data timeline

| Date | eBay runs | Records |
|------|-----------|---------|
| April 24 | ~3 | 125 |
| April 25 | 3 | 11 |
| April 26 | 8 | 8 |
| April 27 | 7 | **47** (last productive day) |
| April 28 | 8 | **0** (outage began) |
| April 29 | 6 | **0** |
| April 30 | 18 | **0** (mix of disabled/credentials/outage) |
| May 1 | 0 | **0** (no run yet — due ~15:43 UTC) |

## What the next run will tell us

SCENARIO A: `match_status_counts: {}` again
→ Confirms H1 (outage still ongoing as of 15:43 UTC)
→ No code fix needed
→ Recommend: monitor with alert when first non-empty run occurs

SCENARIO B: `match_status_counts` populated with `unmatched_*` keys
→ eBay API returning listings again; matching pipeline engaged
→ Compare records_written to pre-outage baseline (April 27: 47 records/run)
→ If records_written > 0: outage resolved, pipeline healthy
→ If records_written = 0 but match_status_counts populated: matching algorithm issue

SCENARIO C: `cards_failed > 0`
→ eBay returning HTTP errors (still partially broken)
→ Check if error is HTTP 429 (rate limit) or HTTP 500 (server error)
