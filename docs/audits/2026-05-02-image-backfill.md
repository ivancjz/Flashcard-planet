# Image Backfill Audit — TASK-204

**Date:** 2026-05-02
**Auditor:** Claude Code
**Conclusion:** Image backfill IS implemented with retry logic. Current imageless rate appears to be ~0% for the cards returned by the API (sampled 200/3,966). No immediate action required.

---

## 1. Does image backfill currently retry?

**Yes — two-layer retry system exists.**

### Layer 1: `run_backfill_pass()` in `pokemon_tcg.py`

Called by the `scheduled-ingestion` scheduler job after each normal ingest run. It:

1. Calls `_query_missing_image(session, limit=batch_size)` — queries assets where `metadata_json -> 'images' -> 'small'` is NULL or empty
2. Merges with missing-price list, deduplicates, caps at `backfill_batch_size` (default 100, configurable)
3. Calls `backfill_single_card(session, asset)` for each — re-fetches from Pokemon TCG API and overwrites `metadata_json` with fresh data including images
4. On failure: calls `record_backfill_failure(session, asset_id, exc)` → writes to `failed_backfill_queue`

### Layer 2: `run_retry_pass()` in `backfill_retry_service.py`

Separate scheduler job (`retry-pass`, interval=6h, `RETRY_PASS_ENABLED=true` in production).

- Processes `failed_backfill_queue` rows oldest-first
- Retries up to `MAX_RETRY_ATTEMPTS = 3` per asset
- After 3 consecutive failures: marks `is_permanent = True` (stops retrying)
- `FailureType` enum classifies failures: `API_TIMEOUT`, `NO_RESULT`, `MAPPING_FAILED`, `IMAGE_FETCH_FAILED`, `PRICE_FETCH_FAILED`, `UNKNOWN`

**Image-specific failure type exists:** `IMAGE_FETCH_FAILED` is a tracked failure category.

---

## 2. How are images stored?

Images are stored in `assets.metadata_json` (JSONB column), not as a separate column:

```sql
metadata_json -> 'images' -> 'small'   -- card thumbnail (used in lists)
metadata_json -> 'images' -> 'large'   -- full card image
```

The `web.py` API layer reads `metadata_json->'images'->>'small'` inline in SQL queries and returns it as `image_url` in API responses.

The `pokemon_client.py` populates `image_url` in `CardMetadata` from `raw.get("images", {}).get("large")` — note: it reads `large` at ingest time but the web layer reads `small` for display. Both are present in the API response from Pokemon TCG API.

---

## 3. Current imageless rate (production, 2026-05-02)

**Measurement method:** API sampling via `GET /api/v1/web/cards?limit=200&game=pokemon`

| Metric | Value |
|---|---|
| Total Pokemon assets | 4,371 |
| Returned by cards API | 3,966 (excludes assets without price history — API filters for priceable cards) |
| Sample size checked | 200 |
| Imageless in sample | **0** |
| Estimated imageless rate | **~0%** |

**Important caveat:** The cards API only returns assets that have at least one `price_history` row. The 405 assets not returned (4,371 - 3,966) may include some imageless cards that were created but never had a price fetched. The backfill queries the full `assets` table, so these would still be in the backfill queue.

---

## 4. `failed_backfill_queue` state

Could not query directly via `railway run` (env isolation issue). From scheduler logs and config:

- `RETRY_PASS_ENABLED = true` (confirmed in Railway env vars)
- `retry-pass` job runs every 6 hours
- The retry-pass job IS registered and active (confirmed in scheduler.py)

Historical evidence from scheduler_run_log: `scheduled-ingestion` records written = 709 per run (consistent over last 3 runs), suggesting no large backlog of missing images is being discovered.

---

## 5. Known limitation: YGO cards have no image backfill

`_query_missing_image()` explicitly filters `WHERE game = 'pokemon'` (line 614 of pokemon_tcg.py). YGO assets that lack images will **not** be picked up by the backfill pass. 

YGO images come from YGOPRODeck API via `ygo.py`. There is no equivalent `_query_missing_image` for YGO. The YGO ingestion either gets the image on first fetch or leaves it NULL with no retry path.

---

## 6. Answer to TASK-204 question

> "Does image backfill currently retry, where, and how often are cards left imageless?"

**Retry exists:** Yes, two-layer (backfill_pass inline + retry-pass scheduled).

**Where:** `backend/app/ingestion/pokemon_tcg.py:run_backfill_pass()` + `backend/app/services/backfill_retry_service.py:run_retry_pass()`

**How often imageless:** ~0% for Pokemon cards currently in production. The backfill system appears to be working.

**Gap:** YGO has no image retry path. Not urgent today (67 YGO assets, low visibility), but a follow-up task if/when YGO expands to 300+ assets.

---

## 7. Follow-up tasks proposed

| Task | Priority | Scope |
|---|---|---|
| Add YGO image retry path (extend `_query_missing_image` to include yugioh game) | P2 | ~20 LOC in pokemon_tcg.py + ygo.py |
| Add `failed_backfill_queue` count to `/admin/diag/subscription` or existing diagnostic | P2 | Add to next diagnostic endpoint PR |

Neither blocks TASK-301. Added as `needs_triage` in BACKLOG.
