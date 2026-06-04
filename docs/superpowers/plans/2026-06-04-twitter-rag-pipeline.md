# Twitter/X RAG Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a daily GitHub Actions pipeline that scrapes X/Twitter for TCG price/event keywords, summarises tweets with Claude Haiku, embeds summaries into pgvector on Railway Postgres, and exposes a semantic retrieval function for Pro Deep Analysis LLM context injection.

**Architecture:** Standalone Python scripts (`twitter_update.py` daily, `twitter_prep.py` monthly) connect directly to Railway Postgres via `DATABASE_URL`. The scripts call X's GraphQL SearchTimeline API directly in Python, mirroring the xreach TypeScript library pattern exactly. SQLAlchemy models on the backend side expose a `sentiment_service.get_tweet_context()` function for FastAPI.

**Tech Stack:** Python 3.13, httpx, psycopg (direct DB writes from scripts), openai (embeddings), anthropic (Haiku summarisation), pgvector extension, SQLAlchemy 2 + pgvector (backend), GitHub Actions.

**Key xreach implementation note:** xreach is a TypeScript library, not a CLI. We re-implement its `graphql()` + `SearchMixin.search()` methods in Python. Bearer token is Twitter's public hardcoded value — never a secret. User-specific secrets are `auth_token` (40-char hex) and `ct0` (160-char hex CSRF token). SearchTimeline uses POST (not GET) — only endpoint that does. Time sharding is cursor-based pagination (4 pages × 50 results per keyword), not time-window sharding (`since:`/`until:` are date-only in the free GraphQL API).

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `migrations/versions/0038_add_tweet_tables.py` | Create | pgvector extension + tweet_keywords + tweet_summaries tables + indexes |
| `migrations/versions/0039_seed_tweet_keywords.py` | Create | Insert 11 initial keywords |
| `backend/app/models/tweet_keyword.py` | Create | SQLAlchemy model for tweet_keywords |
| `backend/app/models/tweet_summary.py` | Create | SQLAlchemy model for tweet_summaries |
| `backend/app/models/__init__.py` | Modify | Export TweetKeyword, TweetSummary |
| `scripts/requirements-twitter.txt` | Create | httpx, anthropic, openai, psycopg[binary], pgvector |
| `scripts/twitter_update.py` | Create | Daily X scraper + embed + upsert + scheduler_run_log |
| `scripts/twitter_prep.py` | Create | Monthly keyword stats refresh + 90-day retention prune |
| `.github/workflows/twitter-scrape.yml` | Create | Daily GitHub Actions workflow (02:00 UTC) |
| `.github/workflows/twitter-prep.yml` | Create | Monthly GitHub Actions workflow (03:00 UTC, 1st of month) |
| `backend/app/services/sentiment_service.py` | Create | Semantic retrieval for Pro Deep Analysis context |

---

## Task 1: Alembic migration — pgvector + tweet tables

**Files:**
- Create: `migrations/versions/0038_add_tweet_tables.py`

- [ ] **Step 1: Write the migration**

```python
"""Add tweet_keywords and tweet_summaries tables for Twitter RAG pipeline."""

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "tweet_keywords",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("keyword", sa.Text, nullable=False),
        sa.Column("game", sa.Text, nullable=True),
        sa.Column("active", sa.Boolean, server_default="true", nullable=False),
        sa.Column("mention_count", sa.Integer, server_default="0", nullable=False),
        sa.Column("last_refreshed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "tweet_summaries",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tweet_id", sa.Text, nullable=False),
        sa.Column("keyword", sa.Text, nullable=False),
        sa.Column("tweet_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("embedding", sa.Text, nullable=True),   # stored via raw SQL; see note
        sa.Column("captured_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_unique_constraint("uq_tweet_summaries_tweet_id", "tweet_summaries", ["tweet_id"])
    op.create_index("ix_tweet_summaries_tweet_date", "tweet_summaries", ["tweet_date"])
    op.create_index("ix_tweet_summaries_keyword", "tweet_summaries", ["keyword"])

    # Add vector column and ivfflat index via raw SQL (pgvector not in SA type system)
    op.execute("ALTER TABLE tweet_summaries ADD COLUMN IF NOT EXISTS embedding vector(1536)")
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_tweet_summaries_embedding
        ON tweet_summaries USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
    """)


def downgrade() -> None:
    op.drop_table("tweet_summaries")
    op.drop_table("tweet_keywords")
```

