#!/usr/bin/env python3
"""generate_smart_sort_top50.py — Gate 7 smart sort batch script.

Applies the smart sort formula to all Pokemon assets with active signals,
ranks them, and outputs the top-50 list to:
  validation_reports/smart_sort_top50_v1.md

Formula (from public-calls-quality-gates.md Gate 7):
  score = signal_weight × log10(max(price_floor, 1)) × data_quality × freshness

  signal_weight: BREAKOUT=8, MOVE=3, WATCH=1, IDLE=0.3, INSUFFICIENT_DATA=0
  data_quality:  1.0 (≥10 price points) / 0.6 (3-9 points) / 0.2 (<3 points)
  freshness:     1.2 (<3d) / 1.0 (3-7d) / 0.7 (7-14d) / 0.3 (>14d)

Run:
    railway run python -m scripts.generate_smart_sort_top50
    python -m scripts.generate_smart_sort_top50   (local DB)

Output is written to validation_reports/smart_sort_top50_v1.md for Ivan review.
Ivan will calibrate weights based on whether "these are the cards a serious
investor would want to see first" (Gate 7 pass criterion).
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.models.asset import Asset
from backend.app.models.asset_signal import AssetSignal
from backend.app.models.price_history import PriceHistory

# ── Formula constants ─────────────────────────────────────────────────────────

SIGNAL_WEIGHTS: dict[str, float] = {
    "BREAKOUT": 8.0,
    "MOVE": 3.0,
    "WATCH": 1.0,
    "IDLE": 0.3,
    "INSUFFICIENT_DATA": 0.0,
}

# Freshness brackets (days since last price update)
_FRESHNESS = [
    (3, 1.2),   # < 3 days
    (7, 1.0),   # 3-7 days
    (14, 0.7),  # 7-14 days
    (9999, 0.3),  # > 14 days
]

# Data quality brackets (number of price points in last 30 days)
_DATA_QUALITY = [
    (10, 1.0),  # ≥ 10 points
    (3, 0.6),   # 3-9 points
    (0, 0.2),   # < 3 points
]

# Excluded sources (CardMarket EUR, eBay) — use only TCG API prices for floors
_EXCLUDED_SOURCES = frozenset({
    "cardmarket_avg1", "cardmarket_avg7", "cardmarket_avg30", "cardmarket_trend",
    "ebay_sold", "ebay_web_sold",
})


@dataclass
class SmartSortRow:
    rank: int
    asset_id: str
    name: str
    set_name: str | None
    card_number: str | None
    signal_label: str
    price_delta_pct: float | None
    price_floor: float | None
    price_points_30d: int
    last_price_age_days: float | None
    signal_weight: float
    data_quality: float
    freshness: float
    smart_score: float


def _freshness_score(age_days: float | None) -> float:
    if age_days is None:
        return 0.3
    for threshold, score in _FRESHNESS:
        if age_days < threshold:
            return score
    return 0.3


def _data_quality_score(n_points: int) -> float:
    for threshold, score in _DATA_QUALITY:
        if n_points >= threshold:
            return score
    return 0.2


def _smart_score(
    *,
    signal_label: str,
    price_floor: float | None,
    n_points: int,
    age_days: float | None,
) -> tuple[float, float, float, float]:
    """Returns (raw_score, signal_weight, data_quality, freshness)."""
    sw = SIGNAL_WEIGHTS.get(signal_label, 0.0)
    dq = _data_quality_score(n_points)
    fr = _freshness_score(age_days)
    floor = max(price_floor or 0.0, 1.0)
    score = sw * math.log10(floor) * dq * fr
    return score, sw, dq, fr


def build_top50(db: Session, top_n: int = 50) -> list[SmartSortRow]:
    """Compute smart sort scores across all pokemon assets with signals."""
    now = datetime.now(UTC)
    cutoff_30d = now - timedelta(days=30)

    # All pokemon asset_signals
    signals = db.scalars(
        select(AssetSignal)
        .join(Asset, Asset.id == AssetSignal.asset_id)
        .where(Asset.game == "pokemon")
    ).all()

    # Price stats per asset (last 30 days, non-excluded sources)
    price_stats = db.execute(
        select(
            PriceHistory.asset_id,
            func.count().label("n_points"),
            func.max(PriceHistory.price).label("max_price"),
            func.max(PriceHistory.captured_at).label("latest_at"),
        )
        .where(
            PriceHistory.captured_at >= cutoff_30d,
            PriceHistory.source.not_in(_EXCLUDED_SOURCES),
        )
        .group_by(PriceHistory.asset_id)
    ).all()

    price_map: dict = {str(r.asset_id): r for r in price_stats}

    rows: list[SmartSortRow] = []
    for sig in signals:
        asset = db.get(Asset, sig.asset_id)
        if asset is None:
            continue

        asset_id_str = str(sig.asset_id)
        ps = price_map.get(asset_id_str)

        n_points = int(ps.n_points) if ps else 0
        price_floor = float(ps.max_price) if ps and ps.max_price else None
        age_days = (
            (now - ps.latest_at.replace(tzinfo=UTC)).total_seconds() / 86400
            if ps and ps.latest_at else None
        )

        score, sw, dq, fr = _smart_score(
            signal_label=sig.label,
            price_floor=price_floor,
            n_points=n_points,
            age_days=age_days,
        )

        rows.append(SmartSortRow(
            rank=0,  # assigned after sort
            asset_id=asset_id_str,
            name=asset.name,
            set_name=asset.set_name,
            card_number=asset.card_number,
            signal_label=sig.label,
            price_delta_pct=(
                float(sig.price_delta_pct) if sig.price_delta_pct is not None else None
            ),
            price_floor=price_floor,
            price_points_30d=n_points,
            last_price_age_days=round(age_days, 1) if age_days is not None else None,
            signal_weight=sw,
            data_quality=dq,
            freshness=fr,
            smart_score=round(score, 4),
        ))

    # Sort by score desc, break ties by price_delta_pct desc
    rows.sort(key=lambda r: (r.smart_score, r.price_delta_pct or 0), reverse=True)
    for i, row in enumerate(rows[:top_n], start=1):
        row.rank = i

    return rows[:top_n]


def write_report(rows: list[SmartSortRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC).isoformat()

    lines = [
        "# Smart Sort Top-50 — Gate 7 Validation",
        "",
        f"**Generated:** {now}",
        "**Formula:**",
        "```",
        "score = signal_weight × log10(max(price_floor, 1)) × data_quality × freshness",
        "",
        "signal_weight: BREAKOUT=8, MOVE=3, WATCH=1, IDLE=0.3",
        "data_quality:  1.0 (≥10 pts) / 0.6 (3-9 pts) / 0.2 (<3 pts)",
        "freshness:     1.2 (<3d) / 1.0 (3-7d) / 0.7 (7-14d) / 0.3 (>14d)",
        "```",
        "",
        "## Gate 7 pass criterion",
        "",
        "> Ivan confirms: \"these are the cards a serious investor would want to see first\"",
        "",
        "Adjust formula weights and regenerate until confirmed.",
        "",
        "## Top-50 list",
        "",
        "| Rank | Card | Set | # | Signal | Δ% | Price Floor | Pts 30d | "
        "Age (d) | SW | DQ | FR | Score |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]

    for r in rows:
        delta_str = f"{r.price_delta_pct:+.1f}%" if r.price_delta_pct is not None else "—"
        price_str = f"${r.price_floor:.2f}" if r.price_floor else "—"
        age_str = str(r.last_price_age_days) if r.last_price_age_days is not None else "—"
        lines.append(
            f"| {r.rank} | {r.name} | {r.set_name or '—'} | {r.card_number or '—'} | "
            f"{r.signal_label} | {delta_str} | {price_str} | {r.price_points_30d} | "
            f"{age_str} | {r.signal_weight} | {r.data_quality} | {r.freshness} | "
            f"{r.smart_score} |"
        )

    lines += [
        "",
        "## Formula calibration notes",
        "",
        "This is the default formula from Gate 7 spec. Subject to Ivan's review.",
        "If feedback like 'too much weight on price' → reduce log10 scale or cap price tier.",
        "If feedback like 'BREAKOUT not prominent enough' → increase BREAKOUT weight (8 → 12).",
        "Regenerate with adjusted weights until Gate 7 pass criterion met.",
        "",
        f"*Script: `scripts/generate_smart_sort_top50.py` — run `railway run python -m scripts.generate_smart_sort_top50`*",
    ]

    path.write_text("\n".join(lines), encoding="utf-8")


def main(top_n: int = 50) -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url)

    print(f"Generating smart sort top-{top_n} list…")
    with Session(engine) as db:
        rows = build_top50(db, top_n=top_n)

    if not rows:
        print("No rows generated — no pokemon assets with signals found.")
        print("Ensure signal sweep has run and produced asset_signals rows.")
        return

    # Print summary to stdout
    print(f"\nTop {min(len(rows), 20)} (of {len(rows)} scored):")
    print(f"{'Rank':<5} {'Signal':<15} {'Score':<8} {'Price':<10} {'Card'}")
    print("-" * 80)
    for r in rows[:20]:
        price_str = f"${r.price_floor:.2f}" if r.price_floor else "—"
        print(f"{r.rank:<5} {r.signal_label:<15} {r.smart_score:<8.3f} {price_str:<10} {r.name}")

    report_path = (
        Path(__file__).resolve().parents[1] / "validation_reports" / "smart_sort_top50_v1.md"
    )
    write_report(rows, report_path)
    print(f"\nFull report written to: {report_path}")
    print("\nGate 7: Ivan review required — do these results match investor intent?")


if __name__ == "__main__":
    main()
