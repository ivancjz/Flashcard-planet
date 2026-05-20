#!/usr/bin/env python3
"""validate_driver_attribution.py — Gate 2 historical validation harness.

Runs the driver attribution rule engine against historical market_events,
applying formal exclusion logic before computing accuracy:

  Exclusion 1 — SOURCE MISSING:   event has no source_url (Evidence Discipline 2026-05-19)
  Exclusion 2 — MACRO RETROSPECTIVE: expected driver = MACRO; historical signal breadth
                not reproducible from current asset_signals table
  Exclusion 3 — UNIVERSE GAP:     affected assets/sets not in coverage universe;
                UNKNOWN is correct engine behavior, not a miss

Accuracy is computed only over testable cases.

Run:
    DATABASE_URL=<public-url> python -m scripts.validate_driver_attribution
    railway run python -m scripts.validate_driver_attribution
"""
from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.models.asset import Asset
from backend.app.models.predictions import MarketEvent
from backend.app.services.driver_attribution_service import attribute_signal

_EXPECTED_DRIVER: dict[str, str] = {
    "INFLUENCER": "EVENT_DRIVEN",
    "TOURNAMENT": "EVENT_DRIVEN",
    "SUPPLY": "SUPPLY_SHOCK",
    "RELEASE": "MACRO",
}

_ACCEPTABLE_DRIVERS: dict[str, set[str]] = {
    "RELEASE": {"MACRO", "EVENT_DRIVEN"},
}

ExclusionType = Literal["NONE", "SOURCE_MISSING", "MACRO_RETROSPECTIVE", "UNIVERSE_GAP"]


def _find_sample_assets(
    db: Session, event: MarketEvent, limit: int = 2
) -> tuple[list[Asset], str]:
    """Return (assets, source) where source describes how they were found.

    source values:
      "EXPLICIT_UUID"  – resolved from affected_asset_ids
      "SET_MATCH"      – found via affected_set_ids matching assets table
      "FALLBACK_RANDOM"– last-resort fallback; assets are unrelated to event
      "NONE"           – no assets found at all
    """
    import uuid as _uuid

    asset_ids_raw = event.affected_asset_ids or []
    set_ids = event.affected_set_ids or []

    # Priority 1: explicit UUID match
    if asset_ids_raw:
        found: list[Asset] = []
        for aid in asset_ids_raw[:limit]:
            try:
                a = db.get(Asset, _uuid.UUID(str(aid)))
                if a:
                    found.append(a)
            except Exception:
                pass
        if found:
            return found, "EXPLICIT_UUID"

    # Priority 2: set-name match
    if set_ids:
        set_assets = db.scalars(
            select(Asset).where(Asset.set_name.in_(set_ids)).limit(limit)
        ).all()
        if set_assets:
            return list(set_assets), "SET_MATCH"

    # Priority 3: last-resort fallback (any pokemon card)
    fallback = db.scalars(
        select(Asset).where(Asset.game == "pokemon").limit(1)
    ).first()
    if fallback:
        return [fallback], "FALLBACK_RANDOM"

    return [], "NONE"


def _classify_exclusion(
    event: MarketEvent, asset_source: str
) -> tuple[ExclusionType, str]:
    """Return (exclusion_type, reason). 'NONE' means testable.

    Priority order:
      1. SOURCE_MISSING  — no source_url; excluded per Evidence Discipline
      2. MACRO_RETROSPECTIVE — expected driver is MACRO (RELEASE event type);
         historical signal breadth cannot be reproduced from current asset_signals
      3. UNIVERSE_GAP    — assets not in coverage universe; UNKNOWN is correct
    """
    if not event.source_url:
        return (
            "SOURCE_MISSING",
            "source_url not set — excluded per Evidence Discipline 2026-05-19; "
            "add authoritative URL to market_events row to make testable",
        )

    if event.event_type == "RELEASE" and not (event.affected_asset_ids or []):
        return (
            "MACRO_RETROSPECTIVE",
            "MACRO attribution requires set-wide signal breadth at moment of event; "
            "asset_signals reflects current state only — historical breadth not reproducible; "
            "validate forward-only via production observation",
        )

    if asset_source == "FALLBACK_RANDOM":
        return (
            "UNIVERSE_GAP",
            "affected_asset_ids resolved to 0 DB rows and affected_set_ids had no matching "
            "assets — harness fell back to unrelated asset; "
            "UNKNOWN is correct engine behavior for assets outside coverage universe",
        )

    if asset_source == "NONE":
        return (
            "UNIVERSE_GAP",
            "no assets found in coverage universe for this event",
        )

    return ("NONE", "")


