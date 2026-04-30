"""Poll production DB every 2 min for the next eBay ingest run after 15:30 UTC."""
import psycopg, time, sys
from datetime import datetime, UTC

DB_URL = "postgresql://postgres:LWGilgVwqDZmkqzNcbXdteGzPbnuNQIN@junction.proxy.rlwy.net:19115/railway"
WATCH_AFTER = "2026-05-01 15:30:00+00"

print(f"Monitoring for eBay run after {WATCH_AFTER}... (Ctrl+C to stop)")
while True:
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(psycopg.sql.SQL("""
                SELECT started_at, finished_at, status, records_written,
                       error_message, meta_json
                FROM scheduler_run_log
                WHERE job_name ILIKE '%ebay%'
                  AND started_at > %s
                ORDER BY started_at DESC
                LIMIT 3
            """), [WATCH_AFTER])
            rows = cur.fetchall()

    now = datetime.now(UTC)
    if rows:
        print(f"\n[{now.strftime('%H:%M:%S')} UTC] FOUND {len(rows)} run(s):")
        for r in rows:
            started, finished, status, records, error_msg, meta = r
            print(f"  started={started} finished={finished} status={status} records={records}")
            print(f"  error={error_msg}")
            print(f"  meta={meta}")
        sys.exit(0)
    else:
        print(f"[{now.strftime('%H:%M:%S')} UTC] No run yet. Next check in 2 min.")

    time.sleep(120)
