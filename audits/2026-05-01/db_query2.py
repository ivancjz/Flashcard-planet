"""Layer 0 and Layer 1 evidence queries for the 2026-05-01 signal audit."""
import psycopg

DB_URL = "postgresql://postgres:LWGilgVwqDZmkqzNcbXdteGzPbnuNQIN@junction.proxy.rlwy.net:19115/railway"


def run(label, sql):
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            # Use execute with no params — escape all literal % as %%
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


# 0.1 eBay ingest scheduler runs — last 7 days
run(
    "0.1 eBay scheduler runs (7d)",
    """
    SELECT job_name, status, started_at, finished_at,
           EXTRACT(EPOCH FROM (finished_at - started_at))::int AS duration_sec,
           records_written, error_message
    FROM scheduler_run_log
    WHERE (job_name ILIKE '%ebay%')
      AND started_at >= NOW() - INTERVAL '7 days'
    ORDER BY started_at DESC
    LIMIT 20
    """
)

# 0.1b eBay rows written to price_history by day (last 7 days)
run(
    "0.1b eBay price_history rows by day (7d)",
    """
    SELECT DATE(captured_at AT TIME ZONE 'UTC') AS day,
           COUNT(*) AS rows_written,
           COUNT(DISTINCT asset_id) AS unique_cards
    FROM price_history
    WHERE source = 'ebay_sold'
      AND captured_at >= NOW() - INTERVAL '7 days'
    GROUP BY 1
    ORDER BY 1 DESC
    """
)

# 0.2 Pokemon TCG ingest health
run(
    "0.2a TCG/ingestion scheduler runs (24h)",
    """
    SELECT job_name, status, COUNT(*) AS run_count,
           MIN(started_at) AS first_run, MAX(started_at) AS last_run,
           SUM(records_written) AS total_records
    FROM scheduler_run_log
    WHERE started_at >= NOW() - INTERVAL '24 hours'
    GROUP BY job_name, status
    ORDER BY job_name, status
    """
)

run(
    "0.2b TCG price freshness histogram",
    """
    SELECT
      CASE
        WHEN captured_at >= NOW() - INTERVAL '6 hours' THEN '0-6h'
        WHEN captured_at >= NOW() - INTERVAL '24 hours' THEN '6-24h'
        WHEN captured_at >= NOW() - INTERVAL '7 days' THEN '1-7d'
        ELSE '>7d'
      END AS age_bucket,
      COUNT(*) AS row_count
    FROM price_history
    WHERE source = 'pokemon_tcg_api'
    GROUP BY 1
    ORDER BY 1
    """
)

# 0.3 Anchor card source coverage
run(
    "0.3 Anchor card source coverage",
    """
    SELECT
        a.name, a.set_name,
        COUNT(ph.id) FILTER (WHERE ph.source = 'ebay_sold') AS ebay_total,
        COUNT(ph.id) FILTER (WHERE ph.source = 'ebay_sold' AND ph.captured_at >= NOW() - INTERVAL '24 hours') AS ebay_24h,
        COUNT(ph.id) FILTER (WHERE ph.source = 'ebay_sold' AND ph.captured_at >= NOW() - INTERVAL '7 days') AS ebay_7d,
        MAX(ph.captured_at) FILTER (WHERE ph.source = 'ebay_sold') AS last_ebay,
        COUNT(ph.id) FILTER (WHERE ph.source = 'pokemon_tcg_api') AS tcg_total,
        COUNT(ph.id) FILTER (WHERE ph.source = 'pokemon_tcg_api' AND ph.captured_at >= NOW() - INTERVAL '24 hours') AS tcg_24h,
        COUNT(ph.id) FILTER (WHERE ph.source = 'pokemon_tcg_api' AND ph.captured_at >= NOW() - INTERVAL '7 days') AS tcg_7d,
        MAX(ph.captured_at) FILTER (WHERE ph.source = 'pokemon_tcg_api') AS last_tcg
    FROM assets a
    LEFT JOIN price_history ph ON ph.asset_id = a.id
    WHERE (a.name = 'Lickitung' AND a.set_name = 'Jungle')
       OR (a.name = 'Kangaskhan ex' AND a.set_name = '151')
       OR (a.name = 'Snorlax' AND a.set_name = 'Crown Zenith')
       OR (a.name = 'Dark Jolteon' AND a.set_name = 'Team Rocket')
    GROUP BY a.id, a.name, a.set_name
    ORDER BY a.name
    """
)

