#!/usr/bin/env python3
"""
Daily Reddit scraper for TCG keywords.
No auth required — uses public Reddit JSON API.

Required env vars:
  DATABASE_URL          Railway Postgres (already a GitHub secret)
  ANTHROPIC_API_KEY     For Claude Haiku summarisation
  OPENAI_API_KEY        For text-embedding-3-small embeddings

Optional env vars:
  REDDIT_EMBED_BATCH_SIZE  OpenAI embed batch size (default: 100)
  DRY_RUN                  Set to 1 to skip DB writes
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import UTC, datetime

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

EMBED_BATCH_SIZE = int(os.environ.get("REDDIT_EMBED_BATCH_SIZE", "100"))
DRY_RUN          = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")

_HEADERS = {"User-Agent": "flashcard-planet-bot/1.0"}

# ── Keyword → subreddit mapping ───────────────────────────────────────────────

_GAME_SUBREDDITS: dict[str | None, list[str]] = {
    "pokemon": ["PokemonTCG"],
    "ygo":     ["yugioh"],
    "optcg":   ["OnePieceTCG"],
    None:      ["PokemonTCG", "yugioh"],
}

# ── Reddit scraping ───────────────────────────────────────────────────────────

def _search_reddit(subreddit: str, keyword: str, limit: int = 25) -> list[dict]:
    """
    GET /r/{subreddit}/search.json — returns posts from the past week.
    Returns list of {id, title, selftext, created_utc}.
    """
    url = f"https://www.reddit.com/r/{subreddit}/search.json"
    params = {"q": keyword, "sort": "new", "t": "week", "limit": limit, "restrict_sr": "1"}
    try:
        resp = httpx.get(url, params=params, headers=_HEADERS, timeout=20, follow_redirects=True)
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        log.warning("Reddit HTTP %s for r/%s + '%s'", exc.response.status_code, subreddit, keyword)
        return []
    except httpx.RequestError as exc:
        log.warning("Reddit request error for r/%s + '%s': %s", subreddit, keyword, exc)
        return []

    posts = []
    for child in resp.json().get("data", {}).get("children", []):
        d = child.get("data", {})
        post_id = d.get("id")
        if not post_id:
            continue
        title    = d.get("title", "")
        selftext = d.get("selftext", "")
        created  = d.get("created_utc")
        posts.append({
            "id":         post_id,
            "title":      title,
            "selftext":   selftext,
            "created_utc": created,
        })
    return posts

# ── Summarisation ─────────────────────────────────────────────────────────────

def _summarise(texts: list[str], client: Anthropic) -> list[str]:
    """Summarise every post with Claude Haiku — original text is never stored."""
    results = []
    for text in texts:
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


def _load_keywords(conn: psycopg.Connection) -> list[tuple[int, str, str | None]]:
    with conn.cursor() as cur:
        cur.execute("SELECT id, keyword, game FROM tweet_keywords WHERE active = TRUE ORDER BY id")
        return cur.fetchall()


def _existing_ids(conn: psycopg.Connection) -> set[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT tweet_id FROM tweet_summaries")
        return {row[0] for row in cur.fetchall()}


def _upsert_summaries(
    conn: psycopg.Connection,
    rows: list[tuple],  # (tweet_id, keyword, tweet_date, summary, embedding_str, source)
) -> int:
    if DRY_RUN or not rows:
        return 0
    with conn.cursor() as cur:
        inserted = 0
        for tweet_id, keyword, tweet_date, summary, embedding_str, source in rows:
            cur.execute(
                """
                INSERT INTO tweet_summaries (tweet_id, keyword, tweet_date, summary, embedding, source)
                VALUES (%s, %s, %s, %s, %s::vector, %s)
                ON CONFLICT (tweet_id) DO NOTHING
                """,
                (tweet_id, keyword, tweet_date, summary, embedding_str, source),
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
                ('reddit-update', %s, NOW(), %s, %s, %s, %s, %s)
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

    total_written = 0
    total_errors = 0
    keywords_processed = 0

    with psycopg.connect(_get_db_url()) as conn:
        try:
            keywords = _load_keywords(conn)
            existing = _existing_ids(conn)
            log.info("Loaded %d active keywords, %d existing tweet_ids", len(keywords), len(existing))

            for _kw_id, keyword, game in keywords:
                subreddits = _GAME_SUBREDDITS.get(game, _GAME_SUBREDDITS[None])
                log.info("Keyword: '%s' → subreddits: %s", keyword, subreddits)

                new_posts: list[tuple] = []  # (post_id, title_text, created_utc)

                for subreddit in subreddits:
                    posts = _search_reddit(subreddit, keyword)
                    for post in posts:
                        dedup_id = f"reddit_{post['id']}"
                        if dedup_id in existing:
                            continue
                        title    = post["title"]
                        selftext = post.get("selftext", "")
                        text     = (title + " " + selftext).strip()[:500]
                        new_posts.append((dedup_id, text, post.get("created_utc")))
                        existing.add(dedup_id)
                    # Brief pause between subreddit requests for same keyword
                    time.sleep(1)

                if not new_posts:
                    keywords_processed += 1
                    continue

                texts = [p[1] for p in new_posts]

                summaries = _summarise(texts, anthropic_client)
                vectors   = _embed_batch(summaries, openai_client)

                rows = []
                for (dedup_id, _text, created_utc), summary, vector in zip(new_posts, summaries, vectors):
                    if created_utc:
                        tweet_date = datetime.fromtimestamp(created_utc, tz=UTC)
                    else:
                        tweet_date = datetime.now(UTC)
                    embedding_str = "[" + ",".join(str(v) for v in vector) + "]"
                    rows.append((dedup_id, keyword, tweet_date, summary, embedding_str, "reddit"))

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
