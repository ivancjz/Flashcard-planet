# Ingestion Layer + AI Asset Mapper — Design Spec
**Date:** 2026-04-10  
**Status:** Approved  
**Scope:** Phase 1 — Pokémon, eBay sold listings only  

---

## 1. Goal

Build the complete data ingestion pipeline that:
1. Fetches sold card listings from eBay (stubbed until credentials available)
2. Stages raw listings with full deduplication
3. Maps every listing to a canonical asset identity via rule engine first, Claude API second
4. Writes confirmed price events to the existing `assets` + `price_history` tables
5. Never pays for the same Claude mapping twice
6. Is fully idempotent — safe to re-run at any time without data corruption

This is the foundation that every other platform feature (signals, smart pool, alerts, Discord bot) depends on.

---

## 2. Architecture

```
runner.py (cron loop, every 2 hours)
  └─ pipeline.py.run_batch()
       ├─ EbayClient.fetch_sold_listings()      [async, stubbed]
       ├─ staging.repository.upsert_batch()     [dedup on source_listing_id]
       ├─ load unprocessed rows (status=pending)
       ├─ mapping_cache.lookup_batch()          [zero-cost cache hit]
       ├─ rule_engine.match_batch()             [RapidFuzz, threshold ≥0.75]
       ├─ ai_mapper.map_batch()                 [Claude, batched 20x, prompt-cached]
       │    └─ confidence <0.50 → human_review_queue
       └─ asset_writer.write_batch()            [upsert assets + price_history]
```

---

## 3. File Structure

All new files under `backend/app/ingestion/`:

```
backend/app/ingestion/
  __init__.py
  runner.py                  ← cron loop, graceful shutdown on SIGTERM
  pipeline.py                ← orchestrates full batch flow
  metrics.py                 ← Prometheus counters per stage

  ebay/
    __init__.py
    client.py                ← abstract EbayClient interface
    stub_client.py           ← stub returns realistic sample data
    models.py                ← EbayListing dataclass

  staging/
    __init__.py
    repository.py            ← upsert_batch, load_pending, mark_processed

  matcher/
    __init__.py
    catalog.py               ← PokémonTCG API loader, in-memory + 24h TTL
    rule_engine.py           ← RapidFuzz token_sort_ratio, confidence scoring
    ai_mapper.py             ← Claude API, 20-listing batches, structured output
    mapping_cache.py         ← persistent cache: read before AI, write after confirm

backend/app/models/
  raw_listing.py             ← SQLAlchemy model
  asset_mapping_cache.py     ← SQLAlchemy model
  human_review.py            ← SQLAlchemy model

alembic/versions/
  XXXX_add_ingestion_tables.py
```

---

## 4. Database Schema

### `raw_listings` (staging table)
```sql
CREATE TABLE raw_listings (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source              VARCHAR(50)  NOT NULL DEFAULT 'ebay',
  source_listing_id   VARCHAR(200) NOT NULL,
  raw_title           TEXT         NOT NULL,
  price_usd           DECIMAL(12,2) NOT NULL,
  sold_at             TIMESTAMPTZ  NOT NULL,
  status              VARCHAR(20)  NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending','matched','ai_matched','review','rejected')),
  mapped_asset_id     UUID REFERENCES assets(id),
  confidence          DECIMAL(4,3),
  match_method        VARCHAR(20) CHECK (match_method IN ('rule','ai','cache','human')),
  ingested_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  processed_at        TIMESTAMPTZ,
  UNIQUE(source, source_listing_id)
);
CREATE INDEX idx_raw_listings_status ON raw_listings(status) WHERE status = 'pending';
```

### `asset_mapping_cache` (never pay Claude twice)
```sql
CREATE TABLE asset_mapping_cache (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  normalized_title    VARCHAR(500) NOT NULL UNIQUE,
  asset_id            UUID NOT NULL REFERENCES assets(id),
  confidence          DECIMAL(4,3) NOT NULL,
  match_method        VARCHAR(20)  NOT NULL,
  hit_count           INTEGER      NOT NULL DEFAULT 0,
  created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  last_hit_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_mapping_cache_title ON asset_mapping_cache(normalized_title);
```

### `human_review_queue`
```sql
CREATE TABLE human_review_queue (
  id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  raw_listing_id          UUID NOT NULL REFERENCES raw_listings(id),
  raw_title               TEXT NOT NULL,
  best_guess_asset_id     UUID REFERENCES assets(id),
  best_guess_confidence   DECIMAL(4,3),
  reason                  VARCHAR(200),
  created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  resolved_at             TIMESTAMPTZ,
  resolved_by             VARCHAR(100)
);
```

---

## 5. eBay Client Interface

```python
# ebay/client.py
class EbayClient(Protocol):
    async def fetch_sold_listings(
        self,
        category: str,
        limit: int = 100,
    ) -> list[EbayListing]: ...

# ebay/models.py
@dataclass
class EbayListing:
    source_listing_id: str
    raw_title: str
    price_usd: Decimal
    sold_at: datetime
    currency_original: str
    url: str | None
```

The stub returns 20–50 realistic Pokémon listing titles sampled from real eBay patterns (mixed quality, some with grades, some with variants, some with noise). Real client implementation slots in by replacing `stub_client.py` with `live_client.py` — zero changes to the pipeline.

---

## 6. Rule Engine

**Source:** PokémonTCG public API (`api.pokemontcg.io/v2/cards`) — free, no key required for basic use.

**Catalog loading:**
- Fetched at startup, stored in memory as a dict keyed by normalized card name + set + number
- Refreshed every 24 hours via background task
- Redis cache (if available) for cross-process sharing; falls back to in-process dict

