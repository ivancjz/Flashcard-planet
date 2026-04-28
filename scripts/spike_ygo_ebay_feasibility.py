"""spike_ygo_ebay_feasibility.py — read-only YGO eBay sold feasibility spike.

Decision input for Phase B (YGO eBay ingest enablement).
API budget: 30 calls hard cap. No DB writes.

Usage:
    python scripts/spike_ygo_ebay_feasibility.py
    python scripts/spike_ygo_ebay_feasibility.py --dry-run-ebay
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median as _median

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import httpx
from sqlalchemy import func, select, text

from backend.app.core.config import settings
from backend.app.db.session import SessionLocal
from backend.app.ingestion.ebay_sold import _fetch_finding_completed
from backend.app.ingestion.title_parser import parse_listing_title
from backend.app.models.asset import Asset

MAX_API_CALLS = 30
SAMPLE_SIZE = 10
LISTINGS_PER_ASSET = 20
LOOKBACK_DAYS = 30
PREFERRED_SETS = ["LEDE", "PHNI", "AGOV", "POTE", "TOCH"]

# ── Mock fixture for --dry-run-ebay ───────────────────────────────────────────
# Realistic YGO listing titles covering all parse outcomes.
_MOCK_LISTINGS: list[dict[str, str]] = [
    {"item_id": "m001", "title": "Blue-Eyes White Dragon LOB-001 Ultra Rare NM", "captured_at": "2026-03-30T10:00:00Z", "price": "42.50"},
    {"item_id": "m002", "title": "Blue-Eyes White Dragon PSA 9 LOB-001 1st Edition", "captured_at": "2026-03-29T10:00:00Z", "price": "310.00"},
    {"item_id": "m003", "title": "Blue-Eyes White Dragon BGS 8 LOB-001 Unlimited", "captured_at": "2026-03-28T10:00:00Z", "price": "185.00"},
    {"item_id": "m004", "title": "Blue-Eyes White Dragon LOB Near Mint Ungraded", "captured_at": "2026-03-27T10:00:00Z", "price": "38.00"},
    {"item_id": "m005", "title": "Blue-Eyes White Dragon LOB LP Light Play", "captured_at": "2026-03-26T10:00:00Z", "price": "28.00"},
    {"item_id": "m006", "title": "Blue-Eyes White Dragon LOB Ultra Rare raw", "captured_at": "2026-03-25T10:00:00Z", "price": "35.00"},
    {"item_id": "m007", "title": "YGO Cards Lot Blue-Eyes 5 cards LOB", "captured_at": "2026-03-24T10:00:00Z", "price": "90.00"},
    {"item_id": "m008", "title": "Blue-Eyes White Dragon LOB-001 CGC 9.5", "captured_at": "2026-03-23T10:00:00Z", "price": "220.00"},
    {"item_id": "m009", "title": "Blue-Eyes White Dragon LOB Custom Art Proxy", "captured_at": "2026-03-22T10:00:00Z", "price": "5.00"},
    {"item_id": "m010", "title": "Blue-Eyes White Dragon LOB-001 Ultra Rare mint condition", "captured_at": "2026-03-21T10:00:00Z", "price": "41.00"},
    {"item_id": "m011", "title": "Blue-Eyes White Dragon LOB-001 Ultra Rare", "captured_at": "2026-03-20T10:00:00Z", "price": "37.00"},
    {"item_id": "m012", "title": "Blue-Eyes White Dragon LOB-001 Ultra Rare NM/M", "captured_at": "2026-03-19T10:00:00Z", "price": "39.00"},
]


@dataclass
class AssetResult:
    external_id: str
    name: str
    set_id: str
    card_number: str
    rarity: str
    listings: int = 0
    raw: int = 0
    graded: int = 0
    unknown: int = 0
    excluded: int = 0
    error: str | None = None
    listing_titles: list[str] = field(default_factory=list)


def _sample_ygo_assets(db) -> list[Asset]:
    """Return up to SAMPLE_SIZE YGO assets, 1 per expansion set, preferred sets first.

    Ordering is deterministic (external_id) so repeated runs are comparable.
    """
    assets: list[Asset] = db.execute(
        select(Asset)
        .where(Asset.game == "yugioh")
        .order_by(Asset.external_id)
    ).scalars().all()

    # Group by expansion code (metadata.set.id), pick first per group
    seen_sets: set[str] = set()
    sampled: list[Asset] = []

    # Two passes: preferred sets first, then remaining
    def expansion(a: Asset) -> str:
        return (a.metadata_json or {}).get("set", {}).get("id", "") or (a.card_number or "").split("-")[0]

    preferred = [a for a in assets if expansion(a) in PREFERRED_SETS]
    rest = [a for a in assets if expansion(a) not in PREFERRED_SETS]

    for asset in preferred + rest:
        exp = expansion(asset)
        if exp not in seen_sets:
            seen_sets.add(exp)
            sampled.append(asset)
        if len(sampled) >= SAMPLE_SIZE:
            break

    return sampled


def _snapshot_row_counts(db) -> dict[str, int]:
    counts = {}
    for table in ("price_history", "assets", "graded_observation_audit"):
        try:
            n = db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() or 0
        except Exception:
            n = -1
        counts[table] = n
    return counts


def _search_ebay(client: httpx.Client, asset: Asset, api_calls: list[int]) -> list[dict] | None:
    """Query eBay findCompletedItems for an asset. Returns listing list or None on error."""
    if api_calls[0] >= MAX_API_CALLS:
        return None

    query = f"{asset.name} {asset.card_number or ''} {asset.variant or ''}".strip()
    api_calls[0] += 1
    return _fetch_finding_completed(client, query)


def _analyse_listings(listings: list[dict], limit: int) -> dict[str, int | list]:
    counts = {"raw": 0, "graded": 0, "unknown": 0, "excluded": 0, "titles": []}
    for item in listings[:limit]:
        title = item.get("title", "")
        result = parse_listing_title(title)
        if result.excluded:
            counts["excluded"] += 1
        elif result.market_segment == "raw":
            counts["raw"] += 1
        elif result.grade_company:
            counts["graded"] += 1
        else:
            counts["unknown"] += 1
        counts["titles"].append(title[:80])  # truncate for safety
    return counts


def _col(value: str, width: int) -> str:
    return value[:width].ljust(width)


def _print_report(
    results: list[AssetResult],
    api_calls_used: int,
    aborted: bool,
) -> None:
    print()
    print("=== YGO eBay Feasibility Spike ===")
    print(f"Sampled assets: {len(results)}")
    print(f"Total API calls: {api_calls_used}/{MAX_API_CALLS} budget{'  [ABORTED: budget hit]' if aborted else ''}")
    print()
    print("Per-asset breakdown:")
    hdr = (
        _col("external_id", 32)
        + _col("name", 28)
        + _col("set", 6)
        + _col("rarity", 18)
        + _col("listings", 10)
        + _col("raw", 6)
        + _col("graded", 8)
        + _col("unknown", 9)
        + "excl"
    )
    print(hdr)
    print("-" * len(hdr))
    for r in results:
        if r.error:
            print(_col(r.external_id, 32) + _col(r.name, 28) + f"  ERROR: {r.error}")
            continue
        print(
            _col(r.external_id, 32)
            + _col(r.name, 28)
            + _col(r.set_id, 6)
            + _col(r.rarity, 18)
            + _col(str(r.listings), 10)
            + _col(str(r.raw), 6)
            + _col(str(r.graded), 8)
            + _col(str(r.unknown), 9)
            + str(r.excluded)
        )

    print()
    ok_results = [r for r in results if r.error is None]
    total_listings = sum(r.listings for r in ok_results)
    listing_counts = [r.listings for r in ok_results]
    med = _median(listing_counts) if listing_counts else 0
    zero_assets = sum(1 for r in ok_results if r.listings == 0)
    total_raw = sum(r.raw for r in ok_results)
    total_graded = sum(r.graded for r in ok_results)
    total_unknown = sum(r.unknown for r in ok_results)
    total_scored = total_raw + total_graded + total_unknown
    raw_pct = total_raw / total_scored * 100 if total_scored else 0.0
    graded_pct = total_graded / total_scored * 100 if total_scored else 0.0
    unknown_pct = total_unknown / total_scored * 100 if total_scored else 0.0

    print("Aggregate:")
    print(f"  Total listings observed:   {total_listings}")
    print(f"  Median listings per asset: {med:.1f}")
    print(f"  Assets with 0 listings:    {zero_assets}/{len(ok_results)}")
    print(f"  Raw / total ratio:         {raw_pct:.1f}%")
    print(f"  Graded / total ratio:      {graded_pct:.1f}%")
    print(f"  Unknown / total ratio:     {unknown_pct:.1f}%")

    q1 = med >= 5
    q2 = raw_pct >= 60.0
    q3 = 10.0 <= graded_pct <= 50.0

    print()
    print("Decision signals:")
    print(f"  [{'PASS' if q1 else 'FAIL'}] Q1 (volume):       median >= 5 listings/asset (got {med:.1f})")
    print(f"  [{'PASS' if q2 else 'FAIL'}] Q2 (parseable):    raw_ratio >= 60% (got {raw_pct:.1f}%)")
    print(f"  [{'PASS' if q3 else 'FAIL'}] Q3 (graded scope): graded_ratio in 10-50% range (got {graded_pct:.1f}%)")

    print()
    print("Recommendation:")
    if q1 and q2 and q3:
        print("  All PASS  -> Proceed to Phase B (write YGO eBay ingest PR)")
    elif not q1 and zero_assets > len(ok_results) // 2:
        print("  Q1 fail   -> Consider sampling popular cards only or expanding lookback to 60 days")
    elif not q2:
        print("  Q2 fail   -> parse_listing_title needs YGO-specific patterns; new PR before Phase B")
    elif graded_pct > 50.0:
        print("  Q3 high   -> graded parser must be production-ready before YGO eBay enabled")
    elif graded_pct < 10.0:
        print("  Q3 low    -> graded shadow audit can stay disabled for YGO initially")
    if not q1 and not (zero_assets > len(ok_results) // 2):
        print("  Q1 fail   -> volume sparse; consider expanding lookback to 60 days")


def main(dry_run: bool) -> None:
    db = SessionLocal()
    try:
        # ── Safety snapshot ────────────────────────────────────────────────────
        before = _snapshot_row_counts(db)

        # ── Sample assets ──────────────────────────────────────────────────────
        assets = _sample_ygo_assets(db)
        if not assets:
            print("ERROR: no YGO assets found in DB. Run ygo ingest first.")
            sys.exit(1)

        print(f"Sampled {len(assets)} YGO assets:")
        for a in assets:
            exp = (a.metadata_json or {}).get("set", {}).get("id", "?")
            print(f"  {a.external_id or '?'}  {a.name}  set={exp}  rarity={a.variant or '?'}")
        print()

        # ── eBay search ────────────────────────────────────────────────────────
        api_calls: list[int] = [0]
        aborted = False
        results: list[AssetResult] = []

        with httpx.Client() as client:
            for asset in assets:
                exp = (asset.metadata_json or {}).get("set", {}).get("id", "?")
                ar = AssetResult(
                    external_id=asset.external_id or "?",
                    name=asset.name,
                    set_id=exp,
                    card_number=asset.card_number or "?",
                    rarity=asset.variant or "?",
                )

                if api_calls[0] >= MAX_API_CALLS:
                    ar.error = "budget_exhausted"
                    results.append(ar)
                    aborted = True
                    continue

                if dry_run:
                    raw_listings = list(_MOCK_LISTINGS)
                    api_calls[0] += 1
                else:
                    raw_listings = _search_ebay(client, asset, api_calls)

                if raw_listings is None:
                    ar.error = "ebay_api_error"
                    results.append(ar)
                    continue

                counts = _analyse_listings(raw_listings, LISTINGS_PER_ASSET)
                ar.listings = counts["raw"] + counts["graded"] + counts["unknown"] + counts["excluded"]
                ar.raw = counts["raw"]
                ar.graded = counts["graded"]
                ar.unknown = counts["unknown"]
                ar.excluded = counts["excluded"]
                ar.listing_titles = counts["titles"]
                results.append(ar)

        # ── Safety invariant ───────────────────────────────────────────────────
        after = _snapshot_row_counts(db)
        print()
        print("Safety: rows written this run")
        writes_detected = False
        for table in ("price_history", "assets", "graded_observation_audit"):
            delta = after[table] - before[table]
            expected = 0
            status = "OK" if delta == delta == 0 else "VIOLATION"
            if delta != 0:
                writes_detected = True
            print(f"  {table} INSERTs: {delta} (expected {expected})  [{status}]")

        if writes_detected:
            raise RuntimeError(
                "SPIKE SAFETY VIOLATION: rows were written. "
                "Spike must never write to production tables."
            )

        # ── Print report ───────────────────────────────────────────────────────
        _print_report(results, api_calls[0], aborted)

    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="YGO eBay sold feasibility spike (read-only)")
    parser.add_argument(
        "--dry-run-ebay",
        action="store_true",
        help="Skip real eBay API calls; use mock fixture titles instead",
    )
    args = parser.parse_args()
    main(dry_run=args.dry_run_ebay)
