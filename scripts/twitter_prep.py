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

DATABASE_URL   = os.environ["DATABASE_URL"]
RETENTION_DAYS = int(os.environ.get("TWITTER_RETENTION_DAYS", "90"))


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
