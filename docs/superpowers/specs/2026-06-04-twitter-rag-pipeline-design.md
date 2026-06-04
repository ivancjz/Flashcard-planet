# Twitter/X RAG Pipeline Design

**Date:** 2026-06-04  
**Status:** Approved  
**Phase:** 4 (Sentiment Aggregation — Pro Deep Analysis context)  
**Related roadmap section:** `docs/superpowers/specs/2026-05-28-12month-roadmap-design.md` §Phase 4 Sentiment Aggregation

---

## Context

Pro Deep Analysis (`POST /api/v1/predict/deep`) needs real-world social context to produce credible, differentiated LLM output. This pipeline scrapes X/Twitter for broad TCG keywords, stores only AI-generated summaries (not original text) in a pgvector table on Railway Postgres, and exposes a semantic retrieval function for FastAPI to inject into LLM prompts.

---

## Architecture

```
GitHub Actions (daily cron 02:00 UTC)
        │
        ▼
scripts/twitter_update.py
  ├── xreach/twitter-cli  ← time-sharded per keyword (4 × 6h windows)
  ├── tweet ≤500 chars  → summary = original text
  ├── tweet  >500 chars  → Claude Haiku one-sentence summary
  ├── summary → OpenAI text-embedding-3-small (batch 100)
  └── UPSERT tweet_summaries ON CONFLICT (tweet_id) DO NOTHING
        │
        ▼
Railway Postgres + pgvector
  ├── tweet_keywords    (keyword config, per-game)
  └── tweet_summaries   (summary + vector + metadata)

GitHub Actions (monthly cron 03:00 UTC, 1st of month)
        │
        ▼
scripts/twitter_prep.py
  ├── refresh mention-count aggregates on tweet_keywords
  └── DELETE tweet_summaries WHERE tweet_date < NOW() - INTERVAL '90 days'

FastAPI backend
        │
        ▼
backend/app/services/sentiment_service.py
  └── SELECT summary ORDER BY embedding <-> $query_vec LIMIT 10
        └── injected as context into Pro Deep Analysis LLM prompt
```

---

