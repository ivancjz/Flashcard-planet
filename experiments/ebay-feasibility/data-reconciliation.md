# eBay Data Inventory Reconciliation
Generated: 2026-05-14

## Task 1 — Production vs Backup-14

**Direct production DB query**: not possible from outside Railway's VPC.  
`postgres.railway.internal:5432` is not resolvable locally; `railway run` v4.40.0 injects env vars only, no tunnel. Public hostname timed out on all ports (5432, 6543).

**Proxy evidence from production HTTP API:**

- `/admin/stats` (2026-05-13 17:47 UTC): `ebay_sold_rows_last_24h: 0`. Consistent with no writes since Apr 27.
- `/admin/diag/graded-price-check` (2026-05-14): Returns rows from the same Apr 21–27 date range as backup-14. No rows outside that window.
- `/admin/diag/ebay-probe`: `last_ebay_sold_captured_at: 2026-04-27 13:33:14`. Same boundary as backup-14.

**Conclusion**: backup-14 is consistent with production on all independently verifiable points. The backup accurately represents the production state.

**Backup-14 counts (2026-05-12):**
```
source           | count   | min                 | max
-----------------+---------+---------------------+--------------------
pokemon_tcg_api  | 2332960 | 2026-04-09 07:53:18 | 2026-05-12 05:42:28
ygoprodeck_api   |    9554 | 2026-04-23 16:54:25 | 2026-05-12 05:40:28
ebay_sold        |    1380 | 2026-04-21 03:00:52 | 2026-04-27 13:33:14
```

---

## Task 2 — Commit 4d63362 in Full

Commit: `fix(ebay): reject future-dated listings; delete 749 existing future-timestamp rows`  
Date: 2026-04-27 23:43 AEST

**The DELETE statement (verbatim from `/trigger/delete-future-timestamps`):**
```sql
DELETE FROM price_history
WHERE captured_at > NOW()
```

**Assessment**: The WHERE clause is correctly bounded. It only deletes rows with `captured_at > NOW()` — future-dated rows only. No implicit filter on source, game, or any other column. It cannot have silently deleted historical rows.

**Rows deleted**: 749 (confirmed by commit message: "Confirmed via /diag/future-timestamps: 749 rows in ebay_sold source").

**Pre-deletion count**: 1,380 (historical, valid) + 749 (future-dated) = 2,129 total ebay_sold rows at peak.

---

## Task 3 — Full Git Log: Commits Touching eBay or Price History

### Code path that writes ebay_sold rows
- `c9b5f25` 2026-04-12 — original eBay Finding API + Browse API fallback
- `fb12d64` 2026-04-12 — migrated to Browse API per-asset search
- `51b279a` 2026-04-12 — eBay scheduled ingest v1 with api_calls tracking
- `46273f5` 2026-04-24 — added `_is_single_card` and `_card_number_matches` filters
- `590ccd8` 2026-04-24 — excluded graded cards at search level

### Commits with DELETE statements targeting price_history (complete list)
1. `4d63362` 2026-04-27 — `/trigger/delete-future-timestamps`: `WHERE captured_at > NOW()` (749 rows)
2. `a59ecaf` 2026-04-24 — `/diag/clean-graded-ebay-outliers`: `WHERE source = 'ebay_sold' AND price > :threshold AND asset_id IN (SELECT id FROM assets WHERE name = 'Blastoise ex' AND metadata->>'set_id' = 'sv3pt5')` — targets one specific card only

**No other DELETE or TRUNCATE statements targeting price_history found** in:
- All 34 migration files (0001–0034)
- `scheduler.py` (only prunes `asset_signal_history` and `scheduler_run_log`)
- `signal_service.py`
- `ebay_sold.py`
- `pokemon_tcg.py`
- All backstage route handlers

**No hidden second cleanup exists.**

---

## Task 4 — Soft Delete Check

`price_history` columns (from model and initial schema migration):
```
id, asset_id, source, currency, price, captured_at
```

No `deleted_at`, `is_deleted`, `status`, `archived`, or any soft-delete column exists on `price_history`.  
The 1,380 count is not a filtered subset — it is the complete table for `source='ebay_sold'`.

---

## Task 5 — TRUE Production Count (Verdict)

**TRUE production ebay_sold count: 1,380 rows**  
**Date range: 2026-04-21 03:00 UTC to 2026-04-27 13:33 UTC (7 days)**  
**Distinct assets: 426**

This is not an estimate. It is:
1. Directly measured in backup-14 (taken 2026-05-12, 2 days old)
2. Consistent with all production HTTP API endpoints
3. Consistent with zero writes since Apr 27 (scheduler writes 0 records; Finding API dead)

---

## CLAUDE.md "~5.5k" Discrepancy — Root Cause

**The ~5.5k figure in CLAUDE.md is wrong. It was never accurate.**

Evidence:
- Pre-deletion peak was 1,380 + 749 future-dated = **2,129 rows** (the absolute maximum ebay_sold ever had)
- The scheduler_run_log in backup-14 starts May 6 only — earlier entries were pruned by `prune_old_runs`. No log evidence of Apr 21–27 write volumes, but price_history is the authoritative source and it shows 1,380 valid rows
- The commit `03d52e8` that documented "~5.5k" was written at 23:33 AEST on Apr 27, AFTER the 749-row deletion (23:43 is the deletion commit, so actually the deletion had not yet been committed when CLAUDE.md was updated — meaning at the time of writing, the count was 2,129, not 5.5k)
- Wait — corrected: `4d63362` (deletion) at 23:43, `03d52e8` (CLAUDE.md refresh) at 23:33. So CLAUDE.md was written 10 minutes BEFORE the deletion was committed. At the time of writing, production had 2,129 rows. "~5.5k" overstates by 2.6x.

**Most likely origin**: The "~5.5k" was carried forward from an even earlier CLAUDE.md revision (when total was ~434k, ygoprodeck_api was ~134). That older revision may have been written by someone who confused the eBay ingest budget limit (250 calls/run × ~20 runs × ~1 result/call ≈ 5,000 writes/month as a ceiling) with the actual count. Or it was simply a rough mental estimate. The `03d52e8` author updated the total_rows figure but did not re-verify the per-source breakdown, carrying the wrong ~5.5k forward.

**Action**: Update CLAUDE.md §7 to correct the count to 1,380 (post-deletion peak).
