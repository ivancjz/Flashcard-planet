"""Production DB query runner for the 2026-05-01 signal audit."""
import psycopg
import json
import sys
from datetime import datetime, UTC

DB_URL = "postgresql://postgres:LWGilgVwqDZmkqzNcbXdteGzPbnuNQIN@junction.proxy.rlwy.net:19115/railway"


def run(label: str, sql: str, params=None):
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or [])
            cols = [d[0] for d in cur.description] if cur.description else []
            rows = cur.fetchall()
    print(f"\n=== {label} ===")
    if cols:
        print("  " + " | ".join(cols))
        print("  " + "-" * 60)
        for r in rows:
            print("  " + " | ".join(str(v) for v in r))
    print(f"  ({len(rows)} rows)")
    return cols, rows


if __name__ == "__main__":
    # Step 0: Leaderboard snapshot — top 15 by price_delta_pct
    run(
        "STEP 0 — Leaderboard snapshot (top 15 by delta)",
        """
        SELECT
            a.name,
            a.set_name,
            s.label,
            s.price_delta_pct,
            s.confidence,
            s.liquidity_score,
            (SELECT price FROM price_history
             WHERE asset_id = a.id AND source = 'pokemon_tcg_api'
             ORDER BY captured_at DESC LIMIT 1) AS tcg_price,
            (SELECT price FROM price_history
             WHERE asset_id = a.id AND source = 'ebay_sold'
             ORDER BY captured_at DESC LIMIT 1) AS ebay_price,
            (SELECT COUNT(*) FROM price_history
             WHERE asset_id = a.id AND source = 'ebay_sold'
               AND captured_at >= NOW() - INTERVAL '24 hours') AS ebay_24h_count,
            s.signal_context
        FROM asset_signals s
        JOIN assets a ON a.id = s.asset_id
        WHERE s.price_delta_pct IS NOT NULL
          AND a.game = 'pokemon'
        ORDER BY s.price_delta_pct DESC NULLS LAST
        LIMIT 15
        """
    )
