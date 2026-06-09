#!/usr/bin/env python3
"""
Daily Nitter scraper for TCG keywords.
No auth required — scrapes public Nitter instances.

Required env vars:
  DATABASE_URL      Railway Postgres (already a GitHub secret)
  GROQ_API_KEY      For Groq LLM summarisation
  OPENAI_API_KEY    For text-embedding-3-small embeddings

Optional env vars:
  NITTER_EMBED_BATCH_SIZE  OpenAI embed batch size (default: 100)
  DRY_RUN                  Set to 1 to skip DB writes
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import UTC, datetime

import httpx
import psycopg
from bs4 import BeautifulSoup
from groq import Groq
from openai import OpenAI

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

DATABASE_URL = os.environ["DATABASE_URL"]
GROQ_KEY     = os.environ["GROQ_API_KEY"]
OPENAI_KEY   = os.environ["OPENAI_API_KEY"]

EMBED_BATCH_SIZE = int(os.environ.get("NITTER_EMBED_BATCH_SIZE", "100"))
DRY_RUN          = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")

# Tried in order; first that returns valid HTML wins for that keyword.
NITTER_INSTANCES = [
    "nitter.poast.org",
    "nitter.privacyredirect.com",
    "nitter.1d4.us",
    "nitter.net",
    "nitter.kavin.rocks",
]

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

# ── Nitter scraping ───────────────────────────────────────────────────────────

def _parse_tweet_date(title_attr: str) -> datetime:
    """
    Nitter renders date as title="Jan 1, 2024 · 12:00:00 PM UTC" or ISO.
    Fall back to now() on parse failure.
    """
    for fmt in ("%b %d, %Y · %I:%M:%S %p UTC", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(title_attr.strip(), fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return datetime.now(UTC)


def _scrape_nitter(instance: str, keyword: str) -> list[dict] | None:
    """
    Scrape one Nitter instance for `keyword`. Returns list of
    {id, text, tweet_date} or None if the instance is unreachable.
    """
    url = f"https://{instance}/search"
    params = {"q": keyword, "f": "tweets"}
    try:
        resp = httpx.get(url, params=params, headers=_HEADERS, timeout=20, follow_redirects=True)
        resp.raise_for_status()
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        log.debug("Nitter %s failed: %s", instance, exc)
        return None

    soup = BeautifulSoup(resp.text, "lxml")
    items = soup.select(".timeline-item")
    if not items:
        # Instance responded but returned no timeline — treat as failure
        log.debug("Nitter %s returned no .timeline-item elements", instance)
        return None

    tweets: list[dict] = []
    for item in items:
        # Extract tweet ID from the permalink href: /user/status/1234567890#m
        link = item.select_one(".tweet-link")
        if not link:
            continue
        href = link.get("href", "")
        match = re.search(r"/status/(\d+)", href)
        if not match:
            continue
        tweet_id = match.group(1)

        content_el = item.select_one(".tweet-content")
        if not content_el:
            continue
        text = content_el.get_text(separator=" ", strip=True)

        # Date from <span class="tweet-date"><a title="...">
        tweet_date = datetime.now(UTC)
        date_span = item.select_one(".tweet-date a")
        if date_span and date_span.get("title"):
            tweet_date = _parse_tweet_date(date_span["title"])

        tweets.append({"id": tweet_id, "text": text, "tweet_date": tweet_date})

    return tweets


def _fetch_with_fallback(keyword: str) -> list[dict]:
    """Try each Nitter instance in order; return first successful result."""
    for instance in NITTER_INSTANCES:
        result = _scrape_nitter(instance, keyword)
        if result is not None:
            log.info("  Nitter: %s returned %d tweets for '%s'", instance, len(result), keyword)
            return result
        time.sleep(2)
    log.warning("All Nitter instances unreachable for keyword '%s'", keyword)
    return []

# ── Summarisation ─────────────────────────────────────────────────────────────

def _summarise(texts: list[str], client: Groq) -> list[str]:
    """Summarise every tweet with Groq — original text is never stored."""
    results = []
    for text in texts:
        resp = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            max_tokens=100,
            messages=[{"role": "user", "content": f"Summarise in one sentence: {text}"}],
        )
        results.append(resp.choices[0].message.content.strip())
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
                ('nitter-update', %s, NOW(), %s, %s, %s, %s, %s)
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
    groq_client   = Groq(api_key=GROQ_KEY)
    openai_client = OpenAI(api_key=OPENAI_KEY)

    total_written = 0
    total_errors = 0
    keywords_processed = 0
    all_instances_failed = True  # flipped if any keyword gets results

    with psycopg.connect(_get_db_url()) as conn:
        try:
            keywords = _load_keywords(conn)
            existing = _existing_ids(conn)
            log.info("Loaded %d active keywords, %d existing tweet_ids", len(keywords), len(existing))

            for _kw_id, keyword in keywords:
                log.info("Keyword: '%s'", keyword)
                tweets = _fetch_with_fallback(keyword)

                if tweets:
                    all_instances_failed = False

                new_tweets = []
                for t in tweets:
                    dedup_id = f"nitter_{t['id']}"
                    if dedup_id not in existing:
                        existing.add(dedup_id)
                        new_tweets.append({**t, "id": dedup_id})

                if not new_tweets:
                    keywords_processed += 1
                    continue

                summaries = _summarise([t["text"] for t in new_tweets], groq_client)
                vectors   = _embed_batch(summaries, openai_client)

                rows = []
                for tweet, summary, vector in zip(new_tweets, summaries, vectors):
                    embedding_str = "[" + ",".join(str(v) for v in vector) + "]"
                    rows.append((tweet["id"], keyword, tweet["tweet_date"], summary, embedding_str, "twitter"))

                written = _upsert_summaries(conn, rows)
                total_written += written
                keywords_processed += 1
                log.info("  +%d new rows (keyword='%s')", written, keyword)

            # All instances failed → warning (not error) so the daily run isn't red
            final_status = "warning" if all_instances_failed and keywords else "success"
            final_error  = "all nitter instances unreachable" if all_instances_failed and keywords else None

            _write_run_log(
                conn,
                status=final_status,
                records_written=total_written,
                errors=total_errors,
                error_message=final_error,
                meta={
                    "keywords_processed": keywords_processed,
                    "all_instances_failed": all_instances_failed,
                    "dry_run": DRY_RUN,
                },
                started_at=started_at,
            )
            log.info("Done. Written=%d errors=%d status=%s", total_written, total_errors, final_status)
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