- [ ] **Step 2: Run migration locally to verify**

```bash
alembic upgrade head
```

Expected: `Running upgrade 0037 -> 0038, Add tweet_keywords and tweet_summaries tables`

- [ ] **Step 3: Confirm tables exist**

```bash
railway run psql $DATABASE_URL -c "\dt tweet_*"
```

Expected: two rows — `tweet_keywords`, `tweet_summaries`

- [ ] **Step 4: Commit**

```bash
git add migrations/versions/0038_add_tweet_tables.py
git commit -m "feat(migration): add tweet_keywords + tweet_summaries tables (pgvector)"
```

---

## Task 2: Seed migration — initial 11 keywords

**Files:**
- Create: `migrations/versions/0039_seed_tweet_keywords.py`

- [ ] **Step 1: Write the seed migration**

```python
"""Seed initial tweet_keywords: 11 TCG price/event keywords."""

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None

from alembic import op


KEYWORDS = [
    ("pokemon tcg price",       "pokemon"),
    ("pokemon card price",      "pokemon"),
    ("yugioh price",            "ygo"),
    ("one piece tcg price",     "optcg"),
    ("tcg price spike",         None),
    ("pokemon new set",         "pokemon"),
    ("yugioh new set",          "ygo"),
    ("one piece tcg new set",   "optcg"),
    ("pokemon tcg event",       "pokemon"),
    ("yugioh event",            "ygo"),
    ("tcg reprint",             None),
]


def upgrade() -> None:
    for keyword, game in KEYWORDS:
        op.execute(
            f"INSERT INTO tweet_keywords (keyword, game) "
            f"VALUES ('{keyword}', {'NULL' if game is None else repr(game)}) "
            f"ON CONFLICT DO NOTHING"
        )


def downgrade() -> None:
    for keyword, _ in KEYWORDS:
        op.execute(f"DELETE FROM tweet_keywords WHERE keyword = '{keyword}'")
```

- [ ] **Step 2: Run migration**

```bash
alembic upgrade head
```

Expected: `Running upgrade 0038 -> 0039`

- [ ] **Step 3: Verify seed**

```bash
railway run psql $DATABASE_URL -c "SELECT keyword, game FROM tweet_keywords ORDER BY id"
```

Expected: 11 rows matching the keyword list above

- [ ] **Step 4: Commit**

```bash
git add migrations/versions/0039_seed_tweet_keywords.py
git commit -m "feat(migration): seed 11 initial tweet_keywords"
```

---

## Task 3: SQLAlchemy models

**Files:**
- Create: `backend/app/models/tweet_keyword.py`
- Create: `backend/app/models/tweet_summary.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Add pgvector and openai to `requirements.txt`**

Open `requirements.txt`. Add these two lines at the end:

```
pgvector==0.3.6
openai==1.82.0
```

Then verify the backend still imports cleanly:

```bash
pip install pgvector==0.3.6 openai==1.82.0
python -c "from pgvector.sqlalchemy import Vector; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Write TweetKeyword model**

```python
# backend/app/models/tweet_keyword.py
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class TweetKeyword(Base):
    __tablename__ = "tweet_keywords"

    id:               Mapped[int]            = mapped_column(Integer, primary_key=True, autoincrement=True)
    keyword:          Mapped[str]            = mapped_column(Text, nullable=False)
    game:             Mapped[str | None]     = mapped_column(Text, nullable=True)
    active:           Mapped[bool]           = mapped_column(Boolean, nullable=False, default=True)
    mention_count:    Mapped[int]            = mapped_column(Integer, nullable=False, default=0)
    last_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at:       Mapped[datetime]       = mapped_column(DateTime(timezone=True), nullable=False)
```

- [ ] **Step 4: Write TweetSummary model**

```python
# backend/app/models/tweet_summary.py
from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Index, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class TweetSummary(Base):
    __tablename__ = "tweet_summaries"
    __table_args__ = (
        UniqueConstraint("tweet_id", name="uq_tweet_summaries_tweet_id"),
        Index("ix_tweet_summaries_tweet_date", "tweet_date"),
        Index("ix_tweet_summaries_keyword", "keyword"),
    )

    id:          Mapped[int]            = mapped_column(Integer, primary_key=True, autoincrement=True)
    tweet_id:    Mapped[str]            = mapped_column(Text, nullable=False)
    keyword:     Mapped[str]            = mapped_column(Text, nullable=False)
    tweet_date:  Mapped[datetime]       = mapped_column(DateTime(timezone=True), nullable=False)
    summary:     Mapped[str]            = mapped_column(Text, nullable=False)
    embedding:   Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    captured_at: Mapped[datetime]       = mapped_column(DateTime(timezone=True), nullable=False)
```