## Database Schema

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE tweet_keywords (
    id                 SERIAL PRIMARY KEY,
    keyword            TEXT NOT NULL,
    game               TEXT,          -- 'pokemon' / 'ygo' / 'optcg' / NULL (cross-game)
    active             BOOLEAN DEFAULT TRUE,
    mention_count      INT DEFAULT 0,
    last_refreshed_at  TIMESTAMPTZ,
    created_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE tweet_summaries (
    id          SERIAL PRIMARY KEY,
    tweet_id    TEXT UNIQUE NOT NULL,
    keyword     TEXT NOT NULL,
    tweet_date  TIMESTAMPTZ NOT NULL,
    summary     TEXT NOT NULL,              -- never original tweet text
    embedding   VECTOR(1536),               -- text-embedding-3-small
    captured_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ON tweet_summaries USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
CREATE INDEX ON tweet_summaries (tweet_date);
CREATE INDEX ON tweet_summaries (keyword);
```

**Design decisions:**
- `summary` stores AI-generated summary only — original tweet text never written to DB (copyright mitigation)
- `tweet_id UNIQUE` enforces dedup at DB layer; `update.py` also checks in-memory before embedding (avoid wasting API calls)
- `VECTOR(1536)` matches `text-embedding-3-small`; changing embedding model requires dimension update + index rebuild
- `ivfflat` sufficient at expected scale (<500K rows); upgrade to HNSW only if query latency exceeds 200ms
- 90-day rolling retention executed by `prep.py` DELETE — no trigger, no separate job

---

## `twitter_update.py` Logic

```
Inputs: DATABASE_URL, ANTHROPIC_API_KEY, OPENAI_API_KEY, XREACH_API_KEY

1. Load all tweet_keywords WHERE active = TRUE
2. For each keyword:
   a. Split yesterday into 4 × 6h time windows
   b. For each window:
      - xreach/twitter-cli search "<keyword>" --since <start> --until <end> --limit 50 --format json
      - For each tweet returned:
          * if tweet_id in local seen_set → skip
          * add tweet_id to seen_set
      - Batch remaining tweets:
          * tweet.text ≤ 500 chars → summary = tweet.text
          * tweet.text  > 500 chars → Claude Haiku: "Summarise in one sentence: {text}"
      - Batch embed all summaries (100 per OpenAI call)
      - INSERT INTO tweet_summaries ... ON CONFLICT (tweet_id) DO NOTHING
      - sleep(rate_limit_delay) between windows
3. Write scheduler_run_log:
   job_name='twitter-update', status='success'/'error',
   records_written=<new rows inserted>,
   meta_json={keywords_processed, windows_run, skipped_duplicates}
```

**Rate limit strategy:** 4 × 6h windows per keyword keeps each xreach call to ≤50 tweets. Window-to-window sleep is configurable via `TWITTER_WINDOW_SLEEP_SECONDS` env var (default: 30s).

---

## `twitter_prep.py` Logic

```
Inputs: DATABASE_URL

1. For each keyword in tweet_keywords:
   UPDATE tweet_keywords
   SET mention_count = (SELECT COUNT(*) FROM tweet_summaries WHERE keyword = k.keyword),
       last_refreshed_at = NOW()
   WHERE id = k.id

2. DELETE FROM tweet_summaries
   WHERE tweet_date < NOW() - (RETENTION_DAYS || ' days')::INTERVAL
   -- RETENTION_DAYS from env var TWITTER_RETENTION_DAYS, default 90

3. Print summary: keywords refreshed, rows deleted
```

No `scheduler_run_log` write (runs locally/manually, not a scheduler job).

---

## GitHub Actions Workflows

**`twitter-scrape.yml`** (daily):
```yaml
on:
  schedule:
    - cron: '0 2 * * *'
  workflow_dispatch:

jobs:
  scrape:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.13' }
      - run: pip install -r scripts/requirements-twitter.txt
      - run: python scripts/twitter_update.py
        env:
          DATABASE_URL:       ${{ secrets.DATABASE_URL }}
          ANTHROPIC_API_KEY:  ${{ secrets.ANTHROPIC_API_KEY }}
          OPENAI_API_KEY:       ${{ secrets.OPENAI_API_KEY }}
          TWITTER_BEARER_TOKEN: ${{ secrets.TWITTER_BEARER_TOKEN }}
          TWITTER_COOKIE:       ${{ secrets.TWITTER_COOKIE }}
```

**`twitter-prep.yml`** (monthly):
```yaml
on:
  schedule:
    - cron: '0 3 1 * *'
  workflow_dispatch:
```

---

## `sentiment_service.py` (FastAPI retrieval)

```python
async def get_tweet_context(query: str, days: int = 30, limit: int = 10) -> list[str]:
    """Return semantically relevant tweet summaries for LLM context injection."""
    query_vec = await embed(query)       # reuse OpenAI embed helper
    rows = await db.fetch("""
        SELECT summary FROM tweet_summaries
        WHERE tweet_date >= NOW() - ($1 || ' days')::INTERVAL
        ORDER BY embedding <-> $2
        LIMIT $3
    """, days, query_vec, limit)
    return [r["summary"] for r in rows]
```

Pro Deep Analysis prompt injection:
```
Relevant recent social context (X/Twitter):
{chr(10).join(f"- {s}" for s in summaries)}
```

---

## New Files

| File | Purpose |
|------|---------|
| `scripts/twitter_update.py` | Daily crawl + embed + upsert |
| `scripts/twitter_prep.py` | Monthly stats refresh + retention prune |
| `scripts/requirements-twitter.txt` | xreach, anthropic, openai, psycopg2, pgvector |
| `.github/workflows/twitter-scrape.yml` | Daily Actions workflow |
| `.github/workflows/twitter-prep.yml` | Monthly Actions workflow |
| `backend/app/services/sentiment_service.py` | Semantic retrieval for LLM context |
| `alembic/versions/<hash>_add_tweet_tables.py` | Migration: tweet_keywords + tweet_summaries + pgvector |

---

## Required Secrets (GitHub Actions + Railway)

| Secret | Used by |
|--------|---------|
| `DATABASE_URL` | already exists |
| `ANTHROPIC_API_KEY` | already exists |
| `OPENAI_API_KEY` | new — for embeddings |
| `TWITTER_BEARER_TOKEN` | new — xreach/twitter-cli Bearer Token (browser-extracted) |
| `TWITTER_COOKIE` | new — xreach/twitter-cli Cookie string (browser-extracted, expires ~30 days) |

---

## Env Vars (configurable)

| Var | Default | Purpose |
|-----|---------|---------|
| `TWITTER_WINDOW_SLEEP_SECONDS` | `30` | Delay between time-window requests |
| `TWITTER_RETENTION_DAYS` | `90` | Rolling retention window |
| `TWITTER_SUMMARY_THRESHOLD` | `500` | Char count above which Haiku summarises |
| `TWITTER_EMBED_BATCH_SIZE` | `100` | OpenAI embed batch size |

---

## Open Questions (pre-implementation)

1. **Initial keyword seed list** (confirmed: price-focused, broad):

| keyword | game |
|---------|------|
| `pokemon tcg price` | pokemon |
| `pokemon card price` | pokemon |
| `yugioh price` | ygo |
| `one piece tcg price` | optcg |
| `tcg price spike` | NULL (cross-game) |
| `pokemon new set` | pokemon |
| `yugioh new set` | ygo |
| `one piece tcg new set` | optcg |
| `pokemon tcg event` | pokemon |
| `yugioh event` | ygo |
| `tcg reprint` | NULL (cross-game) |

**Note — Cookie rotation:** Browser-extracted cookies typically expire in ~30 days. `twitter_update.py` must detect HTTP 401/403 responses and emit a `status='error'` run log with `error_message='TWITTER_COOKIE expired — rotate secret'` rather than silently writing zero rows.

---

## Out of Scope

- Per-card mention tracking (Phase 4 extension, not this pipeline)
- Reddit / YouTube scraping (separate pipelines per roadmap)
- Displaying raw mention counts on frontend (Phase 4 UI work)
- Real-time streaming (daily batch is sufficient for LLM context)
