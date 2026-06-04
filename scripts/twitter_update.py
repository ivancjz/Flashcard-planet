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

DATABASE_URL      = os.environ["DATABASE_URL"]
ANTHROPIC_KEY     = os.environ["ANTHROPIC_API_KEY"]
OPENAI_KEY        = os.environ["OPENAI_API_KEY"]
AUTH_TOKEN        = os.environ["TWITTER_AUTH_TOKEN"]
CT0               = os.environ["TWITTER_CT0"]

WINDOW_SLEEP      = int(os.environ.get("TWITTER_WINDOW_SLEEP_SECONDS", "30"))
SUMMARY_THRESHOLD = int(os.environ.get("TWITTER_SUMMARY_THRESHOLD", "500"))
EMBED_BATCH_SIZE  = int(os.environ.get("TWITTER_EMBED_BATCH_SIZE", "100"))
DRY_RUN           = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")

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
            break

    return tweets, next_cursor


def _parse_tweet(result: dict) -> dict | None:
    """Mirror parseTweetFromSearch() from xreach search.ts."""
    if result.get("__typename") == "TweetTombstone":
        return None
    tweet_data = result.get("tweet") or result
    legacy = tweet_data.get("legacy", {})
    text = legacy.get("full_text", "")   # full_text not text
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