- [ ] **Step 5: Add to `__init__.py`**

Open `backend/app/models/__init__.py`. Add these two lines after the existing imports:

```python
from backend.app.models.tweet_keyword import TweetKeyword
from backend.app.models.tweet_summary import TweetSummary
```

And add `"TweetKeyword"`, `"TweetSummary"` to the `__all__` list.

- [ ] **Step 6: Verify imports work**

```bash
python -c "from backend.app.models import TweetKeyword, TweetSummary; print('ok')"
```

Expected: `ok`

- [ ] **Step 7: Commit**

```bash
git add requirements.txt backend/app/models/tweet_keyword.py backend/app/models/tweet_summary.py backend/app/models/__init__.py
git commit -m "feat(models): add TweetKeyword + TweetSummary models; add pgvector + openai to requirements"
```

---

## Task 4: `scripts/requirements-twitter.txt`

**Files:**
- Create: `scripts/requirements-twitter.txt`

- [ ] **Step 1: Write requirements file**

```
httpx==0.28.1
anthropic==0.52.0
openai==1.82.0
psycopg[binary]==3.2.9
pgvector==0.3.6
```

- [ ] **Step 2: Verify install succeeds**

```bash
pip install -r scripts/requirements-twitter.txt
```

Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add scripts/requirements-twitter.txt
git commit -m "feat(scripts): add requirements-twitter.txt"
```

---

## Task 5: `scripts/twitter_update.py` — core daily scraper

**Files:**
- Create: `scripts/twitter_update.py`

This is the heaviest task. The script mirrors xreach's `BaseClient.graphql()` + `SearchMixin.search()` in Python.

- [ ] **Step 1: Write the script**

```python
#!/usr/bin/env python3
"""
Daily Twitter/X scraper for TCG keywords.
Mirrors xreach TypeScript library patterns — do not restructure HTTP calls.

Required env vars:
  DATABASE_URL          Railway Postgres (already a GitHub secret)
  ANTHROPIC_API_KEY     For Claude Haiku tweet summarisation
  OPENAI_API_KEY        For text-embedding-3-small embeddings
  TWITTER_AUTH_TOKEN    auth_token cookie (40-char hex)
  TWITTER_CT0           ct0 CSRF token (160-char hex)

Optional env vars:
  TWITTER_WINDOW_SLEEP_SECONDS   Seconds between paginated requests (default: 30)
  TWITTER_SUMMARY_THRESHOLD      Char count above which Haiku summarises (default: 500)
  TWITTER_EMBED_BATCH_SIZE       OpenAI embed batch size (default: 100)
  DRY_RUN                        Set to 1 to skip DB writes
"""
from __future__ import annotations

import base64
import json
import logging
import os
import random
import string
import struct
import time
from datetime import UTC, date, datetime, timedelta

import httpx
import psycopg
from anthropic import Anthropic
from openai import OpenAI

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

DATABASE_URL     = os.environ["DATABASE_URL"]
ANTHROPIC_KEY    = os.environ["ANTHROPIC_API_KEY"]
OPENAI_KEY       = os.environ["OPENAI_API_KEY"]
AUTH_TOKEN       = os.environ["TWITTER_AUTH_TOKEN"]
CT0              = os.environ["TWITTER_CT0"]

WINDOW_SLEEP     = int(os.environ.get("TWITTER_WINDOW_SLEEP_SECONDS", "30"))
SUMMARY_THRESHOLD = int(os.environ.get("TWITTER_SUMMARY_THRESHOLD", "500"))
EMBED_BATCH_SIZE = int(os.environ.get("TWITTER_EMBED_BATCH_SIZE", "100"))
DRY_RUN          = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")

# ── xreach constants (mirror base.ts exactly) ─────────────────────────────────

# Twitter's public Bearer Token — hardcoded in xreach, same for all users
_BEARER_TOKEN = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs"
    "%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)

