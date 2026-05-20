#!/usr/bin/env python3
"""validate_driver_attribution.py — Gate 2 historical validation harness.

Runs the driver attribution rule engine against historical market_events in the
DB, comparing the engine's output against the expected driver for each event.

Output is written to validation_reports/driver_attribution_v1.md (created if
absent) and summarised on stdout.

Run:
    railway run python -m scripts.validate_driver_attribution
    python -m scripts.validate_driver_attribution   (local DB)

Evidence discipline: all event dates come from the market_events table (already
seeded with source_urls where available). Attribution results are computed live
against current DB state — no synthetic data.
"""
from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.models.asset import Asset
from backend.app.models.predictions import MarketEvent
from backend.app.services.driver_attribution_service import attribute_signal

# ── Expected driver per event_type ────────────────────────────────────────────

# Rule: INFLUENCER → EVENT_DRIVEN, TOURNAMENT → EVENT_DRIVEN,
#       SUPPLY → SUPPLY_SHOCK, RELEASE → MACRO (set-wide) or EVENT_DRIVEN
_EXPECTED_DRIVER: dict[str, str] = {
    "INFLUENCER": "EVENT_DRIVEN",
    "TOURNAMENT": "EVENT_DRIVEN",
    "SUPPLY": "SUPPLY_SHOCK",
    "RELEASE": "MACRO",  # broad set events; ENGINE may return EVENT_DRIVEN too
}

# For RELEASE events, both MACRO and EVENT_DRIVEN are acceptable.
_ACCEPTABLE_DRIVERS: dict[str, set[str]] = {
    "RELEASE": {"MACRO", "EVENT_DRIVEN"},
}


def _find_sample_assets(db: Session, event: MarketEvent, limit: int = 3) -> list[Asset]:
    """Find assets to test attribution for a given event."""
    asset_ids_raw = event.affected_asset_ids or []
    set_ids = event.affected_set_ids or []
    assets: list[Asset] = []

    # Prefer explicitly named assets
    if asset_ids_raw:
        for aid in asset_ids_raw[:limit]:
            try:
                import uuid
                a = db.get(Asset, uuid.UUID(str(aid)))
                if a:
                    assets.append(a)
            except Exception:
                pass

    # Fallback: any asset from the affected set
    if not assets and set_ids:
        set_assets = db.scalars(
            select(Asset).where(Asset.set_name.in_(set_ids)).limit(limit)
        ).all()
        assets.extend(set_assets)

    # Last fallback: any pokemon asset
    if not assets:
        fallback = db.scalars(
            select(Asset).where(Asset.game == "pokemon").limit(1)
        ).first()
        if fallback:
            assets.append(fallback)

    return assets


def run_validation(db: Session) -> dict:
    """Run attribution engine against all market_events. Returns summary dict."""
    events = db.scalars(
        select(MarketEvent).order_by(MarketEvent.event_date.desc())
    ).all()

    results = []
    total = 0
    correct = 0
    acceptable = 0

    for ev in events:
        expected = _EXPECTED_DRIVER.get(ev.event_type, "UNKNOWN")
        acceptable_set = _ACCEPTABLE_DRIVERS.get(ev.event_type, {expected})

        sample_assets = _find_sample_assets(db, ev, limit=2)
        if not sample_assets:
            results.append({
                "event": ev.description[:80],
                "event_type": ev.event_type,
                "event_date": str(ev.event_date.date()),
                "expected": expected,
                "actual": "N/A",
                "confidence": None,
                "reason": "No sample assets found",
                "pass": False,
                "skipped": True,
            })
            continue

        # Use event's expected_window_days as signal_window_days.
        # reference_time = event_date + 1 day: simulates the signal firing one
        # day after the event started (well within its impact window). This is
        # necessary because attribute_signal defaults to datetime.now(UTC),
        # which places all historical events outside the current window.
        window_days = ev.expected_window_days or 14
        reference_time = ev.event_date + timedelta(days=1)

        for asset in sample_assets:
            result = attribute_signal(
                db,
                asset_id=asset.id,
                signal_move_pct=Decimal("10"),  # positive synthetic move
                signal_window_days=window_days,
                reference_time=reference_time,
            )
            total += 1
            passed = result.driver in acceptable_set
            if result.driver == expected:
                correct += 1
            if passed:
                acceptable += 1

            results.append({
                "event": ev.description[:80],
                "event_type": ev.event_type,
                "event_date": str(ev.event_date.date()),
                "asset": f"{asset.name} [{asset.set_name}]",
                "expected": expected,
                "acceptable": sorted(acceptable_set),
                "actual": result.driver,
                "confidence": round(result.confidence, 3),
                "reason": result.reason[:120] if result.reason else "",
                "pass": passed,
                "skipped": False,
            })

    return {
        "run_at": datetime.now(UTC).isoformat(),
        "total_cases": total,
        "correct": correct,
        "acceptable": acceptable,
        "accuracy_strict": correct / total if total else 0.0,
        "accuracy_acceptable": acceptable / total if total else 0.0,
        "results": results,
    }


