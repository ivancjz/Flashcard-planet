"""Remaining evidence queries for the 2026-05-01 signal audit."""
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


# 1.2 Cross-source contamination — fixed: bucket CASE in subquery, aggregate outside
run(
    "1.2 Source breakdown per window for top 5 BREAKOUT cards",
    """
    WITH top_cards AS (
        SELECT s.asset_id, a.name, a.set_name
        FROM asset_signals s
        JOIN assets a ON a.id = s.asset_id
        WHERE s.label = 'BREAKOUT' AND s.price_delta_pct IS NOT NULL AND a.game = 'pokemon'
        ORDER BY s.price_delta_pct DESC
        LIMIT 5
    ),
    windowed AS (
        SELECT
            tc.name, tc.set_name, ph.source,
            CASE
                WHEN ph.captured_at >= NOW() - INTERVAL '24 hours' THEN 'current'
                WHEN ph.captured_at <= NOW() - INTERVAL '7 days' THEN 'baseline'
                ELSE 'middle'
            END AS win
        FROM top_cards tc
        JOIN price_history ph ON ph.asset_id = tc.asset_id
        WHERE ph.market_segment = 'raw'
    )
    SELECT name, set_name, source, win, COUNT(*) AS row_count
    FROM windowed
    GROUP BY name, set_name, source, win
    ORDER BY name, win, source
    """
)

# 1.3 BREAKOUT/MOVE by eBay 24h sales count — is '0 sales + BREAKOUT' the norm?
run(
    "1.3 BREAKOUT/MOVE distribution by eBay 24h sales",
    """
    WITH ebay_counts AS (
        SELECT asset_id, COUNT(*) AS cnt
        FROM price_history
        WHERE source = 'ebay_sold'
          AND captured_at >= NOW() - INTERVAL '24 hours'
        GROUP BY asset_id
    )
    SELECT s.label,
           COALESCE(ec.cnt, 0) AS ebay_24h_sales,
           COUNT(*) AS card_count
    FROM asset_signals s
    LEFT JOIN ebay_counts ec ON ec.asset_id = s.asset_id
    WHERE s.label IN ('BREAKOUT', 'MOVE')
    GROUP BY s.label, COALESCE(ec.cnt, 0)
    ORDER BY s.label, ebay_24h_sales DESC
    """
)

# 1.4 Liquidity score source breakdown
run(
    "1.4 Liquidity component breakdown (TCG vs eBay rows) for top 10 BREAKOUT",
    """
    WITH top_breakout AS (
        SELECT s.asset_id, a.name, a.set_name, s.liquidity_score, s.confidence,
               s.price_delta_pct
        FROM asset_signals s
        JOIN assets a ON a.id = s.asset_id
        WHERE s.label = 'BREAKOUT' AND s.price_delta_pct IS NOT NULL AND a.game = 'pokemon'
        ORDER BY s.price_delta_pct DESC
        LIMIT 10
    ),
    stats AS (
        SELECT
            tb.asset_id,
            SUM(CASE WHEN ph.source = 'ebay_sold'
                     AND ph.captured_at >= NOW() - INTERVAL '7 days' THEN 1 ELSE 0 END) AS ebay_7d,
            SUM(CASE WHEN ph.source = 'pokemon_tcg_api'
                     AND ph.captured_at >= NOW() - INTERVAL '7 days' THEN 1 ELSE 0 END) AS tcg_7d,
            SUM(CASE WHEN ph.source = 'ebay_sold'
                     AND ph.captured_at >= NOW() - INTERVAL '30 days' THEN 1 ELSE 0 END) AS ebay_30d,
            SUM(CASE WHEN ph.source = 'pokemon_tcg_api'
                     AND ph.captured_at >= NOW() - INTERVAL '30 days' THEN 1 ELSE 0 END) AS tcg_30d,
            COUNT(DISTINCT ph.source) FILTER (WHERE ph.source != 'sample_seed') AS source_count,
            MAX(CASE WHEN ph.source = 'ebay_sold' THEN ph.captured_at END) AS last_ebay
        FROM top_breakout tb
        LEFT JOIN price_history ph ON ph.asset_id = tb.asset_id
        GROUP BY tb.asset_id
    )
    SELECT
        tb.name, tb.set_name,
        tb.liquidity_score, tb.confidence,
        tb.price_delta_pct::numeric(8,1) AS delta_pct,
        s.ebay_7d, s.tcg_7d, s.ebay_30d, s.tcg_30d,
        s.source_count, s.last_ebay
    FROM top_breakout tb
    JOIN stats s ON s.asset_id = tb.asset_id
    ORDER BY tb.price_delta_pct DESC
    """
)

