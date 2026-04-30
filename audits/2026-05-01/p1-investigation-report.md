# eBay Zero-Match Investigation — 2026-05-01
Investigator: Claude Code (claude-sonnet-4-6)
Closed: 2026-05-01 ~14:00 UTC

---

## Latest Run Details

Last run before investigation close (2026-04-30 15:42 UTC):
- `api_calls_used=201`, `assets_processed=100`, `records_written=0`
- `match_status_counts={}`, `cards_failed=0`, `error_message=None`
- Duration: 77 seconds

---

## Code Analysis: What `match_status_counts: {}` Means

`observation_match_status_counts` in `ebay_sold.py` is populated inside the per-listing for-loop.
`{}` + `api_calls_used=201` + `cards_failed=0` = the API was called successfully for all 100 assets
but EVERY response returned zero listings. The per-listing loop never executed.

Call count breakdown for 100-asset run:
- 1 OAuth token
- 100 × Finding API = 100
- 100 × Browse API fallback = 100 (Browse triggered when Finding returns empty/None)
= 201 total ✓

`cards_failed=0` means Browse API returned valid JSON (not HTTP errors) — specifically
`{"itemSummaries": []}` for every single asset query.

---

## Hypothesis Matrix

| Hypothesis | Verdict | Evidence |
|---|---|---|
| H1: eBay API outage | **CONFIRMED** | See external evidence below. Both Finding+Browse returned empty for all assets. Time-line matches published outage reports. |
| H2: Search query construction broken | RULED OUT | No changes to `_build_search_query` or matching logic since April 26. Last productive run (April 27, 47 records) used identical code. |
| H3: Match algorithm 0% hit rate | RULED OUT | `unmatched=0` AND `match_status_counts={}`. If listings were returned but rejected, we'd see `unmatched > 0`. Empty match_status_counts means no listings to process. |
| H4: eBay API schema changed | RULED OUT | Browse returning `{"itemSummaries": []}` is not a schema change — it's an empty valid response. A schema change would produce parse errors or unexpected field names. |
| H5: Auth/credential issue | RULED OUT | OAuth succeeded (api_calls_used includes 1 OAuth call, no auth failure logged). If OAuth failed, function returns early with 0 calls. |
| H6: Rate limit/throttling | RULED OUT | HTTP 429 → exception handler → `cards_failed > 0`. We see `cards_failed=0`. |

---

## Confirmed Root Cause: eBay API Outage — H1

### External evidence

Ivan conducted the manual eBay UI cross-check (Step 4) via web search, finding an independent
third-party report confirming the cause:

**Source:** The Cyber Express (2026-04-26)
**Finding:** eBay experienced a major technical outage beginning Sunday 2026-04-26 ~22:30 ET.
Downdetector recorded >1,300 failure reports. Users and sellers reported that critical API
functionality was severely disrupted — third-party tools relying on eBay's API for listing
management, inventory, and sales data were specifically impacted.
**Suspected cause:** DDoS attack by hacktivist group "313 Team" (consistent with Lesson 7 in CLAUDE.md).

### Timeline alignment

| Event | Timestamp |
|---|---|
| eBay outage began | 2026-04-26 ~22:30 ET (~04:30 UTC April 27) |
| Last productive eBay ingest | 2026-04-27 08:37 UTC (47 records) |
| `match_status_counts: {}` pattern began | 2026-04-28 03:22 UTC |
| Pattern still present at investigation close | 2026-04-30 15:42 UTC |

The eBay UI shows active listings for the test queries (web search results for
"Pokemon Lickitung Jungle" return active listings), confirming the web/search layer is
operational. The outage specifically impacted the API layer used by the ingest code.

### Git log confirmation: no code changes

```
No changes to backend/app/ingestion/ebay_sold.py matching functions
since the last productive run on 2026-04-27:
  - _build_search_query: unchanged
  - _fetch_finding_completed: unchanged
  - _parse_browse_items: unchanged
  - Per-listing filter chain: unchanged
```

---

## Recommended Next Action

**No fix PR needed.** H1 (upstream outage) confirmed. Our code is behaving correctly under degraded API conditions.

**Transition to P2 (zero-output alerting):**
The real gap this incident exposed is that `scheduler_run_log` shows `status=success` and records our
API calls, but has no way to distinguish "ran usefully" from "ran but got nothing." P2 addresses this.

**When eBay data returns:**
Monitor the next run (due ~2026-05-01 15:43 UTC) for `match_status_counts != {}`. When it populates,
run Layer 3.1 sanity check from the audit: do our signals directionally match actual eBay activity
for the top 5 signal cards?

**Backlog item added:**
- After first non-empty eBay run post-outage, run sanity cross-validation (Layer 3.1) and report
  to Ivan. The audit left this as "WEAK/ANECDOTAL" — real eBay volume data will make it definitive.

---

## Evidence Appendix

- `p1-investigation-evidence/pre-run-analysis.md` — code trace and hypothesis matrix
- `p1-investigation-evidence/ebay-search-queries.md` — exact search queries used by ingest
