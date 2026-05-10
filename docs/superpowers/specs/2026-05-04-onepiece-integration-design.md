# One Piece TCG Phase 1 Integration — Design Spec

**Status:** Approved — parked, ready to execute after TASK-301 (Pro launch) ships
**Task:** TASK-202 (Phase 1 implementation)
**Date:** 2026-05-04
**Author:** Claude Code
**Research doc:** `docs/strategy/05_onepiece_integration.md`
**Related:** TASK-202b (OP13 source gap follow-up, deferred)

---

## Summary

Wire One Piece TCG (OPTCG) as a third live game using `optcgapi.com` as the free Phase 1 catalog + price source, with eBay Browse API as secondary. Five seed sets: OP01, OP05, OP08, OP09, OP13. Two-pass DB write enforces Lesson 6 (catalog/price decoupled). Kill-switch env var `ONEPIECE_INGEST_ENABLED`. 12h interval, conservative for undocumented optcgapi.com rate limits.

**No alembic migration required.** `assets.game` is a plain `String(32)` column with no CheckConstraint — `'one_piece'` writes freely.

---

## Lesson 6 Reference

> *"Lesson 6 (downstream-filtered silently): Asset 行存在与 Price 行存在的判断必须解耦。Catalog 数据是否被 ingest 的决定不能依赖 price 字段的非零性。"*

Option A (catalog+price coupled, skip both on price=0) was rejected because optcgapi.com can return `price=0` for real cards — new releases before first sale, illiquid cards, API field naming inconsistencies. Under Option A, those cards would never have an `Asset` row, producing silent data loss identical to the YGO 13-set failure mode. Option B (always upsert Asset, conditionally write PriceHistory) eliminates this at zero extra API complexity.

---

## Architecture

### Files changed

| File | Action |
|---|---|
| `backend/app/ingestion/game_data/optcgapi_client.py` | **New** — HTTP client + `OnePieceCard` dataclass + `APINotFoundError` |
| `backend/app/ingestion/onepiece.py` | **New** — `ingest_onepiece_sets()`, two-pass persist |
| `backend/app/backstage/scheduler.py` | Add `_run_onepiece_ingestion()` + job registration guarded by kill switch |
| `backend/app/core/config.py` | Add `onepiece_ingest_enabled: bool = False` |
| `backend/app/services/scheduler_run_log_service.py` | Add `JOB_ONEPIECE = "onepiece-ingestion"` + add to `_monitored_jobs` |
| `BACKLOG.md` | Add TASK-202b |
| `tests/test_onepiece_ingest.py` | **New** — 6 TDD test cases |

**No changes:** `backend/app/models/game.py` status stays `"coming_soon"` (promote is an operator action post-merge, not in PR scope).

---

## Data Model

### `OnePieceCard` (in `optcgapi_client.py`)

```python
@dataclass(frozen=True)
class OnePieceCard:
    card_number: str        # "OP01-060" — set code + sequence
    name: str               # "Monkey D. Luffy"
    set_code: str           # "OP01"
    set_name: str           # "Romance Dawn"
    rarity: str             # "Super Rare"
    market_price: Decimal | None
    image_url: str | None
```

Naming follows the would-be convention (`PokemonCard`, `YugiohCard`) — neither exists in the codebase today (both use `CardMetadata` from `base.py`), but `OnePieceCard` is consistent with that pattern.

### `external_id` format

`f"{card_number}|{rarity}"` — e.g. `"OP01-060|Super Rare"`.

Same rationale as YGO's `make_external_id(konami_id, set_entry_code, rarity)`: a card can exist as both Normal print and Alternate Art / Manga Rare — each is a distinct investable asset with independent price movement.

### `PriceHistory.source` value

`"optcgapi"` — new value, consistent with underscore/lowercase convention (`"pokemon_tcg_api"`, `"ebay_sold"`, `"ygoprodeck_api"`).

### `PriceHistory.market_segment`

**Explicitly pass `market_segment='raw'` in `_write_op_price()`** — do not rely on DB default. This guarantees the null audit (`SELECT COUNT(*) WHERE source='optcgapi' AND market_segment IS NULL`) returns 0 by code contract, not schema fallback.

---

## Client Interface