# Fallback QueryID for SearchTimeline (from xreach query-ids/index.ts)
_SEARCH_QUERY_ID = "6AAys3t42mosm_yTI_QENg"

# defaultFeatures from xreach base.ts — copy verbatim, do not edit
_DEFAULT_FEATURES: dict[str, bool] = {
    "rweb_tipjar_consumption_enabled": True,
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "communities_web_enable_tweet_community_results_fetch": True,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "articles_preview_enabled": True,
    "tweetypie_unmention_optimization_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "tweet_awards_web_tipping_enabled": False,
    "creator_subscriptions_quote_tweet_preview_enabled": False,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "rweb_video_timestamps_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": True,
    "responsive_web_enhance_cards_enabled": False,
    "responsive_web_twitter_article_notes_tab_enabled": True,
    "subscriptions_verification_info_verified_since_enabled": True,
    "subscriptions_verification_info_is_identity_verified_enabled": True,
    "highlights_tweets_tab_ui_enabled": True,
    "profile_label_improvements_pcf_label_in_post_enabled": True,
    "hidden_profile_subscriptions_enabled": True,
    "subscriptions_feature_can_gift_premium": True,
    "responsive_web_grok_show_grok_translated_post": True,
    "responsive_web_grok_analyze_post_followups_enabled": True,
    "premium_content_api_read_enabled": True,
    "responsive_web_grok_image_annotation_enabled": True,
    "responsive_web_grok_share_attachment_enabled": True,
    "responsive_web_grok_analysis_button_from_backend": True,
    "responsive_web_grok_analyze_button_fetch_trends_enabled": True,
    "rweb_video_screen_enabled": True,
    "responsive_web_jetfuel_frame": True,
}

# ── xreach: generateTransactionId() (mirror anti-detect/transaction.ts) ───────

def _generate_transaction_id() -> str:
    now_ms = int(time.time() * 1000)
    buf = struct.pack(">Q", now_ms)
    timestamp = base64.urlsafe_b64encode(buf).rstrip(b"=").decode()
    chars = string.ascii_letters + string.digits + "+/"
    return timestamp + "".join(random.choices(chars, k=24))

# ── xreach: getHeaders() (mirror base.ts) ────────────────────────────────────

def _headers() -> dict[str, str]:
    return {
        "authorization": f"Bearer {_BEARER_TOKEN}",
        "x-twitter-auth-type": "OAuth2Session",
        "x-twitter-active-user": "yes",
        "x-csrf-token": CT0,
        "cookie": f"auth_token={AUTH_TOKEN}; ct0={CT0}",
        "content-type": "application/json",
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "x-twitter-client-language": "en",
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "x-client-transaction-id": _generate_transaction_id(),
    }

# ── xreach: SearchMixin.search() → POST SearchTimeline ───────────────────────

def _search_page(
    query: str,
    count: int = 50,
    cursor: str | None = None,
) -> tuple[list[dict], str | None]:
    """
    Mirror SearchMixin.search() from xreach search.ts.
    Returns (tweets, next_cursor). Raises httpx.HTTPStatusError on 4xx.
    """
    url = f"https://x.com/i/api/graphql/{_SEARCH_QUERY_ID}/SearchTimeline"
    variables: dict = {
        "rawQuery": query,
        "count": count,
        "querySource": "typed_query",
        "product": "Latest",
    }
    if cursor:
        variables["cursor"] = cursor

    # SearchTimeline: variables in URL params, features in POST body
    resp = httpx.post(
        url,
        params={"variables": json.dumps(variables)},
        json={"features": _DEFAULT_FEATURES, "queryId": _SEARCH_QUERY_ID},
        headers=_headers(),
        timeout=30,
    )
    resp.raise_for_status()

    data = resp.json()
    instructions = (
        data.get("data", {})
        .get("search_by_raw_query", {})
        .get("search_timeline", {})
        .get("timeline", {})
        .get("instructions", [])
    )
    entries = next(
        (i["entries"] for i in instructions if i.get("type") == "TimelineAddEntries"),
        [],
    )

    tweets: list[dict] = []
    next_cursor: str | None = None

    for entry in entries:
        result = (
            entry.get("content", {})
            .get("itemContent", {})
            .get("tweet_results", {})
            .get("result")
        )
        if result:
            tweet = _parse_tweet(result)
            if tweet:
                tweets.append(tweet)
        if entry.get("content", {}).get("cursorType") == "Bottom":
            next_cursor = entry["content"].get("value")

    return tweets, next_cursor