# 1.1 Lickitung Jungle — all price rows last 14 days to reproduce the delta
run(
    "1.1a Lickitung Jungle price history (14d, newest first)",
    """
    SELECT ph.source, ph.price, ph.market_segment,
           ph.captured_at,
           ROUND(EXTRACT(EPOCH FROM (NOW() - ph.captured_at))/3600, 1) AS hours_ago
    FROM price_history ph
    JOIN assets a ON a.id = ph.asset_id
    WHERE a.name = 'Lickitung' AND a.set_name = 'Jungle'
      AND ph.captured_at >= NOW() - INTERVAL '14 days'
    ORDER BY ph.captured_at DESC
    LIMIT 60
    """
)

# 1.1b Baseline window breakdown for Lickitung (before 7 days ago, most recent 5)
run(
    "1.1b Lickitung Jungle BASELINE rows (before 7d cutoff, top 5 by recency)",
    """
    SELECT ph.source, ph.price, ph.market_segment, ph.captured_at
    FROM price_history ph
    JOIN assets a ON a.id = ph.asset_id
    WHERE a.name = 'Lickitung' AND a.set_name = 'Jungle'
      AND ph.captured_at <= NOW() - INTERVAL '7 days'
      AND ph.market_segment = 'raw'
    ORDER BY ph.captured_at DESC
    LIMIT 5
    """
)

# 1.1c Current window for Lickitung (last 24h, top 10)
run(
    "1.1c Lickitung Jungle CURRENT rows (last 24h, top 10)",
    """
    SELECT ph.source, ph.price, ph.market_segment, ph.captured_at
    FROM price_history ph
    JOIN assets a ON a.id = ph.asset_id
    WHERE a.name = 'Lickitung' AND a.set_name = 'Jungle'
      AND ph.captured_at >= NOW() - INTERVAL '24 hours'
      AND ph.market_segment = 'raw'
    ORDER BY ph.captured_at DESC
    LIMIT 10
    """
)

# 1.2 Cross-source contamination: sources in baseline vs current windows
run(
    "1.2 Source breakdown across windows for top 5 BREAKOUT cards",
    """
    WITH top_cards AS (
        SELECT s.asset_id, a.name, a.set_name, s.price_delta_pct, s.signal_context
        FROM asset_signals s
        JOIN assets a ON a.id = s.asset_id
        WHERE s.label = 'BREAKOUT' AND s.price_delta_pct IS NOT NULL AND a.game = 'pokemon'
        ORDER BY s.price_delta_pct DESC
        LIMIT 5
    )
    SELECT
        tc.name, tc.set_name,
        ph.source,
        CASE
            WHEN ph.captured_at >= NOW() - INTERVAL '24 hours' THEN 'current'
            WHEN ph.captured_at <= NOW() - INTERVAL '7 days' THEN 'baseline'
            ELSE 'middle'
        END AS window,
        COUNT(*) AS row_count,
        MIN(ph.price)::numeric(10,2) AS min_p, MAX(ph.price)::numeric(10,2) AS max_p
    FROM top_cards tc
    JOIN price_history ph ON ph.asset_id = tc.asset_id
    WHERE ph.market_segment = 'raw'
    GROUP BY tc.name, tc.set_name, ph.source, 3
    ORDER BY tc.name, 3, ph.source
    """
)