```python
class APINotFoundError(Exception):
    """Raised when optcgapi.com returns 404 for a set code."""

class OptcgapiClient:
    game = Game.ONE_PIECE
    rate_limit_per_second = 2.0   # conservative — limits not documented by optcgapi.com

    def fetch_set_cards(self, set_code: str) -> list[OnePieceCard]:
        """Returns all cards for a set.

        Raises APINotFoundError if set not in source (expected for OP13 until
        optcgapi.com adds coverage — see TASK-202b).
        Returns [] if set exists but has no cards.
        Raises for other HTTP errors (5xx, timeout).
        """
```

---

## Ingestion Logic

### Sets

```python
ONEPIECE_SETS = ["OP01", "OP05", "OP08", "OP09", "OP13"]
ONEPIECE_PRICE_SOURCE = "optcgapi"
```

OP13 included. If optcgapi.com doesn't have it yet, `APINotFoundError` is caught per-set and recorded as `"not_found_in_source"` in `meta_json`. This is the expected path until TASK-202b is triggered.

### Two-pass persist

```python
def _persist_cards(session: Session, cards: list[OnePieceCard], captured_at: datetime) -> tuple[int, int]:
    """Returns (assets_created, price_points_inserted)."""
    assets_created = 0
    price_points_inserted = 0
    for card in cards:
        # Pass 1 — always upsert Asset, price field irrelevant
        asset, created = _upsert_op_asset(session, card)
        if created:
            assets_created += 1

        # Pass 2 — PriceHistory only when price is real
        price = card.market_price or Decimal("0")
        if price > 0:
            _write_op_price(session, asset.id, price, captured_at)
            price_points_inserted += 1

    session.commit()   # single transaction — both passes atomic
    return assets_created, price_points_inserted
```

### Per-set loop

```python
def ingest_onepiece_sets(session: Session) -> OnePieceIngestionResult:
    result = OnePieceIngestionResult()
    captured_at = datetime.now(UTC).replace(microsecond=0)
    client = OptcgapiClient()

    for set_code in ONEPIECE_SETS:
        try:
            cards = client.fetch_set_cards(set_code)
            if not cards:
                result.per_set[set_code] = "empty"
                continue
            created, inserted = _persist_cards(session, cards, captured_at)
            result.per_set[set_code] = f"success ({len(cards)} cards)"
            result.assets_created += created
            result.price_points_inserted += inserted
        except APINotFoundError:
            result.per_set[set_code] = "not_found_in_source"  # OP13 expected path
        except Exception as exc:
            result.per_set[set_code] = f"failed: {str(exc)[:100]}"
        finally:
            time.sleep(1.0 / client.rate_limit_per_second)

    return result
```

### Scheduler status mapping

Maps to existing `SchedulerRunLog` status values:

| Condition | Status |
|---|---|
| All sets `"success (...)"` | `"success"` |
| ≥1 success + ≥1 failure/not_found | `"partial"` |
| All sets failed or not_found | `"error"` |

`not_found_in_source` counts as non-success for status calculation — OP13 missing is expected but not a success.

---

## Scheduler Integration

### Startup delay ladder (full, post-PR)

```
scheduled-ingestion      120s   ( 2 min)
signal-sweep             600s   (10 min)
ebay-ingestion           660s   (11 min)
alert-heartbeat          720s   (12 min)
yugioh-ingestion         780s   (13 min)
onepiece-ingestion       840s   (14 min)  ← NEW
bulk-set-price-refresh   900s   (15 min)
explanation-sweep        960s   (16 min)
market-digest-send      1200s   (20 min)
```

No slot conflicts. 60s gap on each side of the new entry.

### Interval rationale

**12h for Phase 1.** optcgapi.com publishes no rate limit documentation — conservative interval avoids unknown throttling. Accepted trade-off: OPTCG data refreshes at 50% of YGO frequency (6h) until Phase 2.

**Phase 2 trigger:** ARR ≥ $5K → migrate to `tcgapi.dev` Pro ($49.99/mo) → promote interval to 6h matching YGO. See TASK-202b and `docs/strategy/05_onepiece_integration.md` §2.

### Kill switch

```python
# config.py
onepiece_ingest_enabled: bool = False

# scheduler.py — in prepare_scheduler():
if settings.onepiece_ingest_enabled:
    scheduler.add_job(
        _run_onepiece_ingestion, "interval", hours=12,
        id=JOB_ONEPIECE, next_run_time=None,
    )
```

Railway default: `ONEPIECE_INGEST_ENABLED=false` until operator verification passes.

### `_monitored_jobs`

