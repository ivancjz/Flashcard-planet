Review PR fix/liquidity-source-filter for the Flashcard Planet signal audit.

Context:
- Audit identified that get_liquidity_snapshots in liquidity_service.py was counting pokemon_tcg_api
  hourly bulk-refresh polls (~180 rows/card/7d) as sales when computing sales_count_7d, sales_count_30d,
  and last_real_sale_at. Every card in the bulk-refresh pool scored liquidity_score=95-98 regardless
  of actual eBay activity, clearing the BREAKOUT threshold with zero actual sales evidence.
- Bug 1 in audits/2026-05-01/REPORT.md
- The fix adds ebay_sold source filters to sales_count_7d, sales_count_30d, last_real_sale_at aggregates
  inside get_liquidity_snapshots, while preserving history_depth and source_count as all-source metrics.

Change made to backend/app/services/liquidity_service.py:
1. Added `and_` to sqlalchemy imports
2. Added `EBAY_SOLD_PRICE_SOURCE` to price_sources import
3. Changed sales_count_7d CASE: added `PriceHistory.source == EBAY_SOLD_PRICE_SOURCE` condition
4. Changed sales_count_30d CASE: added `PriceHistory.source == EBAY_SOLD_PRICE_SOURCE` condition
5. Changed last_real_sale_at MAX: uses CASE to return captured_at only for ebay_sold rows (else NULL)
6. Preserved: history_depth counts ALL non-sample rows; source_count counts ALL distinct non-sample sources

Tests added: tests/test_liquidity_sales_source_filter.py (8 new tests, all pass)
- 5 tests were RED on main, now GREEN
- 3 preservation tests stay GREEN (history_depth and source_count unchanged)
- Full suite: 893 passed, 0 failures

Specifically check:
1. Is 'ebay_sold' the correct source value? Verify against schema and existing inserts in the codebase.
   Check backend/app/core/price_sources.py and how the eBay ingest actually writes source values.
2. Does the filter break any other code path that reads from the same query? Search for callers of
   get_liquidity_snapshots, get_asset_signal_snapshots, and any code reading sales_count_7d.
3. Is there a downstream cache or materialized view that needs invalidation?
4. The audit notes liquidity_score feeds into alert_confidence (35% weight). Now that liquidity_score
   will be much lower for most cards (0 eBay sales → liquidity ≈ 0-25), does the BREAKOUT threshold
   (confidence >= 70) still make sense? Is this fix silently eliminating nearly all BREAKOUT signals?
5. The last_real_sale_at fix uses a CASE expression returning NULL for non-ebay rows. Does SQLAlchemy's
   func.max(case(..., else_=None)) produce valid SQL in both SQLite (tests) and PostgreSQL (production)?
   Specifically: does MAX(CASE WHEN ... THEN captured_at ELSE NULL END) behave correctly when all rows
   are non-ebay (expected: NULL result)?
