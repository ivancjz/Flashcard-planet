"""Final evidence queries for 2026-05-01 audit."""
import psycopg

DB_URL = "postgresql://postgres:LWGilgVwqDZmkqzNcbXdteGzPbnuNQIN@junction.proxy.rlwy.net:19115/railway"


def run(label, sql):
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(psycopg.sql.SQL(sql))
            cols = [d[0] for d in cur.description] if cur.description else []
            rows = cur.fetchall()
    print(f"\n=== {label} ===")
    if cols:
        print("  " + " | ".join(str(c) for c in cols))
        print("  " + "-" * 80)
        for r in rows:
            print("  " + " | ".join(str(v) for v in r))
    print(f"  ({len(rows)} rows)")
    return cols, rows


# eBay runs 2026-04-28 and 2026-04-29 — what's in the meta_json?
run(
    "eBay 2026-04-28 and 2026-04-29 runs with meta_json",
    """
    SELECT started_at, EXTRACT(EPOCH FROM (finished_at-started_at))::int AS dur_sec,
           records_written, error_message, meta_json
    FROM scheduler_run_log
    WHERE job_name ILIKE '%ebay%'
      AND started_at >= '2026-04-28 00:00:00+00'
      AND started_at < '2026-04-30 00:00:00+00'
    ORDER BY started_at DESC
    LIMIT 15
    """
)

# Ingestion error details (last 24h)
run(
    "Ingestion error details",
    """
    SELECT started_at, finished_at, status, records_written, error_message, meta_json
    FROM scheduler_run_log
    WHERE job_name = 'ingestion' AND status = 'error'
      AND started_at >= NOW() - INTERVAL '48 hours'
    ORDER BY started_at DESC
    LIMIT 5
    """
)

# Check if there are any BREAKOUT cards with actual eBay sales
run(
    "BREAKOUT cards with at least 1 eBay sale in last 7 days",
    """
    WITH ebay_7d AS (
        SELECT asset_id, COUNT(*) AS cnt
        FROM price_history
        WHERE source = 'ebay_sold'
          AND captured_at >= NOW() - INTERVAL '7 days'
        GROUP BY asset_id
    )
    SELECT a.name, a.set_name, s.price_delta_pct::numeric(8,1), s.confidence,
           e.cnt AS ebay_7d_count,
           (SELECT price FROM price_history WHERE asset_id=a.id AND source='ebay_sold'
            ORDER BY captured_at DESC LIMIT 1) AS last_ebay_price
    FROM asset_signals s
    JOIN assets a ON a.id = s.asset_id
    JOIN ebay_7d e ON e.asset_id = s.asset_id
    WHERE s.label = 'BREAKOUT'
    ORDER BY e.cnt DESC, s.price_delta_pct DESC
    LIMIT 20
    """
)

# Baseline window boundary check — what date is "7 days ago"?
# Any eBay rows written in the baseline window?
run(
    "eBay rows in baseline window (7-14 days ago) vs current data",
    """
    SELECT
        CASE
            WHEN captured_at >= NOW() - INTERVAL '24 hours' THEN 'current'
            WHEN captured_at >= NOW() - INTERVAL '7 days'
                 AND captured_at < NOW() - INTERVAL '24 hours' THEN 'middle_1_7d'
            WHEN captured_at >= NOW() - INTERVAL '30 days'
                 AND captured_at < NOW() - INTERVAL '7 days' THEN 'baseline'
            ELSE 'old_30d+'
        END AS bucket,
        COUNT(*) AS row_count,
        COUNT(DISTINCT asset_id) AS unique_cards
    FROM price_history
    WHERE source = 'ebay_sold'
    GROUP BY 1
    ORDER BY 1
    """
)

# Overall price_history source summary
run(
    "price_history source and recency summary",
    """
    SELECT source,
           COUNT(*) AS total_rows,
           MAX(captured_at) AS latest,
           COUNT(*) FILTER (WHERE captured_at >= NOW() - INTERVAL '24 hours') AS last_24h,
           COUNT(*) FILTER (WHERE captured_at >= NOW() - INTERVAL '7 days') AS last_7d
    FROM price_history
    WHERE source != 'sample_seed'
    GROUP BY source
    ORDER BY total_rows DESC
    """
)

# INSUFFICIENT_DATA signal context breakdown
run(
    "INSUFFICIENT_DATA reasons",
    """
    SELECT
        signal_context->>'reason' AS reason,
        signal_context->>'downgrade_reason' AS downgrade_reason,
        COUNT(*) AS count
    FROM asset_signals
    WHERE label = 'INSUFFICIENT_DATA'
    GROUP BY 1, 2
    ORDER BY 3 DESC
    """
)

# Orphaned running row check
run(
    "Orphaned 'running' scheduler rows",
    """
    SELECT job_name, started_at, records_written,
           EXTRACT(EPOCH FROM (NOW() - started_at))/3600 AS hours_ago
    FROM scheduler_run_log
    WHERE status = 'running'
    ORDER BY started_at DESC
    """
)