def write_report(summary: dict, path: Path) -> None:
    """Write Gate 2 validation report to Markdown."""
    path.parent.mkdir(parents=True, exist_ok=True)
    run_at = summary["run_at"]
    total = summary["total_cases"]
    strict = summary["accuracy_strict"]
    accept = summary["accuracy_acceptable"]

    lines = [
        "# Driver Attribution Validation — Gate 2",
        "",
        f"**Run at:** {run_at}",
        f"**Total test cases:** {total}",
        f"**Accuracy (strict — exact match):** {strict:.1%}",
        f"**Accuracy (acceptable — RELEASE may be MACRO or EVENT_DRIVEN):** {accept:.1%}",
        "",
        "## Pass criteria (Ivan to review)",
        "",
        "- Accuracy threshold: **TBD by Ivan based on initial results**",
        "- All INFLUENCER events → EVENT_DRIVEN",
        "- All TOURNAMENT events → EVENT_DRIVEN",
        "- All SUPPLY events → SUPPLY_SHOCK",
        "- RELEASE events → MACRO or EVENT_DRIVEN",
        "- UNKNOWN is a valid output when no event matches (honest uncertainty)",
        "",
        "## Per-case results",
        "",
        "| Event | Type | Date | Asset | Expected | Actual | Confidence | Pass | Reason |",
        "|---|---|---|---|---|---|---|---|---|",
    ]

    for r in summary["results"]:
        if r.get("skipped"):
            lines.append(
                f"| {r['event']} | {r['event_type']} | {r['event_date']} | "
                f"*(skipped — no assets)* | {r['expected']} | N/A | — | — | — |"
            )
        else:
            pass_icon = "✓" if r["pass"] else "✗"
            lines.append(
                f"| {r['event']} | {r['event_type']} | {r['event_date']} | "
                f"{r['asset']} | {r['expected']} | {r['actual']} | "
                f"{r['confidence']} | {pass_icon} | {r['reason']} |"
            )

    lines += [
        "",
        "## Evidence discipline",
        "",
        "All event dates and descriptions sourced from `market_events` table,",
        "seeded via `scripts/seed_market_events.py`. Events marked `VERIFY DATE`",
        "in the seed script have approximate dates and must be confirmed before",
        "treating Gate 2 accuracy as authoritative.",
        "",
        f"*Report generated by `scripts/validate_driver_attribution.py` at {run_at}*",
    ]

    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url)

    with Session(engine) as db:
        print("Running driver attribution validation against market_events table…")
        summary = run_validation(db)

    # Print summary
    total = summary["total_cases"]
    strict = summary["accuracy_strict"]
    accept = summary["accuracy_acceptable"]
    print(f"\nResults: {total} test cases")
    print(f"  Strict accuracy:     {strict:.1%} ({summary['correct']}/{total})")
    print(f"  Acceptable accuracy: {accept:.1%} ({summary['acceptable']}/{total})")

    # Print per-case table
    print("\n{:<80} {:<14} {:<14} {:<10} {:<6}".format(
        "Event", "Expected", "Actual", "Confidence", "Pass"
    ))
    print("-" * 130)
    for r in summary["results"]:
        if r.get("skipped"):
            print(f"{'[SKIPPED] ' + r['event']:<80} {r['expected']:<14} {'N/A':<14} {'—':<10} {'—'}")
        else:
            pass_str = "PASS" if r["pass"] else "FAIL"
            print(
                f"{r['event']:<80} {r['expected']:<14} {r['actual']:<14} "
                f"{str(r['confidence']):<10} {pass_str}"
            )

    # Write report
    report_path = Path(__file__).resolve().parents[1] / "validation_reports" / "driver_attribution_v1.md"
    write_report(summary, report_path)
    print(f"\nReport written to: {report_path}")
    print("\nGate 2 verdict: Ivan review required. See report for per-case breakdown.")


if __name__ == "__main__":
    main()