def _parse_tweet(result: dict) -> dict | None:
    """Mirror parseTweetFromSearch() from xreach search.ts."""
    if result.get("__typename") == "TweetTombstone":
        return None
    tweet_data = result.get("tweet") or result
    legacy = tweet_data.get("legacy", {})
    text = legacy.get("full_text", "")   # ⚠️ full_text, not text
    if not text:
        return None
    return {
        "id": tweet_data.get("rest_id"),
        "text": text,
        "created_at": legacy.get("created_at"),
        "lang": legacy.get("lang"),
    }

# ── Summarisation ─────────────────────────────────────────────────────────────

def _summarise(texts: list[str], client: Anthropic) -> list[str]:
    """Summarise long tweets with Claude Haiku; pass short ones through unchanged."""
    results = []
    for text in texts:
        if len(text) <= SUMMARY_THRESHOLD:
            results.append(text)
        else:
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=100,
                messages=[{"role": "user", "content": f"Summarise in one sentence: {text}"}],
            )
            results.append(msg.content[0].text.strip())
    return results

# ── Embedding ─────────────────────────────────────────────────────────────────

def _embed_batch(texts: list[str], client: OpenAI) -> list[list[float]]:
    """Batch embed up to EMBED_BATCH_SIZE texts with text-embedding-3-small."""
    all_vectors: list[list[float]] = []
    for i in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[i : i + EMBED_BATCH_SIZE]
        resp = client.embeddings.create(model="text-embedding-3-small", input=batch)
        all_vectors.extend([item.embedding for item in resp.data])
    return all_vectors

# ── DB helpers ────────────────────────────────────────────────────────────────

def _get_db_url() -> str:
    url = DATABASE_URL
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url[len("postgresql+psycopg://"):]
    return url


def _load_keywords(conn: psycopg.Connection) -> list[tuple[int, str]]:
    with conn.cursor() as cur:
        cur.execute("SELECT id, keyword FROM tweet_keywords WHERE active = TRUE ORDER BY id")
        return cur.fetchall()