# eBay ingest history — last 14 days, all runs with records_written > 0
run(
    "eBay ingest: all runs with records > 0 (last 14 days)",
    """
    SELECT job_name, status, started_at, finished_at,
           EXTRACT(EPOCH FROM (finished_at - started_at))::int AS dur_sec,
           records_written, meta_json
    FROM scheduler_run_log
    WHERE job_name ILIKE '%ebay%'
      AND records_written > 0
      AND started_at >= NOW() - INTERVAL '14 days'
    ORDER BY started_at DESC
    LIMIT 20
    """
)

# eBay ingest history — last 14 days, what's actually happening?
run(
    "eBay ingest: all runs summary (last 14 days)",
    """
    SELECT DATE(started_at AT TIME ZONE 'UTC') AS day,
           COUNT(*) AS run_count,
           SUM(records_written) AS total_records,
           MIN(EXTRACT(EPOCH FROM (finished_at - started_at))::int) AS min_dur,
           MAX(EXTRACT(EPOCH FROM (finished_at - started_at))::int) AS max_dur
    FROM scheduler_run_log
    WHERE job_name ILIKE '%ebay%'
      AND started_at >= NOW() - INTERVAL '14 days'
    GROUP BY 1
    ORDER BY 1 DESC
    """
)

# Check the most recent eBay ingest meta_json for clues
run(
    "eBay ingest: last 5 runs with meta_json",
    """
    SELECT started_at, finished_at,
           EXTRACT(EPOCH FROM (finished_at - started_at))::int AS dur_sec,
           records_written, error_message, meta_json
    FROM scheduler_run_log
    WHERE job_name ILIKE '%ebay%'
    ORDER BY started_at DESC
    LIMIT 5
    """
)

# 2.1 Sort: confirm naked sort is driving misleading leaderboard
run(
    "2.1 Top 20 by delta (the actual leaderboard order) — confidence comparison",
    """
    SELECT
        a.name, a.set_name, s.label,
        s.price_delta_pct::numeric(8,1) AS delta_pct,
        s.confidence,
        s.liquidity_score,
        (SELECT COUNT(*) FROM price_history
         WHERE asset_id = a.id AND source = 'ebay_sold'
           AND captured_at >= NOW() - INTERVAL '7 days') AS ebay_7d
    FROM asset_signals s
    JOIN assets a ON a.id = s.asset_id
    WHERE s.price_delta_pct IS NOT NULL AND a.game = 'pokemon'
      AND s.label IN ('BREAKOUT', 'MOVE')
    ORDER BY s.price_delta_pct DESC NULLS LAST
    LIMIT 20
    """
)

# 3.2 High-value base set signal check
run(
    "3.2 High-value base set cards",
    """
    SELECT a.name, a.set_name, s.label,
           s.price_delta_pct::numeric(8,1) AS delta_pct,
           s.confidence, s.liquidity_score,
           (SELECT COUNT(*) FROM price_history
            WHERE asset_id = a.id AND source = 'ebay_sold'
              AND captured_at >= NOW() - INTERVAL '24 hours') AS ebay_24h,
           (SELECT COUNT(*) FROM price_history
            WHERE asset_id = a.id AND source = 'ebay_sold'
              AND captured_at >= NOW() - INTERVAL '7 days') AS ebay_7d,
           (SELECT price FROM price_history WHERE asset_id = a.id AND source = 'pokemon_tcg_api'
            ORDER BY captured_at DESC LIMIT 1) AS tcg_price
    FROM assets a
    JOIN asset_signals s ON s.asset_id = a.id
    WHERE a.name IN ('Charizard', 'Pikachu', 'Mewtwo', 'Blastoise', 'Venusaur')
      AND (a.set_name ILIKE '%Base%' OR a.set_name = 'Base Set' OR a.set_name = 'Base Set 2')
    ORDER BY a.name, a.set_name
    """
)

# Overall signal counts
run(
    "Overall signal distribution",
    """
    SELECT label, COUNT(*) AS count,
           AVG(confidence) FILTER (WHERE confidence IS NOT NULL)::int AS avg_conf,
           AVG(liquidity_score) FILTER (WHERE liquidity_score IS NOT NULL)::int AS avg_liq
    FROM asset_signals
    GROUP BY label
    ORDER BY count DESC
    """
)

# Stoutland White Flare check (user mentioned it)
run(
    "Stoutland White Flare signal state",
    """
    SELECT a.name, a.set_name, s.label, s.price_delta_pct, s.confidence, s.liquidity_score,
           s.signal_context
    FROM asset_signals s
    JOIN assets a ON a.id = s.asset_id
    WHERE a.name ILIKE '%Stoutland%'
    ORDER BY a.set_name
    """
)