# 1.3 BREAKOUT/MOVE labels with 0 eBay sales — full breakdown
run(
    "1.3 BREAKOUT/MOVE by eBay 24h sales count",
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
    ORDER BY s.label, COALESCE(ec.cnt, 0) DESC
    """
)

# 1.4 Liquidity component breakdown: is liquidity score driven by TCG API rows?
run(
    "1.4 Liquidity source breakdown for BREAKOUT cards (top 10)",
    """
    WITH top_breakout AS (
        SELECT s.asset_id, a.name, a.set_name, s.liquidity_score, s.confidence, s.price_delta_pct
        FROM asset_signals s
        JOIN assets a ON a.id = s.asset_id
        WHERE s.label = 'BREAKOUT' AND s.price_delta_pct IS NOT NULL AND a.game = 'pokemon'
        ORDER BY s.price_delta_pct DESC
        LIMIT 10
    )
    SELECT
        tb.name, tb.set_name, tb.liquidity_score, tb.confidence, tb.price_delta_pct::numeric(8,1),
        COUNT(ph.id) FILTER (WHERE ph.source = 'ebay_sold' AND ph.captured_at >= NOW() - INTERVAL '7 days') AS ebay_7d,
        COUNT(ph.id) FILTER (WHERE ph.source = 'pokemon_tcg_api' AND ph.captured_at >= NOW() - INTERVAL '7 days') AS tcg_7d,
        COUNT(ph.id) FILTER (WHERE ph.source = 'ebay_sold' AND ph.captured_at >= NOW() - INTERVAL '30 days') AS ebay_30d,
        COUNT(ph.id) FILTER (WHERE ph.source = 'pokemon_tcg_api' AND ph.captured_at >= NOW() - INTERVAL '30 days') AS tcg_30d,
        COUNT(DISTINCT ph.source) FILTER (WHERE ph.source != 'sample_seed') AS source_count,
        MAX(ph.captured_at) FILTER (WHERE ph.source = 'ebay_sold') AS last_ebay
    FROM top_breakout tb
    LEFT JOIN price_history ph ON ph.asset_id = tb.asset_id
    GROUP BY tb.asset_id, tb.name, tb.set_name, tb.liquidity_score, tb.confidence, tb.price_delta_pct
    ORDER BY tb.price_delta_pct DESC
    """
)

# 2.1 Leaderboard sort — is confidence/volume used in the sort?
# Already checked in code (naked price_delta_pct DESC) — confirm via distribution
run(
    "2.1 Distribution: confidence vs delta for all BREAKOUT/MOVE",
    """
    SELECT
        s.label,
        FLOOR(s.price_delta_pct / 10) * 10 AS delta_bucket,
        COUNT(*) AS card_count,
        AVG(s.confidence)::int AS avg_confidence,
        AVG(s.liquidity_score)::int AS avg_liquidity
    FROM asset_signals s
    WHERE s.label IN ('BREAKOUT', 'MOVE') AND s.price_delta_pct IS NOT NULL
    GROUP BY s.label, 2
    ORDER BY 2 DESC
    LIMIT 20
    """
)

# 2.2 Volume field semantics — confirm what the '0 sales' column is
run(
    "2.2 eBay 24h rows total across all assets",
    """
    SELECT
        COUNT(DISTINCT asset_id) AS assets_with_ebay_24h,
        COUNT(*) AS total_ebay_24h_rows,
        MIN(captured_at) AS earliest, MAX(captured_at) AS latest
    FROM price_history
    WHERE source = 'ebay_sold'
      AND captured_at >= NOW() - INTERVAL '24 hours'
    """
)

# 3.2 High-liquidity domain check — Charizard, Mewtwo, Pikachu base set
run(
    "3.2 High-value base set cards signal state",
    """
    SELECT a.name, a.set_name, s.label, s.price_delta_pct::numeric(8,1),
           s.confidence, s.liquidity_score,
           (SELECT COUNT(*) FROM price_history
            WHERE asset_id = a.id AND source = 'ebay_sold'
              AND captured_at >= NOW() - INTERVAL '24 hours') AS ebay_24h,
           (SELECT COUNT(*) FROM price_history
            WHERE asset_id = a.id AND source = 'ebay_sold'
              AND captured_at >= NOW() - INTERVAL '7 days') AS ebay_7d
    FROM assets a
    JOIN asset_signals s ON s.asset_id = a.id
    WHERE a.name IN ('Charizard', 'Pikachu', 'Mewtwo', 'Blastoise', 'Venusaur')
      AND (a.set_name ILIKE '%Base%' OR a.set_name = 'Base Set')
    ORDER BY a.name, a.set_name
    """
)

# Overall signal count snapshot
run(
    "OVERALL signal counts right now",
    """
    SELECT label, COUNT(*) AS count
    FROM asset_signals
    GROUP BY label
    ORDER BY count DESC
    """
)

print("\n=== SNAPSHOT TIMESTAMP ===")
with psycopg.connect(DB_URL) as conn:
    with conn.cursor() as cur:
        cur.execute(psycopg.sql.SQL("SELECT NOW() AT TIME ZONE 'UTC'"))
        ts = cur.fetchone()[0]
        print(f"  Production DB NOW() UTC: {ts}")