Add `JOB_ONEPIECE` to `_monitored_jobs` in `_send_heartbeat`. Zero-output alert applies from day one per Lesson 9.

---

## Edge Cases

| Case | Behaviour |
|---|---|
| `price=0` | Asset upserted, PriceHistory skipped |
| `price=None` | Treated as 0 — Asset upserted, PriceHistory skipped |
| `price>0` | Asset + PriceHistory both written |
| Duplicate `external_id` in API response | Upsert idempotent via `external_id` unique path — no duplicate Asset |
| Card already in DB, metadata updated upstream | Upsert refreshes `metadata_json` |
| Required field missing in API response | Skip card, `logger.warning(...)`, continue loop |
| Set not in optcgapi.com (e.g. OP13) | `APINotFoundError` caught, `per_set[set_code] = "not_found_in_source"`, loop continues |
| Full set fetch fails (5xx, timeout) | Generic `except` caught, `per_set[set_code] = "failed: ..."`, loop continues |

---

## Tests (TDD — write before implementation)

File: `tests/test_onepiece_ingest.py`. SQLite in-memory + mock `OptcgapiClient`, same pattern as `tests/test_ygo_ingest_segment.py`.

```
test_asset_created_when_price_zero
    card with market_price=0 → Asset row exists, no PriceHistory row

test_asset_created_when_price_null
    card with market_price=None → Asset row exists, no PriceHistory row

test_asset_and_price_written_when_price_positive
    card with market_price=Decimal("5.50") → Asset + PriceHistory both present
    PriceHistory.market_segment == 'raw'  ← explicit assertion

test_upsert_idempotent_on_duplicate_external_id
    same card appears twice in API response → only one Asset row

test_schema_error_skips_card_continues_loop
    malformed card (missing required field) → WARN logged, other cards processed

test_api_not_found_continues_next_set
    OptcgapiClient.fetch_set_cards raises APINotFoundError for "OP13"
    → result.per_set["OP13"] == "not_found_in_source"
    → other sets still processed
```

---

## Post-Deploy SQL Verification

Run after first completed 12h cycle. Expected results noted inline.

```sql
-- 1. Set coverage (expect rows for OP01/05/08/09; OP13 may be absent)
SELECT LEFT(card_number, 4) AS set_code, COUNT(*) AS cards
FROM assets
WHERE game = 'one_piece'
GROUP BY 1
ORDER BY 1;

-- 2. Price coverage ratio
--    without_price > 0 is healthy (illiquid / new cards have no price yet)
--    without_price > 50% of total warrants investigation
SELECT
  COUNT(DISTINCT a.id) FILTER (WHERE p.id IS NOT NULL) AS with_price,
  COUNT(DISTINCT a.id) FILTER (WHERE p.id IS NULL)     AS without_price,
  COUNT(DISTINCT a.id)                                  AS total
FROM assets a
LEFT JOIN price_history p
  ON p.asset_id = a.id AND p.source = 'optcgapi'
WHERE a.game = 'one_piece';

-- 3. market_segment null audit (must return 0 — guaranteed by code, not schema default)
SELECT COUNT(*) AS null_count
FROM price_history
WHERE source = 'optcgapi' AND market_segment IS NULL;
```

---

## Operator Action Items (post-merge, not in PR)

1. **Enable ingestion:** Railway → set `ONEPIECE_INGEST_ENABLED=true` on the backend service.
2. **Verify first cycle:** After first 12h cycle completes, run the three SQL verification queries above. Confirm `null_count = 0` and `with_price / total > 0`.
3. **7-day observation:** Monitor `scheduler_run_log` for `job_name='onepiece-ingestion'`. Confirm `status='success'` or `'partial'` (OP13 `not_found_in_source` is expected and acceptable for status `'partial'`).
4. **Status promote:** After 7 stable days, update `GAME_CONFIG[Game.ONE_PIECE].status` from `"coming_soon"` to `"beta"` in a routine PR.

---

## TASK-202b Reference

**TASK-202b — OP13 data source gap**

Trigger: optcgapi.com still has no OP13 coverage after 30 days **and** Plus/Pro users ask why OP13 is missing.

Options (decide at trigger time, not now):
- Wait for optcgapi.com to add OP13 (passive)
- Test tcgapi.dev free tier for OP13 coverage
- Accelerate Phase 2 (tcgapi.dev Pro $49.99/mo, standard trigger: ARR ≥ $5K)
