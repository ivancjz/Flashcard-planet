"""Pre-fix evidence for Bug 1 (P0): liquidity counts TCG polls as sales."""
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
        print("  " + "-" * 90)
        for r in rows:
            print("  " + " | ".join(str(v) for v in r))
    print(f"  ({len(rows)} rows)")
    return cols, rows


# Pre-fix: liquidity_score vs source breakdown for top 20 BREAKOUT cards
# Shows that high liquidity is driven by TCG polls, not eBay sales
run(
    "Pre-fix: BREAKOUT cards — liquidity_score vs ebay_sold_7d vs tcg_polls_7d",
    """
    SELECT
        a.name,
        a.set_name,
        s.label,
        s.liquidity_score,
        s.confidence,
        s.price_delta_pct::numeric(8,1) AS delta_pct,
        COUNT(ph.id) FILTER (
            WHERE ph.source = 'ebay_sold'
              AND ph.captured_at >= NOW() - INTERVAL '7 days'
        ) AS ebay_sold_7d,
        COUNT(ph.id) FILTER (
            WHERE ph.source = 'pokemon_tcg_api'
              AND ph.captured_at >= NOW() - INTERVAL '7 days'
        ) AS tcg_polls_7d,
        COUNT(ph.id) FILTER (
            WHERE ph.captured_at >= NOW() - INTERVAL '7 days'
              AND ph.source != 'sample_seed'
        ) AS total_rows_7d
    FROM asset_signals s
    JOIN assets a ON a.id = s.asset_id
    LEFT JOIN price_history ph ON ph.asset_id = s.asset_id
    WHERE s.label = 'BREAKOUT'
      AND s.price_delta_pct IS NOT NULL
      AND a.game = 'pokemon'
    GROUP BY a.id, a.name, a.set_name, s.label, s.liquidity_score, s.confidence, s.price_delta_pct
    ORDER BY s.price_delta_pct DESC
    LIMIT 20
    """
)

# Pre-fix: histogram of liquidity_score for BREAKOUT/MOVE/WATCH cards
run(
    "Pre-fix: liquidity_score distribution for actionable signals",
    """
    SELECT
        s.label,
        s.liquidity_score,
        COUNT(*) AS card_count
    FROM asset_signals s
    WHERE s.label IN ('BREAKOUT', 'MOVE', 'WATCH')
    GROUP BY s.label, s.liquidity_score
    ORDER BY s.label, s.liquidity_score DESC
    """
)

# Pre-fix: for each BREAKOUT card, show the actual DB query inputs (what counts as sales)
run(
    "Pre-fix: Lickitung Jungle — current liquidity source counts",
    """
    SELECT
        ph.source,
        COUNT(*) FILTER (WHERE ph.captured_at >= NOW() - INTERVAL '7 days') AS cnt_7d,
        COUNT(*) FILTER (WHERE ph.captured_at >= NOW() - INTERVAL '30 days') AS cnt_30d,
        MAX(ph.captured_at) AS last_observed
    FROM price_history ph
    JOIN assets a ON a.id = ph.asset_id
    WHERE a.name = 'Lickitung' AND a.set_name = 'Jungle'
      AND ph.source != 'sample_seed'
    GROUP BY ph.source
    """
)

print("\n=== SNAPSHOT TIMESTAMP ===")
with psycopg.connect(DB_URL) as conn:
    with conn.cursor() as cur:
        cur.execute(psycopg.sql.SQL("SELECT NOW() AT TIME ZONE 'UTC'"))
        ts = cur.fetchone()[0]
        print(f"  Production DB NOW() UTC: {ts}")
