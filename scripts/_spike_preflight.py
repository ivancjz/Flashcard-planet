"""Pre-flight check before running the YGO eBay feasibility spike.

Checks:
  1. eBay API daily budget remaining (need >=30 free slots)
  2. No active scheduler jobs in the last 15 minutes

Exit 0  = all clear
Exit 1  = one or more checks failed
"""
from __future__ import annotations
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text
from backend.app.db.session import SessionLocal
from backend.app.core.config import settings

db = SessionLocal()
try:
    # ── 1. Budget check ───────────────────────────────────────────────────────
    row = db.execute(text("""
        SELECT
          COALESCE(SUM((meta_json->>'api_calls_used')::int), 0) AS calls_today,
          (SELECT COUNT(*) FROM assets WHERE game = 'yugioh') AS ygo_assets
        FROM scheduler_run_log
        WHERE job_name = 'ebay-ingestion'
          AND started_at >= date_trunc('day', NOW() AT TIME ZONE 'UTC')
    """)).fetchone()
    calls_today  = int(row.calls_today or 0)
    ygo_assets   = int(row.ygo_assets  or 0)
    budget_limit = settings.ebay_daily_budget_limit
    remaining    = budget_limit - calls_today
    budget_ok    = remaining >= 30

    print("=== Budget Check ===")
    print(f"  ebay_daily_budget_limit       : {budget_limit}")
    print(f"  calls_today (assets ingested) : {calls_today}")
    print(f"  remaining                     : {remaining}")
    print(f"  spike needs 30 calls          : {'OK' if budget_ok else 'WARN — tight budget'}")
    print(f"  ygo_assets in DB              : {ygo_assets}")
    print()

    # ── 2. Active jobs check ──────────────────────────────────────────────────
    active = db.execute(text("""
        SELECT job_name, started_at
        FROM scheduler_run_log
        WHERE finished_at IS NULL
          AND started_at > NOW() - INTERVAL '15 minutes'
        ORDER BY started_at DESC
    """)).fetchall()

    print("=== Active Jobs (unfinished, last 15 min) ===")
    jobs_ok = len(active) == 0
    if active:
        for r in active:
            print(f"  RUNNING: {r.job_name}  started_at={r.started_at}")
        print("  ACTION: wait for jobs to finish or choose a quieter window")
    else:
        print("  No active jobs — clear to proceed")
    print()

    # ── 3. Config snapshot ────────────────────────────────────────────────────
    print("=== eBay Ingest Config ===")
    print(f"  ebay_scheduled_ingest_enabled : {settings.ebay_scheduled_ingest_enabled}")
    print(f"  ebay_max_calls_per_run        : {settings.ebay_max_calls_per_run}")
    print()

    # ── Decision ──────────────────────────────────────────────────────────────
    all_ok = budget_ok and jobs_ok
    print(f"=== Pre-flight result: {'PASS — run the spike' if all_ok else 'WARN — see above'} ===")
    sys.exit(0 if all_ok else 1)
finally:
    db.close()