def run_validation(db: Session) -> dict:
    """Run attribution engine with exclusion logic. Returns structured summary."""
    events = db.scalars(
        select(MarketEvent).order_by(MarketEvent.event_date.desc())
    ).all()

    testable: list[dict] = []
    excl_source: list[dict] = []
    excl_macro: list[dict] = []
    excl_universe: list[dict] = []

    for ev in events:
        expected = _EXPECTED_DRIVER.get(ev.event_type, "UNKNOWN")
        # RELEASE with specific cards in affected_asset_ids → Rule 4 (EVENT_DRIVEN), not MACRO
        if ev.event_type == "RELEASE" and ev.affected_asset_ids:
            expected = "EVENT_DRIVEN"
        acceptable_set = _ACCEPTABLE_DRIVERS.get(ev.event_type, {expected})

        sample_assets, asset_source = _find_sample_assets(db, ev, limit=2)

        excl_type, excl_reason = _classify_exclusion(ev, asset_source)

        window_days = ev.expected_window_days or 14
        reference_time = ev.event_date + timedelta(days=1)

        def _base(asset_name: str | None = None) -> dict:
            return {
                "event": ev.description,
                "event_type": ev.event_type,
                "event_date": str(ev.event_date.date()),
                "source_url": ev.source_url or "",
                "asset": asset_name or "—",
                "expected": expected,
                "actual": "—",
                "confidence": None,
                "pass": None,
                "reason": "",
                "excl_reason": excl_reason,
            }

        if excl_type == "SOURCE_MISSING":
            row = _base()
            row["reason"] = excl_reason
            excl_source.append(row)
            continue

        if excl_type == "MACRO_RETROSPECTIVE":
            asset_name = (
                f"{sample_assets[0].name} [{sample_assets[0].set_name}]"
                if sample_assets else "—"
            )
            row = _base(asset_name)
            row["reason"] = excl_reason
            excl_macro.append(row)
            continue

        if not sample_assets or excl_type == "UNIVERSE_GAP":
            asset_name = (
                f"{sample_assets[0].name} [{sample_assets[0].set_name}]"
                if sample_assets else "—"
            )
            row = _base(asset_name)
            row["reason"] = excl_reason
            excl_universe.append(row)
            continue

        # Testable — run the engine for each sample asset
        for asset in sample_assets:
            result = attribute_signal(
                db,
                asset_id=asset.id,
                signal_move_pct=Decimal("10"),
                signal_window_days=window_days,
                reference_time=reference_time,
            )
            passed = result.driver in acceptable_set
            row = _base(f"{asset.name} [{asset.set_name}]")
            row.update({
                "actual": result.driver,
                "confidence": round(result.confidence, 3),
                "pass": passed,
                "reason": (result.reason or "")[:150],
            })
            testable.append(row)

    # Compute testable accuracy
    total = len(testable)
    passes = sum(1 for r in testable if r["pass"])

    # Per-driver breakdown on testable cases
    driver_stats: dict[str, dict[str, int]] = {}
    for r in testable:
        d = r["expected"]
        if d not in driver_stats:
            driver_stats[d] = {"pass": 0, "total": 0}
        driver_stats[d]["total"] += 1
        if r["pass"]:
            driver_stats[d]["pass"] += 1

    return {
        "run_at": datetime.now(UTC).isoformat(),
        "testable": testable,
        "excl_source": excl_source,
        "excl_macro": excl_macro,
        "excl_universe": excl_universe,
        "total_testable": total,
        "passes": passes,
        "accuracy": passes / total if total else None,
        "driver_stats": driver_stats,
    }