**Matching algorithm:**
1. Strip noise tokens from title (promotional words, shipping terms, seller prefixes)
2. Extract candidate fields: card name, set abbreviation, card number, grade, language
3. RapidFuzz `token_sort_ratio` against catalog entries — handles word order variation
4. Confidence score formula:
   - Name match ≥95: +0.50
   - Set match ≥90: +0.20
   - Card number exact: +0.20
   - Language detected: +0.05
   - Grade detected correctly: +0.05
5. Score ≥0.75 → confirmed match, skip AI
6. Score 0.50–0.74 → send to Claude
7. Score <0.50 (before AI) → send to Claude regardless

---

## 7. AI Asset Mapper (Claude Integration)

**Model:** `claude-sonnet-4-6`  
**Batching:** 20 listing titles per API call  
**Prompt caching:** System prompt + few-shot examples marked `cache_control: ephemeral` → stable prefix cached, ~90% input token savings on repeated calls  
**Output:** JSON schema enforced, Pydantic-validated  

### Prompt structure
```
[SYSTEM — cached]
You are an expert trading card identifier for Flashcard Planet.
Given raw eBay listing titles, extract structured card identity fields.

Rules:
- game is always "Pokemon" for this pipeline
- grade_company: PSA / BGS / CGC / SGC only, null if raw
- grade_score: numeric only (10, 9.5, etc), null if ungraded
- variant: SAR / IR / UR / HR / FA / Alt Art / Rainbow etc, null if standard
- language: EN / JP / KR / ZH / DE / FR, default EN if unclear
- confidence: 0.0–1.0, your honest assessment of match quality
- card_number: exact format e.g. "199/165", null if not found

[FEW-SHOT EXAMPLES — cached]
Title: "Pokemon Charizard ex SAR 199/165 SV151 PSA 10"
→ {"name":"Charizard ex","set_name":"Scarlet & Violet 151","card_number":"199/165","variant":"SAR","grade_company":"PSA","grade_score":10.0,"language":"EN","confidence":0.97}

Title: "PIKACHU FULL ART PROMO JAPANESE MINT"
→ {"name":"Pikachu","set_name":null,"card_number":null,"variant":"Full Art","grade_company":null,"grade_score":null,"language":"JP","confidence":0.61}

[USER — not cached]
Extract fields for these {n} listings:
1. {title_1}
2. {title_2}
...
```

### Post-processing
- `confidence ≥ 0.75` → write to assets + mark `ai_matched`
- `confidence 0.50–0.74` → write with disclaimer flag, mark `ai_matched`
- `confidence < 0.50` → human_review_queue, mark `review`
- Every result ≥ 0.50 written to `asset_mapping_cache` with normalized title key

---

## 8. Cost Model

| Source | Monthly calls (estimated) | Notes |
|---|---|---|
| PokémonTCG API | ~720 | Catalog refresh every 2h |
| mapping_cache hits | ~35,000 | Zero cost — DB lookup |
| Rule engine matches | ~10,000 | Zero cost — in-process |
| Claude API calls | ~250 | 20 titles/call × 5,000 uncached listings |
| Claude token cost | ~$8–12/month | Prompt cache reduces input by 90% |

**Total AI cost target: under $15/month at Phase 1 volume.**

---

## 9. Observability

Prometheus counters exposed via existing FastAPI `/metrics` endpoint:

```
ingestion_listings_fetched_total        [source]
ingestion_listings_staged_total         [source, deduped]
ingestion_cache_hits_total              
ingestion_rule_matches_total            [confidence_bucket]
ingestion_ai_calls_total               
ingestion_ai_listings_mapped_total      [confidence_bucket]
ingestion_human_review_queue_total      
ingestion_assets_written_total          [method]
ingestion_batch_duration_seconds        [stage]
ingestion_errors_total                  [stage, error_type]
```

Structured log output (JSON) on every batch:
```json
{
  "event": "batch_complete",
  "fetched": 87,
  "staged_new": 72,
  "cache_hits": 31,
  "rule_matched": 28,
  "ai_mapped": 11,
  "review_queued": 2,
  "assets_written": 70,
  "duration_ms": 4821
}
```

---

## 10. Reliability

- **Idempotency:** `UPSERT` on `source_listing_id` — re-running the pipeline never creates duplicates
- **Graceful shutdown:** `runner.py` traps `SIGTERM`, finishes current batch, exits cleanly
- **AI retries:** exponential backoff with jitter (0.5s, 1s, 2s, 4s) on Claude API rate limits
- **Partial batch safety:** DB writes are per-listing transactions — a failure at listing 15 of 20 doesn't roll back listings 1–14
- **Dead letter:** listings that fail 3 times are marked `rejected` with error reason, not silently lost

---

## 11. Configuration

All values via environment variables, no hardcoding:

```
EBAY_STUB_MODE=true                    # flip to false when credentials ready
EBAY_APP_ID=                           # slots in later
EBAY_CERT_ID=                          # slots in later
POKEMONTCG_API_KEY=                    # optional, raises rate limits
ANTHROPIC_API_KEY=                     # Claude API
INGESTION_INTERVAL_SECONDS=7200        # 2 hours
INGESTION_BATCH_SIZE=100               
AI_BATCH_SIZE=20                       
AI_CONFIDENCE_THRESHOLD_AUTO=0.75      
AI_CONFIDENCE_THRESHOLD_REVIEW=0.50    
```

---

## 12. Out of Scope (Phase 1)

- BullMQ / Redis job queue (add in Phase 2 — interfaces designed for it)
- TCGplayer, Cardmarket, PriceCharting ingestion
- Sports cards, MTG, other categories
- Watchlist-triggered 15-minute polling
- Real eBay API credentials (stub used throughout Phase 1 dev)
- Human review UI (queue populated, UI is Phase 2)
