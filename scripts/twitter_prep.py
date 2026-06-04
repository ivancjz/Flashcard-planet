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

import json
import logging
import os
from datetime import UTC, datetime

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
    started_at = datetime.now(UTC)
    refreshed = 0
    deleted = 0

    with psycopg.connect(_get_db_url()) as conn:
        try:
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

            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO scheduler_run_log
                        (job_name, started_at, finished_at, status, records_written, errors, meta_json)
                    VALUES
                        ('twitter-prep', %s, NOW(), 'success', %s, 0, %s)
                    """,
                    (
                        started_at,
                        deleted,
                        json.dumps({"keywords_refreshed": refreshed, "summaries_pruned": deleted,
                                    "retention_days": RETENTION_DAYS}),
                    ),
                )
            conn.commit()

        except Exception as exc:
            log.exception("Fatal error")
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO scheduler_run_log
                            (job_name, started_at, finished_at, status, records_written, errors,
                             error_message, meta_json)
                        VALUES
                            ('twitter-prep', %s, NOW(), 'error', 0, 1, %s, %s)
                        """,
                        (started_at, str(exc)[:500],
                         json.dumps({"keywords_refreshed": refreshed, "summaries_pruned": deleted})),
                    )
                conn.commit()
            except Exception:
                pass
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