def write_report(summary: dict, path: Path) -> None:
    """Write Gate 2 validation report with formal exclusion sections."""
    path.parent.mkdir(parents=True, exist_ok=True)
    run_at = summary["run_at"]
    total = summary["total_testable"]
    passes = summary["passes"]
    accuracy = summary["accuracy"]
    n_source = len(summary["excl_source"])
    n_macro = len(summary["excl_macro"])
    n_universe = len(summary["excl_universe"])

    def _row(r: dict, *, include_pass: bool = True) -> str:
        pass_col = ("✓" if r["pass"] else "✗") if include_pass and r["pass"] is not None else "—"
        conf = str(r["confidence"]) if r["confidence"] is not None else "—"
        url_display = f"[source]({r['source_url']})" if r["source_url"] else "—"
        return (
            f"| {r['event'][:80]} | {r['event_type']} | {r['event_date']} "
            f"| {url_display} | {r['asset'][:60]} | {r['expected']} "
            f"| {r['actual']} | {conf} | {pass_col} | {r['reason'][:100]} |"
        )

    _table_header = (
        "| Event | Type | Date | Source | Asset | Expected | Actual "
        "| Confidence | Pass | Reason |\n"
        "|---|---|---|---|---|---|---|---|---|---|"
    )

    lines = [
        "# Driver Attribution Validation — Gate 2",
        "",
        f"**Run at:** {run_at}",
        f"**DB:** production (junction.proxy.rlwy.net)",
        "",
        "---",
        "",
        "## Summary",
        "",
        f"**Testable cases:** {total}",
        f"**Accuracy (testable only):** "
        + (f"{passes}/{total} = {accuracy:.1%}" if accuracy is not None else "N/A — no testable cases"),
        "",
        "### Per-driver breakdown (testable cases only)",
        "",
        "| Expected Driver | Pass | Total | Accuracy |",
        "|---|---|---|---|",
    ]

    for driver, stats in sorted(summary["driver_stats"].items()):
        acc = stats["pass"] / stats["total"] if stats["total"] else 0
        lines.append(
            f"| {driver} | {stats['pass']} | {stats['total']} | {acc:.1%} |"
        )

    lines += [
        "",
        "### Excluded cases",
        "",
        f"| Category | Count | Reason |",
        f"|---|---|---|",
        f"| Source Missing | {n_source} | source_url not set — excluded per Evidence Discipline 2026-05-19 |",
        f"| MACRO Retrospective | {n_macro} | historical signal breadth not reproducible |",
        f"| Universe Gap | {n_universe} | affected assets/sets not in coverage universe |",
        "",
        "**Accuracy threshold:** TBD by Ivan based on these numbers.",
        "",
        "---",
        "",
        "## Testable Cases",
        "",
        _table_header,
    ]

    for r in summary["testable"]:
        lines.append(_row(r, include_pass=True))

    if not summary["testable"]:
        lines.append("| *No testable cases after exclusions* | — | — | — | — | — | — | — | — | — |")

    lines += [
        "",
        "---",
        "",
        "## Excluded — Source Missing",
        "",
        f"*{n_source} events excluded. Add authoritative source_url to `market_events` to make testable.*",
        "",
        _table_header,
    ]
    for r in summary["excl_source"]:
        lines.append(_row(r, include_pass=False))

    lines += [
        "",
        "---",
        "",
        "## Excluded — MACRO Retrospective",
        "",
        (
            f"*{n_macro} cases excluded. MACRO attribution checks set-wide signal breadth "
            "at the moment of attribution. The `asset_signals` table reflects the current "
            "state — it does not store snapshots of historical signal states. "
            "Retrospective MACRO validation requires time-travel queries; "
            "validate forward-only via production observation after Gate 4 enables the scheduler.*"
        ),
        "",
        _table_header,
    ]
    for r in summary["excl_macro"]:
        lines.append(_row(r, include_pass=False))

    lines += [
        "",
        "---",
        "",
        "## Excluded — Universe Gap",
        "",
        (
            f"*{n_universe} cases excluded. Affected assets/sets not tracked in the asset "
            "coverage universe (vintage cards, untracked sets, or broad events with no "
            "set affiliation). Engine returning UNKNOWN is correct behavior — it honestly "
            "reports uncertainty when the card is outside its data universe.*"
        ),
        "",
        _table_header,
    ]
    for r in summary["excl_universe"]:
        lines.append(_row(r, include_pass=False))

    lines += [
        "",
        "---",
        "",
        "## Evidence discipline",
        "",
        "- All event data sourced from `market_events` table.",
        "- `reference_time = event_date + 1d` simulates attribution firing one day after event.",
        "- `signal_move_pct = +10%` (synthetic positive move).",
        "- Cases excluded by SOURCE_MISSING remain excluded regardless of engine result.",
        "- Source URLs for all testable cases are embedded in the Source column above.",
        "",
        f"*Generated by `scripts/validate_driver_attribution.py` at {run_at}*",
    ]

    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url)

    print("Running driver attribution validation against market_events table…")
    with Session(engine) as db:
        summary = run_validation(db)

    total = summary["total_testable"]
    passes = summary["passes"]
    accuracy = summary["accuracy"]
    n_src = len(summary["excl_source"])
    n_mac = len(summary["excl_macro"])
    n_uni = len(summary["excl_universe"])

    print(f"\nTestable cases: {total}  (excl: {n_src} source-missing, {n_mac} MACRO, {n_uni} universe-gap)")
    if accuracy is not None:
        print(f"Accuracy: {passes}/{total} = {accuracy:.1%}")
    else:
        print("Accuracy: N/A (no testable cases)")

    print("\nPer-driver (testable):")
    for driver, stats in sorted(summary["driver_stats"].items()):
        acc = stats["pass"] / stats["total"] if stats["total"] else 0
        print(f"  {driver}: {stats['pass']}/{stats['total']} = {acc:.1%}")

    print("\nTestable results:")
    print(f"{'Event':<70} {'Expected':<14} {'Actual':<14} {'Conf':<8} {'Pass'}")
    print("-" * 120)
    for r in summary["testable"]:
        print(
            f"{r['event'][:70]:<70} {r['expected']:<14} {r['actual']:<14} "
            f"{str(r['confidence']):<8} {'PASS' if r['pass'] else 'FAIL'}"
        )

    report_path = Path(__file__).resolve().parents[1] / "validation_reports" / "driver_attribution_v1.md"
    write_report(summary, report_path)
    print(f"\nReport written to: {report_path}")
    print("\nGate 2 verdict: Ivan review required. See report for per-case breakdown.")


if __name__ == "__main__":
    main()
