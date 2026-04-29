"""One-shot diagnostic: why did migration 0028 not backfill?"""
import os, json, sys
from sqlalchemy import create_engine, text

url = os.environ.get("DATABASE_URL", "")
if not url:
    print("ERROR: DATABASE_URL not set")
    sys.exit(1)

engine = create_engine(url)
with engine.connect() as conn:
    print("=== 1. metadata keys in yugioh assets ===")
    rows = conn.execute(text(
        "SELECT jsonb_object_keys(metadata) AS k, COUNT(*) AS n "
        "FROM assets WHERE game='yugioh' GROUP BY k ORDER BY n DESC"
    )).fetchall()
    for r in rows:
        print(f"  {r[0]}: {r[1]}")

    print("\n=== 2. migration WHERE clause row count ===")
    n = conn.execute(text(
        "SELECT COUNT(*) FROM assets "
        "WHERE game='yugioh' AND metadata ? 'set_code' "
        "AND COALESCE(metadata->'set'->>'id', '') = ''"
    )).scalar()
    print(f"  rows matching: {n}")

    print("\n=== 3. sample row ===")
    r = conn.execute(text(
        "SELECT id, card_number, metadata FROM assets WHERE game='yugioh' LIMIT 1"
    )).fetchone()
    if r:
        print(f"  id={r[0]}")
        print(f"  card_number={r[1]}")
        print(f"  metadata={json.dumps(r[2], indent=4)}")
