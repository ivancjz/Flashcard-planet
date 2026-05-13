"""Build card sample for eBay feasibility analysis. Run via: railway run python experiments/ebay-feasibility/_query_sample.py"""
import os, json
import sqlalchemy as sa

engine = sa.create_engine(os.environ['DATABASE_URL'], pool_pre_ping=True)

with engine.connect() as conn:
    # Tier H: top 10 by ebay_sold count in 90d pre-cliff
    r_h = conn.execute(sa.text("""
        SELECT a.id, a.name, a.set_name, a.card_number,
               COALESCE(a.variant,'') AS variant,
               COALESCE(a.grade_company,'') AS grade_company,
               COALESCE(a.grade_score::text,'') AS grade_score,
               COUNT(ph.id) AS sold_count,
               ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ph.price::numeric),2) AS median_sold,
               'H' AS tier
        FROM assets a
        JOIN price_history ph ON ph.asset_id=a.id
        WHERE ph.source='ebay_sold'
          AND ph.captured_at >= '2026-01-27'
          AND ph.captured_at <  '2026-04-27'
        GROUP BY a.id,a.name,a.set_name,a.card_number,a.variant,a.grade_company,a.grade_score
        ORDER BY sold_count DESC
        LIMIT 10
    """))
    rows_h = [dict(r._mapping) for r in r_h]

    # Tier M: ranks 50-60
    r_m = conn.execute(sa.text("""
        SELECT a.id, a.name, a.set_name, a.card_number,
               COALESCE(a.variant,'') AS variant,
               COALESCE(a.grade_company,'') AS grade_company,
               COALESCE(a.grade_score::text,'') AS grade_score,
               COUNT(ph.id) AS sold_count,
               ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ph.price::numeric),2) AS median_sold,
               'M' AS tier
        FROM assets a
        JOIN price_history ph ON ph.asset_id=a.id
        WHERE ph.source='ebay_sold'
          AND ph.captured_at >= '2026-01-27'
          AND ph.captured_at <  '2026-04-27'
        GROUP BY a.id,a.name,a.set_name,a.card_number,a.variant,a.grade_company,a.grade_score
        ORDER BY sold_count DESC
        LIMIT 11 OFFSET 49
    """))
    rows_m = [dict(r._mapping) for r in r_m]

    # Tier L: 3-10 sold records, pick 10
    r_l = conn.execute(sa.text("""
        SELECT a.id, a.name, a.set_name, a.card_number,
               COALESCE(a.variant,'') AS variant,
               COALESCE(a.grade_company,'') AS grade_company,
               COALESCE(a.grade_score::text,'') AS grade_score,
               COUNT(ph.id) AS sold_count,
               ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ph.price::numeric),2) AS median_sold,
               'L' AS tier
        FROM assets a
        JOIN price_history ph ON ph.asset_id=a.id
        WHERE ph.source='ebay_sold'
          AND ph.captured_at >= '2026-01-27'
          AND ph.captured_at <  '2026-04-27'
        GROUP BY a.id,a.name,a.set_name,a.card_number,a.variant,a.grade_company,a.grade_score
        HAVING COUNT(ph.id) BETWEEN 3 AND 10
        ORDER BY COUNT(ph.id) DESC
        LIMIT 10
    """))
    rows_l = [dict(r._mapping) for r in r_l]

    all_rows = rows_h + rows_m + rows_l
    print(f"Tier H: {len(rows_h)} cards, Tier M: {len(rows_m)} cards, Tier L: {len(rows_l)} cards")
    
    # Convert Decimal to float for JSON
    import decimal
    def fix(v):
        return float(v) if isinstance(v, decimal.Decimal) else v
    all_rows = [{k: fix(v) for k,v in row.items()} for row in all_rows]
    
    with open('experiments/ebay-feasibility/sample-cards.json','w') as f:
        json.dump(all_rows, f, indent=2, default=str)
    print("Written to experiments/ebay-feasibility/sample-cards.json")
    
    # Pretty print
    for row in all_rows:
        print(f"[{row['tier']}] id={row['id']} sold={row['sold_count']} median=${row['median_sold']} | {row['name']} ({row['set_name']}) {row['grade_company']} {row['grade_score']}")