def _existing_ids(conn: psycopg.Connection) -> set[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT tweet_id FROM tweet_summaries")
        return {row[0] for row in cur.fetchall()}


def _upsert_summaries(
    conn: psycopg.Connection,
    rows: list[tuple],  # (tweet_id, keyword, tweet_date, summary, embedding_str)
) -> int:
    if DRY_RUN or not rows:
        return 0
    with conn.cursor() as cur:
        inserted = 0
        for tweet_id, keyword, tweet_date, summary, embedding_str in rows:
            cur.execute(
                """
                INSERT INTO tweet_summaries (tweet_id, keyword, tweet_date, summary, embedding)
                VALUES (%s, %s, %s, %s, %s::vector)
                ON CONFLICT (tweet_id) DO NOTHING
                """,
                (tweet_id, keyword, tweet_date, summary, embedding_str),
            )
            inserted += cur.rowcount
    conn.commit()
    return inserted


def _write_run_log(
    conn: psycopg.Connection,
    *,
    status: str,
    records_written: int,
    errors: int,
    error_message: str | None,
    meta: dict,
    started_at: datetime,
) -> None:
    if DRY_RUN:
        return
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO scheduler_run_log
                (job_name, started_at, finished_at, status, records_written, errors, error_message, meta_json)
            VALUES
                ('twitter-update', %s, NOW(), %s, %s, %s, %s, %s)
            """,
            (
                started_at,
                status,
                records_written,
                errors,
                error_message,
                json.dumps(meta),
            ),
        )
    conn.commit()

# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    started_at = datetime.now(UTC)
    anthropic_client = Anthropic(api_key=ANTHROPIC_KEY)
    openai_client = OpenAI(api_key=OPENAI_KEY)

    yesterday = (date.today() - timedelta(days=1)).isoformat()
    today = date.today().isoformat()

    total_written = 0
    total_errors = 0
    keywords_processed = 0

    with psycopg.connect(_get_db_url()) as conn:
        try:
            keywords = _load_keywords(conn)
            existing = _existing_ids(conn)
            log.info("Loaded %d active keywords, %d existing tweet_ids", len(keywords), len(existing))

            for _kw_id, keyword in keywords:
                kw_query = f"{keyword} lang:en since:{yesterday} until:{today}"
                log.info("Keyword: %s", keyword)

                new_tweets: list[dict] = []
                cursor: str | None = None

                # Paginate up to 4 pages (max ~200 tweets per keyword)
                for page in range(4):
                    try:
                        tweets, cursor = _search_page(kw_query, count=50, cursor=cursor)
                    except httpx.HTTPStatusError as exc:
                        if exc.response.status_code in (401, 403):
                            _write_run_log(
                                conn,
                                status="error",
                                records_written=total_written,
                                errors=total_errors + 1,
                                error_message="TWITTER_CT0 expired — rotate GitHub secret",
                                meta={"keywords_processed": keywords_processed},
                                started_at=started_at,
                            )
                            log.error("Auth error %s — aborting", exc.response.status_code)
                            return 1
                        log.warning("HTTP %s on page %d for '%s'", exc.response.status_code, page, keyword)
                        total_errors += 1
                        break

                    for tweet in tweets:
                        if tweet["id"] and tweet["id"] not in existing:
                            new_tweets.append(tweet)
                            existing.add(tweet["id"])

                    if not cursor or not tweets:
                        break
                    time.sleep(WINDOW_SLEEP)

                if not new_tweets:
                    keywords_processed += 1
                    continue

                # Summarise
                summaries = _summarise([t["text"] for t in new_tweets], anthropic_client)

                # Embed
                vectors = _embed_batch(summaries, openai_client)

                # Build rows
                rows = []
                for tweet, summary, vector in zip(new_tweets, summaries, vectors):
                    tweet_date = None
                    if tweet.get("created_at"):
                        try:
                            tweet_date = datetime.strptime(
                                tweet["created_at"], "%a %b %d %H:%M:%S +0000 %Y"
                            ).replace(tzinfo=UTC)
                        except ValueError:
                            tweet_date = datetime.now(UTC)
                    else:
                        tweet_date = datetime.now(UTC)

                    # Serialize vector as Postgres array string
                    embedding_str = "[" + ",".join(str(v) for v in vector) + "]"
                    rows.append((tweet["id"], keyword, tweet_date, summary, embedding_str))

                written = _upsert_summaries(conn, rows)
                total_written += written
                keywords_processed += 1
                log.info("  +%d new rows (keyword='%s')", written, keyword)

            _write_run_log(
                conn,
                status="success",
                records_written=total_written,
                errors=total_errors,
                error_message=None,
                meta={
                    "keywords_processed": keywords_processed,
                    "date_range": f"{yesterday}/{today}",
                    "dry_run": DRY_RUN,
                },
                started_at=started_at,
            )
            log.info("Done. Written=%d errors=%d", total_written, total_errors)
            return 0

        except Exception as exc:
            log.exception("Fatal error")
            try:
                _write_run_log(
                    conn,
                    status="error",
                    records_written=total_written,
                    errors=total_errors + 1,
                    error_message=str(exc)[:500],
                    meta={"keywords_processed": keywords_processed},
                    started_at=started_at,
                )
            except Exception:
                pass
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Smoke test with DRY_RUN (requires valid credentials)**

```bash
DRY_RUN=1 python scripts/twitter_update.py
```

Expected: log lines showing keywords loaded, search pages attempted, no DB writes.

- [ ] **Step 3: Commit**

```bash
git add scripts/twitter_update.py
git commit -m "feat(scripts): add twitter_update.py — daily X scraper with xreach HTTP pattern"
```

---

## Task 6: `scripts/twitter_prep.py` — monthly maintenance

**Files:**
- Create: `scripts/twitter_prep.py`

- [ ] **Step 1: Write the script**

```python
#!/usr/bin/env python3
"""
Monthly Twitter knowledge base maintenance.
  1. Refresh mention_count + last_refreshed_at on tweet_keywords
  2. DELETE tweet_summaries older than TWITTER_RETENTION_DAYS (default 90)

Required env vars:
  DATABASE_URL

Optional:
  TWITTER_RETENTION_DAYS   (default: 90)
"""
from __future__ import annotations

import logging
import os

import psycopg

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATABASE_URL    = os.environ["DATABASE_URL"]
RETENTION_DAYS  = int(os.environ.get("TWITTER_RETENTION_DAYS", "90"))


def _get_db_url() -> str:
    url = DATABASE_URL
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url[len("postgresql+psycopg://"):]
    return url


def main() -> int:
    with psycopg.connect(_get_db_url()) as conn:
        with conn.cursor() as cur:
            # 1. Refresh keyword mention counts
            cur.execute("""
                UPDATE tweet_keywords k
                SET mention_count = (
                    SELECT COUNT(*) FROM tweet_summaries s WHERE s.keyword = k.keyword
                ),
                last_refreshed_at = NOW()
            """)
            refreshed = cur.rowcount
            log.info("Refreshed mention_count on %d keywords", refreshed)

            # 2. Prune old summaries
            cur.execute(
                "DELETE FROM tweet_summaries "
                "WHERE tweet_date < NOW() - (%s || ' days')::INTERVAL",
                (str(RETENTION_DAYS),),
            )
            deleted = cur.rowcount
            log.info("Pruned %d summaries older than %d days", deleted, RETENTION_DAYS)

        conn.commit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Test locally (read-only check)**

```bash
python -c "
import psycopg, os
with psycopg.connect(os.environ['DATABASE_URL'].replace('postgresql+psycopg://', 'postgresql://')) as conn:
    with conn.cursor() as cur:
        cur.execute('SELECT COUNT(*) FROM tweet_keywords')
        print('keywords:', cur.fetchone())
        cur.execute('SELECT COUNT(*) FROM tweet_summaries')
        print('summaries:', cur.fetchone())
"
```

Expected: counts match what was seeded in Tasks 1–2.

- [ ] **Step 3: Commit**

```bash
git add scripts/twitter_prep.py
git commit -m "feat(scripts): add twitter_prep.py — monthly keyword stats + retention prune"
```

---

## Task 7: GitHub Actions workflows

**Files:**
- Create: `.github/workflows/twitter-scrape.yml`
- Create: `.github/workflows/twitter-prep.yml`

- [ ] **Step 1: Write daily scrape workflow**

```yaml
# .github/workflows/twitter-scrape.yml
name: Twitter TCG Keyword Scraper

on:
  schedule:
    - cron: '0 2 * * *'   # 02:00 UTC daily — yesterday's data is complete
  workflow_dispatch:
    inputs:
      dry_run:
        description: 'Dry run (no DB writes)'
        type: boolean
        default: false

env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true

jobs:
  scrape:
    runs-on: ubuntu-latest
    timeout-minutes: 30

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.13'

      - name: Install dependencies
        run: pip install -r scripts/requirements-twitter.txt

      - name: Run Twitter scraper
        env:
          DATABASE_URL:        ${{ secrets.DATABASE_URL }}
          ANTHROPIC_API_KEY:   ${{ secrets.ANTHROPIC_API_KEY }}
          OPENAI_API_KEY:      ${{ secrets.OPENAI_API_KEY }}
          TWITTER_AUTH_TOKEN:  ${{ secrets.TWITTER_AUTH_TOKEN }}
          TWITTER_CT0:         ${{ secrets.TWITTER_CT0 }}
          DRY_RUN:             ${{ github.event.inputs.dry_run || 'false' }}
        run: python scripts/twitter_update.py
```

- [ ] **Step 2: Write monthly prep workflow**

```yaml
# .github/workflows/twitter-prep.yml
name: Twitter Knowledge Base Maintenance

on:
  schedule:
    - cron: '0 3 1 * *'   # 03:00 UTC on 1st of each month
  workflow_dispatch:

env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true

jobs:
  prep:
    runs-on: ubuntu-latest
    timeout-minutes: 10

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.13'

      - name: Install dependencies
        run: pip install psycopg[binary]

      - name: Run prep
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
        run: python scripts/twitter_prep.py
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/twitter-scrape.yml .github/workflows/twitter-prep.yml
git commit -m "feat(ci): add twitter-scrape and twitter-prep GitHub Actions workflows"
```

- [ ] **Step 4: Add GitHub secrets (operator action)**

In GitHub repo → Settings → Secrets and variables → Actions, add:
- `OPENAI_API_KEY` — OpenAI API key
- `TWITTER_AUTH_TOKEN` — `auth_token` cookie value from a logged-in X session
- `TWITTER_CT0` — `ct0` cookie value from the same X session

`DATABASE_URL` and `ANTHROPIC_API_KEY` already exist.

- [ ] **Step 5: Trigger dry run to validate workflow**

```bash
gh workflow run twitter-scrape.yml -f dry_run=true
```

Then check:

```bash
gh run list --workflow twitter-scrape.yml --limit 3
```

Expected: most recent run shows `completed` / `success`.

---

## Task 8: `backend/app/services/sentiment_service.py`

**Files:**
- Create: `backend/app/services/sentiment_service.py`

- [ ] **Step 1: Write the service**

```python
# backend/app/services/sentiment_service.py
"""Semantic retrieval of tweet summaries for Pro Deep Analysis context injection."""
from __future__ import annotations

import os

from openai import OpenAI
from sqlalchemy import text
from sqlalchemy.orm import Session

_openai = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))


def _embed(query: str) -> list[float]:
    resp = _openai.embeddings.create(model="text-embedding-3-small", input=[query])
    return resp.data[0].embedding


def get_tweet_context(
    db: Session,
    query: str,
    days: int = 30,
    limit: int = 10,
) -> list[str]:
    """
    Return up to `limit` tweet summaries semantically closest to `query`
    within the last `days` days. Returns [] if tweet_summaries is empty.
    """
    query_vec = _embed(query)
    embedding_str = "[" + ",".join(str(v) for v in query_vec) + "]"

    rows = db.execute(
        text("""
            SELECT summary FROM tweet_summaries
            WHERE tweet_date >= NOW() - (:days || ' days')::INTERVAL
              AND embedding IS NOT NULL
            ORDER BY embedding <-> CAST(:vec AS vector)
            LIMIT :limit
        """),
        {"days": str(days), "vec": embedding_str, "limit": limit},
    ).fetchall()

    return [r[0] for r in rows]


def format_for_prompt(summaries: list[str]) -> str:
    """Format summaries as a bulleted block for LLM prompt injection."""
    if not summaries:
        return ""
    lines = "\n".join(f"- {s}" for s in summaries)
    return f"Relevant recent social context (X/Twitter):\n{lines}"
```

- [ ] **Step 2: Write a unit test**

Create `tests/services/test_sentiment_service.py`:

```python
from unittest.mock import MagicMock, patch

from backend.app.services.sentiment_service import format_for_prompt, get_tweet_context


def test_format_for_prompt_empty():
    assert format_for_prompt([]) == ""


def test_format_for_prompt_nonempty():
    result = format_for_prompt(["price spike on Charizard", "new set announced"])
    assert result.startswith("Relevant recent social context")
    assert "- price spike on Charizard" in result
    assert "- new set announced" in result


def test_get_tweet_context_empty_table():
    mock_db = MagicMock()
    mock_db.execute.return_value.fetchall.return_value = []

    with patch("backend.app.services.sentiment_service._embed", return_value=[0.1] * 1536):
        result = get_tweet_context(mock_db, "Charizard price", days=30, limit=10)

    assert result == []
```

- [ ] **Step 3: Run the test**

```bash
pytest tests/services/test_sentiment_service.py -v
```

Expected: 3 tests pass.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/sentiment_service.py tests/services/test_sentiment_service.py
git commit -m "feat(services): add sentiment_service for tweet context retrieval"
```

---

## Post-deploy verification

After first successful `twitter-scrape` Action run:

```bash
railway run psql $DATABASE_URL -c "
SELECT
  job_name, status, records_written, error_message, finished_at
FROM scheduler_run_log
WHERE job_name = 'twitter-update'
ORDER BY started_at DESC
LIMIT 3;
"
```

Expected: `status='success'`, `records_written > 0`.

```bash
railway run psql $DATABASE_URL -c "
SELECT keyword, COUNT(*) as rows
FROM tweet_summaries
GROUP BY keyword
ORDER BY rows DESC;
"
```

Expected: rows across multiple keywords.

**If `status='error'` with `error_message LIKE '%CT0 expired%'`:** rotate `TWITTER_CT0` in GitHub Secrets.

---

## Required GitHub Secrets checklist

| Secret | Status |
|--------|--------|
| `DATABASE_URL` | ✅ exists |
| `ANTHROPIC_API_KEY` | ✅ exists |
| `OPENAI_API_KEY` | ⬜ add |
| `TWITTER_AUTH_TOKEN` | ⬜ add |
| `TWITTER_CT0` | ⬜ add |
