from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from backend.app.core.price_sources import get_active_price_source_filter, get_primary_price_source
from backend.app.core.tracked_pools import (
    BASE_SET_POOL_KEY,
    HIGH_ACTIVITY_TRIAL_POOL_KEY,
    HIGH_ACTIVITY_V2_POOL_KEY,
    TRIAL_POOL_KEY,
    get_tracked_pokemon_pools,
)
from backend.app.db.session import SessionLocal
from backend.app.models.asset import Asset
from backend.app.models.price_history import PriceHistory
from backend.app.services.asset_tagging import (
    CHASE_TAG_LABEL,
    HIGH_ACTIVITY_TAG_LABEL,
    STANDARD_ACTIVITY_TAG_LABEL,
    STANDARD_TAG_LABEL,
    TAG_DIMENSION_LABELS,
    TAG_DIMENSION_ORDER,
    get_tag_value_sort_key,
)
from backend.app.services.diagnostics_summary_service import build_standardized_diagnostics_summary
from backend.app.services.data_health_service import (
    PoolHealthSnapshot,
    ProviderHealthSnapshot,
    TagHealthSnapshot,
)
from backend.app.services.data_health_service import get_data_health_report


def _format_count_ratio(count: int, total: int) -> str:
    return f"{count} of {total}"


def _format_row_change_ratio(percent: Decimal, changed_rows: int, comparable_rows: int) -> str:
    return f"{percent}% ({changed_rows}/{comparable_rows})"


def _render_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    widths = [
        max(len(str(row[index])) for row in [headers, *rows])
        for index in range(len(headers))
    ]
    separator = "-+-".join("-" * width for width in widths)

    def render_row(row: list[str]) -> str:
        return " | ".join(f"{cell:<{widths[index]}}" for index, cell in enumerate(row))

    return [render_row(headers), separator, *(render_row(row) for row in rows)]


def _get_movement_row_definitions():
    return [
        (
            "Assets with real history",
            lambda snapshot: _format_count_ratio(
                snapshot.assets_with_real_history,
                snapshot.total_assets,
            ),
        ),
        (
            "Average history depth",
            lambda snapshot: f"{snapshot.average_real_history_points_per_asset} rows/asset",
        ),
        (
            "Assets with price changes in last 24h",
            lambda snapshot: _format_count_ratio(
                snapshot.assets_with_price_change_last_24h,
                snapshot.assets_with_real_history,
            ),
        ),
        (
            "Assets with price changes in last 7d",
            lambda snapshot: _format_count_ratio(
                snapshot.assets_with_price_change_last_7d,
                snapshot.assets_with_real_history,
            ),
        ),
        (
            "Percent of comparable rows changed in last 24h",
            lambda snapshot: _format_row_change_ratio(
                snapshot.percent_recent_rows_changed_last_24h,
                snapshot.recent_rows_with_price_change_last_24h,
                snapshot.recent_comparable_rows_last_24h,
            ),
        ),
        (
            "Percent of comparable rows changed in last 7d",
            lambda snapshot: _format_row_change_ratio(
                snapshot.percent_recent_rows_changed_last_7d,
                snapshot.recent_rows_with_price_change_last_7d,
                snapshot.recent_comparable_rows_last_7d,
            ),
        ),
        (
            "Assets with no movement across full history",
            lambda snapshot: _format_count_ratio(
                snapshot.assets_with_no_price_movement_full_history,
                snapshot.assets_with_real_history,
            ),
        ),
        (
            "Assets whose latest two prices are unchanged",
            lambda snapshot: _format_count_ratio(
                snapshot.assets_with_unchanged_latest_price,
                snapshot.assets_with_real_history,
            ),
        ),
    ]
 

def _build_pool_comparison_table(pool_reports: list[PoolHealthSnapshot]) -> list[str]:
    headers = ["Metric", *[pool.label for pool in pool_reports]]
    row_definitions = _get_movement_row_definitions()
    rows = [
        [label, *[formatter(pool) for pool in pool_reports]]
        for label, formatter in row_definitions
    ]
    return _render_table(headers, rows)


def _format_provider_column(provider: ProviderHealthSnapshot) -> str:
    if provider.is_primary:
        return f"{provider.label} ({provider.slot}, primary)"
    return f"{provider.label} ({provider.slot})"


def _build_provider_comparison_table(provider_reports: list[ProviderHealthSnapshot]) -> list[str]:
    headers = ["Metric", *[_format_provider_column(provider) for provider in provider_reports]]
    row_definitions = _get_movement_row_definitions()
    rows = [
        [label, *[formatter(provider) for provider in provider_reports]]
        for label, formatter in row_definitions
    ]
    return _render_table(headers, rows)


def _build_provider_pool_comparison_sections(
    provider_reports: list[ProviderHealthSnapshot],
) -> list[tuple[str, list[str]]]:
    sections: list[tuple[str, list[str]]] = []
    if not provider_reports:
        return sections

    ordered_pool_keys = [pool.key for pool in provider_reports[0].pool_reports]
    row_definitions = _get_movement_row_definitions()
    headers = ["Metric", *[_format_provider_column(provider) for provider in provider_reports]]

    for pool_key in ordered_pool_keys:
        pool_label: str | None = None
        rows: list[list[str]] = []
        selected_pools: list[PoolHealthSnapshot | None] = []
        for provider in provider_reports:
            pool = _get_pool_by_key(provider.pool_reports, pool_key)
            if pool_label is None and pool is not None:
                pool_label = pool.label
            selected_pools.append(pool)

        if pool_label is None:
            continue

        for label, formatter in row_definitions:
            rows.append(
                [
                    label,
                    *[
                        formatter(pool) if pool is not None else "N/A"
                        for pool in selected_pools
                    ],
                ]
            )
        sections.append((pool_label, _render_table(headers, rows)))

    return sections


def _build_tag_movement_sections(
    tag_reports: list[TagHealthSnapshot],
) -> list[tuple[str, list[str]]]:
    grouped_reports: dict[str, list[TagHealthSnapshot]] = {}
    for report in tag_reports:
        grouped_reports.setdefault(report.dimension, []).append(report)

    sections: list[tuple[str, list[str]]] = []
    for dimension in [*TAG_DIMENSION_ORDER, *sorted(grouped_reports.keys())]:
        reports = grouped_reports.pop(dimension, None)
        if not reports:
            continue
        reports = sorted(
            reports,
            key=lambda report: get_tag_value_sort_key(report.dimension, report.tag_value),
        )
        headers = [
            "Tag",
            "Assets with real history",
            "Avg depth",
            "Changed 24h",
            "Changed 7d",
            "Row movement 24h",
            "Row movement 7d",
            "No movement full history",
            "Unchanged latest two",
        ]
        rows = [
            [
                report.tag_value,
                _format_count_ratio(report.assets_with_real_history, report.total_assets),
                f"{report.average_real_history_points_per_asset} rows/asset",
                _format_count_ratio(
                    report.assets_with_price_change_last_24h,
                    report.assets_with_real_history,
                ),
                _format_count_ratio(
                    report.assets_with_price_change_last_7d,
                    report.assets_with_real_history,
                ),
                _format_row_change_ratio(
                    report.percent_recent_rows_changed_last_24h,
                    report.recent_rows_with_price_change_last_24h,
                    report.recent_comparable_rows_last_24h,
                ),
                _format_row_change_ratio(
                    report.percent_recent_rows_changed_last_7d,
                    report.recent_rows_with_price_change_last_7d,
                    report.recent_comparable_rows_last_7d,
                ),
                _format_count_ratio(
                    report.assets_with_no_price_movement_full_history,
                    report.assets_with_real_history,
                ),
                _format_count_ratio(
                    report.assets_with_unchanged_latest_price,
                    report.assets_with_real_history,
                ),
            ]
            for report in reports
        ]
        sections.append(
            (
                TAG_DIMENSION_LABELS.get(dimension, reports[0].dimension_label),
                _render_table(headers, rows),
            )
        )
    return sections


def _safe_ratio(numerator: int, denominator: int) -> Decimal:
    if denominator <= 0:
        return Decimal("0")
    return Decimal(numerator) / Decimal(denominator)


def _get_tag_report(
    tag_reports: list[TagHealthSnapshot],
    dimension: str,
    tag_value: str,
) -> TagHealthSnapshot | None:
    return next(
        (
            report
            for report in tag_reports
            if report.dimension == dimension and report.tag_value == tag_value
        ),
        None,
    )


def _get_pool_by_key(
    pool_reports: list[PoolHealthSnapshot],
    key: str,
) -> PoolHealthSnapshot | None:
    return next((pool for pool in pool_reports if pool.key == key), None)


def _snapshot_activity_advantage(
    candidate: PoolHealthSnapshot | TagHealthSnapshot,
    baseline: PoolHealthSnapshot | TagHealthSnapshot,
) -> bool:
    candidate_changed_asset_share_24h = _safe_ratio(
        candidate.assets_with_price_change_last_24h,
        candidate.assets_with_real_history,
    )
    baseline_changed_asset_share_24h = _safe_ratio(
        baseline.assets_with_price_change_last_24h,
        baseline.assets_with_real_history,
    )
    candidate_changed_asset_share_7d = _safe_ratio(
        candidate.assets_with_price_change_last_7d,
        candidate.assets_with_real_history,
    )
    baseline_changed_asset_share_7d = _safe_ratio(
        baseline.assets_with_price_change_last_7d,
        baseline.assets_with_real_history,
    )
    candidate_no_movement_share = _safe_ratio(
        candidate.assets_with_no_price_movement_full_history,
        candidate.assets_with_real_history,
    )
    baseline_no_movement_share = _safe_ratio(
        baseline.assets_with_no_price_movement_full_history,
        baseline.assets_with_real_history,
    )
    candidate_unchanged_latest_share = _safe_ratio(
        candidate.assets_with_unchanged_latest_price,
        candidate.assets_with_real_history,
    )
    baseline_unchanged_latest_share = _safe_ratio(
        baseline.assets_with_unchanged_latest_price,
        baseline.assets_with_real_history,
    )

    comparison_wins = {
        "24h comparable-row change rate": (
            candidate.percent_recent_rows_changed_last_24h
            > baseline.percent_recent_rows_changed_last_24h
        ),
        "7d comparable-row change rate": (
            candidate.percent_recent_rows_changed_last_7d
            > baseline.percent_recent_rows_changed_last_7d
        ),
        "24h changed-asset share": candidate_changed_asset_share_24h
        > baseline_changed_asset_share_24h,
        "7d changed-asset share": candidate_changed_asset_share_7d
        > baseline_changed_asset_share_7d,
        "full-history no-movement share": candidate_no_movement_share
        < baseline_no_movement_share,
        "unchanged-latest share": candidate_unchanged_latest_share
        < baseline_unchanged_latest_share,
    }
    has_stronger_recent_movement = (
        comparison_wins["24h comparable-row change rate"]
        and comparison_wins["7d comparable-row change rate"]
    )
    return has_stronger_recent_movement and sum(comparison_wins.values()) >= 4


def _build_high_activity_trial_pool_summary(
    pool_reports: list[PoolHealthSnapshot],
) -> tuple[str, str]:
    base_pool = _get_pool_by_key(pool_reports, BASE_SET_POOL_KEY)
    trial_pool = _get_pool_by_key(pool_reports, TRIAL_POOL_KEY)
    high_activity_pool = _get_pool_by_key(pool_reports, HIGH_ACTIVITY_TRIAL_POOL_KEY)
    if base_pool is None or trial_pool is None or high_activity_pool is None:
        return (
            "insufficient",
            "High-Activity Trial vs pools: cannot compare yet because one or more pool snapshots are missing.",
        )

    comparison_depth_floor = max(
        base_pool.average_real_history_points_per_asset,
        trial_pool.average_real_history_points_per_asset,
    ) * Decimal("0.75")
    has_enough_recent_signal = (
        high_activity_pool.recent_comparable_rows_last_24h > 0
        and high_activity_pool.recent_comparable_rows_last_7d > 0
    )
    has_enough_depth = (
        high_activity_pool.assets_with_real_history > 0
        and high_activity_pool.average_real_history_points_per_asset >= comparison_depth_floor
    )
    beats_base = _snapshot_activity_advantage(high_activity_pool, base_pool)
    beats_trial = _snapshot_activity_advantage(high_activity_pool, trial_pool)

    if has_enough_recent_signal and has_enough_depth and beats_base and beats_trial:
        return (
            "positive",
            "High-Activity Trial vs pools: more active than Base Set and Scarlet & Violet 151 Trial.",
        )

    if not has_enough_recent_signal:
        return (
            "insufficient",
            "High-Activity Trial vs pools: not decision-grade yet because recent comparable rows are still too thin.",
        )

    if not has_enough_depth:
        return (
            "insufficient",
            "High-Activity Trial vs pools: not decision-grade yet because history depth is still too thin.",
        )

    if not beats_base and not beats_trial:
        return (
            "negative",
            "High-Activity Trial vs pools: not more active than Base Set and Scarlet & Violet 151 Trial.",
        )

    return (
        "mixed",
        "High-Activity Trial vs pools: mixed signal; it shows some movement advantages, but not enough to beat both baseline pools.",
    )


def _assess_tag_against_rest(
    candidate: TagHealthSnapshot | None,
    baseline: TagHealthSnapshot | None,
) -> str:
    if candidate is None or baseline is None:
        return "insufficient"

    has_enough_recent_signal = (
        candidate.recent_comparable_rows_last_24h > 0
        and candidate.recent_comparable_rows_last_7d > 0
    )
    comparison_depth_floor = baseline.average_real_history_points_per_asset * Decimal("0.75")
    has_enough_depth = (
        candidate.assets_with_real_history > 0
        and baseline.assets_with_real_history > 0
        and candidate.average_real_history_points_per_asset >= comparison_depth_floor
    )
    if not has_enough_recent_signal or not has_enough_depth:
        return "insufficient"

    if _snapshot_activity_advantage(candidate, baseline):
        return "positive"
    if _snapshot_activity_advantage(baseline, candidate):
        return "negative"
    return "mixed"


def _build_tag_segment_summary(
    tag_reports: list[TagHealthSnapshot],
) -> tuple[str, str]:
    chase_report = _get_tag_report(tag_reports, "collectible_chase", CHASE_TAG_LABEL)
    standard_report = _get_tag_report(tag_reports, "collectible_chase", STANDARD_TAG_LABEL)
    high_activity_report = _get_tag_report(
        tag_reports,
        "high_activity_candidate",
        HIGH_ACTIVITY_TAG_LABEL,
    )
    standard_activity_report = _get_tag_report(
        tag_reports,
        "high_activity_candidate",
        STANDARD_ACTIVITY_TAG_LABEL,
    )
    chase_status = _assess_tag_against_rest(chase_report, standard_report)
    high_activity_status = _assess_tag_against_rest(high_activity_report, standard_activity_report)

    if chase_status == "positive" and high_activity_status == "positive":
        return (
            "positive",
            "Tags vs rest: Collectible / Chase and High-Activity Candidate are both showing stronger movement than the rest.",
        )

    if chase_status == "negative" and high_activity_status == "negative":
        return (
            "negative",
            "Tags vs rest: Collectible / Chase and High-Activity Candidate are not showing stronger movement than the rest.",
        )

    if chase_status == "insufficient" or high_activity_status == "insufficient":
        return (
            "insufficient",
            "Tags vs rest: not decision-grade yet because Collectible / Chase and/or High-Activity Candidate still lack enough comparable rows or depth.",
        )

    if chase_status == "positive" and high_activity_status in {"mixed", "negative"}:
        qualifier = "not clearly stronger" if high_activity_status == "mixed" else "not stronger"
        return (
            "mixed_positive",
            f"Tags vs rest: Collectible / Chase is stronger, but High-Activity Candidate is {qualifier} than the rest.",
        )

    if high_activity_status == "positive" and chase_status in {"mixed", "negative"}:
        qualifier = "not clearly stronger" if chase_status == "mixed" else "not stronger"
        return (
            "mixed_positive",
            f"Tags vs rest: High-Activity Candidate is stronger, but Collectible / Chase is {qualifier} than the rest.",
        )

    if chase_status == "mixed" and high_activity_status == "mixed":
        return (
            "mixed",
            "Tags vs rest: Collectible / Chase and High-Activity Candidate show some movement advantages, but neither is clearly stronger than the rest.",
        )

    return (
        "mixed_negative",
        "Tags vs rest: Collectible / Chase and High-Activity Candidate are not showing stronger movement than the rest.",
    )


def _build_operator_decision_summary(
    pool_reports: list[PoolHealthSnapshot],
    tag_reports: list[TagHealthSnapshot],
) -> list[str]:
    pool_status, pool_line = _build_high_activity_trial_pool_summary(pool_reports)
    tag_status, tag_line = _build_tag_segment_summary(tag_reports)

    if pool_status == "positive" and tag_status in {"positive", "mixed_positive"}:
        recommendation_line = (
            "Recommendation: continue with the current provider and smarter pool selection."
        )
    elif pool_status == "negative" and tag_status in {"negative", "mixed_negative"}:
        recommendation_line = "Recommendation: prepare provider #2."
    elif pool_status == "insufficient" or tag_status == "insufficient":
        recommendation_line = (
            "Recommendation: keep running the current provider test before choosing between smarter selection and provider #2."
        )
    else:
        recommendation_line = (
            "Recommendation: evidence is mixed; keep running the current provider test before making the provider #2 call."
        )

    return [pool_line, tag_line, recommendation_line]


@dataclass(frozen=True)
class CardCoverageAuditSnapshot:
    card_id: str
    name: str
    external_id: str | None
    latest_price: Decimal | None
    real_history_points: int
    changed_rows_last_24h: int
    changed_rows_last_7d: int
    distinct_real_prices: int
    asset_match_count: int
    first_captured_at: datetime | None
    latest_captured_at: datetime | None
    fetch_consistent: bool
    history_depth_increasing: bool
    prices_ever_changed: bool
    weak_coverage_candidate: bool
    assessment: str
    note: str


def _coerce_datetime_to_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _get_tracked_pool(pool_key: str):
    return next((pool for pool in get_tracked_pokemon_pools() if pool.key == pool_key), None)


def _build_card_external_id_pattern(card_id: str) -> str:
    return f"pokemontcg:{card_id}:%"


def _load_card_coverage_audit(
    session,
    *,
    card_ids: list[str],
    source: str,
) -> list[CardCoverageAuditSnapshot]:
    raw_snapshots: list[dict[str, object]] = []

    for card_id in card_ids:
        asset_pattern = _build_card_external_id_pattern(card_id)
        matched_assets = session.execute(
            select(Asset)
            .where(Asset.external_id.like(asset_pattern))
            .order_by(Asset.external_id.asc())
        ).scalars().all()
        selected_asset = matched_assets[0] if matched_assets else None

        history_rows = []
        if selected_asset is not None:
            history_rows = session.execute(
                select(
                    PriceHistory.price,
                    PriceHistory.captured_at,
                )
                .where(
                    PriceHistory.asset_id == selected_asset.id,
                    PriceHistory.source == source,
                )
                .order_by(PriceHistory.captured_at.asc())
            ).all()

        changed_rows_last_24h = 0
        changed_rows_last_7d = 0
        distinct_real_prices = len({str(price) for price, _captured_at in history_rows})
        latest_price = history_rows[-1][0] if history_rows else None
        first_captured_at = _coerce_datetime_to_utc(history_rows[0][1]) if history_rows else None
        latest_captured_at = _coerce_datetime_to_utc(history_rows[-1][1]) if history_rows else None
        cutoff_24h = datetime.now(UTC) - timedelta(hours=24)
        cutoff_7d = datetime.now(UTC) - timedelta(days=7)
        previous_price = None

        for price, captured_at in history_rows:
            captured_at = _coerce_datetime_to_utc(captured_at)
            if previous_price is not None and captured_at is not None and price != previous_price:
                if captured_at >= cutoff_24h:
                    changed_rows_last_24h += 1
                if captured_at >= cutoff_7d:
                    changed_rows_last_7d += 1
            previous_price = price

        raw_snapshots.append(
            {
                "card_id": card_id,
                "name": selected_asset.name if selected_asset is not None else card_id,
                "external_id": selected_asset.external_id if selected_asset is not None else None,
                "latest_price": latest_price,
                "real_history_points": len(history_rows),
                "changed_rows_last_24h": changed_rows_last_24h,
                "changed_rows_last_7d": changed_rows_last_7d,
                "distinct_real_prices": distinct_real_prices,
                "asset_match_count": len(matched_assets),
                "first_captured_at": first_captured_at,
                "latest_captured_at": latest_captured_at,
            }
        )

    latest_timestamps = [
        snapshot["latest_captured_at"]
        for snapshot in raw_snapshots
        if snapshot["latest_captured_at"] is not None
    ]
    cohort_latest = max(latest_timestamps) if latest_timestamps else None
    max_history_points = max(
        (int(snapshot["real_history_points"]) for snapshot in raw_snapshots),
        default=0,
    )

    audits: list[CardCoverageAuditSnapshot] = []
    for snapshot in raw_snapshots:
        real_history_points = int(snapshot["real_history_points"])
        latest_captured_at = snapshot["latest_captured_at"]
        asset_match_count = int(snapshot["asset_match_count"])
        fetch_consistent = (
            asset_match_count == 1
            and real_history_points > 0
            and latest_captured_at is not None
            and cohort_latest is not None
            and (cohort_latest - latest_captured_at) <= timedelta(hours=2)
            and real_history_points >= max(max_history_points - 2, 1)
        )
        history_depth_increasing = (
            fetch_consistent
            and real_history_points >= 8
            and snapshot["first_captured_at"] is not None
            and latest_captured_at is not None
            and latest_captured_at > snapshot["first_captured_at"]
        )
        prices_ever_changed = int(snapshot["distinct_real_prices"]) > 1
        weak_coverage_candidate = (
            asset_match_count != 1
            or real_history_points == 0
            or not fetch_consistent
            or not history_depth_increasing
        )

        if asset_match_count == 0:
            assessment = "Coverage watch"
            note = "No asset has been created for this card id yet."
        elif asset_match_count > 1:
            assessment = "Coverage watch"
            note = "Multiple assets match this card id, so canonical identity is not clean."
        elif weak_coverage_candidate:
            assessment = "Coverage watch"
            note = "History is present but still too stale or too shallow to trust coverage."
        elif prices_ever_changed:
            assessment = "Healthy / movement observed"
            note = (
                f"Observed changes: 24h={snapshot['changed_rows_last_24h']}, "
                f"7d={snapshot['changed_rows_last_7d']}, "
                f"distinct_prices={snapshot['distinct_real_prices']}."
            )
        else:
            assessment = "Healthy / no movement yet"
            note = "Fetch and depth look healthy; this card has simply stayed flat so far."

        audits.append(
            CardCoverageAuditSnapshot(
                card_id=str(snapshot["card_id"]),
                name=str(snapshot["name"]),
                external_id=snapshot["external_id"],
                latest_price=snapshot["latest_price"],
                real_history_points=real_history_points,
                changed_rows_last_24h=int(snapshot["changed_rows_last_24h"]),
                changed_rows_last_7d=int(snapshot["changed_rows_last_7d"]),
                distinct_real_prices=int(snapshot["distinct_real_prices"]),
                asset_match_count=asset_match_count,
                first_captured_at=snapshot["first_captured_at"],
                latest_captured_at=latest_captured_at,
                fetch_consistent=fetch_consistent,
                history_depth_increasing=history_depth_increasing,
                prices_ever_changed=prices_ever_changed,
                weak_coverage_candidate=weak_coverage_candidate,
                assessment=assessment,
                note=note,
            )
        )

    return audits


def _build_high_activity_definition_review_lines() -> list[str]:
    high_activity_pool = _get_tracked_pool(HIGH_ACTIVITY_TRIAL_POOL_KEY)
    high_activity_v2_pool = _get_tracked_pool(HIGH_ACTIVITY_V2_POOL_KEY)
    if high_activity_pool is None or high_activity_v2_pool is None:
        return []

    return [
        (
            f"Current High-Activity Trial: {len(high_activity_pool.card_ids)} explicit cards "
            "from the contiguous sv8pt5-148..180 premium slice."
        ),
        (
            "Current High-Activity Candidate tag: cards inside High-Activity Trial plus any "
            "modern Chase / Collectible card."
        ),
        (
            f"Proposed High-Activity v2: {len(high_activity_v2_pool.card_ids)} explicit sv8pt5 "
            "single-card raws focused on the most market-relevant names."
        ),
    ]


def _build_high_activity_v2_card_lines(
    coverage_audits: list[CardCoverageAuditSnapshot],
) -> list[str]:
    return [
        (
            f"{audit.card_id} - {audit.name} "
            f"(latest={audit.latest_price} USD, "
            f"rows={audit.real_history_points}, "
            f"changed_7d={audit.changed_rows_last_7d})"
        )
        for audit in coverage_audits
    ]


def _build_provider_coverage_audit_summary_lines(
    coverage_audits: list[CardCoverageAuditSnapshot],
) -> list[str]:
    total_cards = len(coverage_audits)
    consistent_fetch = sum(1 for audit in coverage_audits if audit.fetch_consistent)
    increasing_depth = sum(1 for audit in coverage_audits if audit.history_depth_increasing)
    prices_changed = sum(1 for audit in coverage_audits if audit.prices_ever_changed)
    changed_last_24h = sum(1 for audit in coverage_audits if audit.changed_rows_last_24h > 0)
    weak_coverage = sum(1 for audit in coverage_audits if audit.weak_coverage_candidate)
    flat_but_healthy = sum(
        1
        for audit in coverage_audits
        if (not audit.weak_coverage_candidate and not audit.prices_ever_changed)
    )
    return [
        f"Consistent provider fetches: {consistent_fetch} of {total_cards}",
        f"History depth still increasing: {increasing_depth} of {total_cards}",
        f"Cards with any observed real price change: {prices_changed} of {total_cards}",
        f"Cards with a real price change in the last 24h: {changed_last_24h} of {total_cards}",
        f"Weak coverage candidates: {weak_coverage} of {total_cards}",
        f"No market movement observed despite healthy coverage: {flat_but_healthy} of {total_cards}",
    ]


def _build_provider_coverage_audit_table(
    coverage_audits: list[CardCoverageAuditSnapshot],
) -> list[str]:
    headers = ["Card", "Rows", "Fetch", "Depth", "Price changes", "Assessment"]
    rows = [
        [
            f"{audit.name} [{audit.card_id}]",
            str(audit.real_history_points),
            "Yes" if audit.fetch_consistent else "No",
            "Growing" if audit.history_depth_increasing else "Thin/Stale",
            (
                f"24h {audit.changed_rows_last_24h} / "
                f"7d {audit.changed_rows_last_7d} / "
                f"distinct {audit.distinct_real_prices}"
            ),
            audit.assessment,
        ]
        for audit in coverage_audits
    ]
    return _render_table(headers, rows)


def _build_current_provider_decision_note(
    pool_reports: list[PoolHealthSnapshot],
    coverage_audits: list[CardCoverageAuditSnapshot],
) -> list[str]:
    high_activity_pool = _get_pool_by_key(pool_reports, HIGH_ACTIVITY_TRIAL_POOL_KEY)
    high_activity_v2_pool = _get_pool_by_key(pool_reports, HIGH_ACTIVITY_V2_POOL_KEY)
    total_cards = len(coverage_audits)
    weak_coverage = sum(1 for audit in coverage_audits if audit.weak_coverage_candidate)
    prices_changed = sum(1 for audit in coverage_audits if audit.prices_ever_changed)

    note_lines = [
        (
            "Current-provider diagnosis: pool design looks weaker than provider coverage; "
            f"{prices_changed} of {total_cards} High-Activity v2 cards already show real price "
            f"changes, and {weak_coverage} of {total_cards} look weak on coverage."
        )
    ]

    if high_activity_pool is not None and high_activity_v2_pool is not None:
        note_lines.append(
            (
                "High-Activity v2 vs current slice: "
                f"no-movement cards {high_activity_v2_pool.assets_with_no_price_movement_full_history}"
                f"/{high_activity_v2_pool.assets_with_real_history} vs "
                f"{high_activity_pool.assets_with_no_price_movement_full_history}"
                f"/{high_activity_pool.assets_with_real_history}; "
                f"changed-in-7d {high_activity_v2_pool.assets_with_price_change_last_7d}"
                f"/{high_activity_v2_pool.assets_with_real_history} vs "
                f"{high_activity_pool.assets_with_price_change_last_7d}"
                f"/{high_activity_pool.assets_with_real_history}; "
                f"row-change rate 7d {high_activity_v2_pool.percent_recent_rows_changed_last_7d}% "
                f"vs {high_activity_pool.percent_recent_rows_changed_last_7d}%."
            )
        )

    note_lines.append(
        "Recommendation: replace the current High-Activity Trial with High-Activity v2 and keep observing before any provider #2 decision."
    )
    return note_lines


def print_price_history_summary(limit: int = 30) -> None:
    with SessionLocal() as session:
        primary_source = get_primary_price_source()
        report = get_data_health_report(session)
        diagnostics_summary = build_standardized_diagnostics_summary(session)
        source_filter = get_active_price_source_filter(session)
        high_activity_v2_pool = _get_tracked_pool(HIGH_ACTIVITY_V2_POOL_KEY)
        high_activity_v2_audits = (
            _load_card_coverage_audit(
                session,
                card_ids=high_activity_v2_pool.card_ids,
                source=primary_source,
            )
            if high_activity_v2_pool is not None
            else []
        )
        print("Tracked Pokemon data health:")
        print(f"- Active price source: {primary_source}")
        print(f"- Total assets: {report.total_assets}")
        print(f"- Assets with real non-sample history: {report.assets_with_real_history}")
        print(f"- Assets without real history: {report.assets_without_real_history}")
        print(f"- Average real history points per asset: {report.average_real_history_points_per_asset}")
        print(f"- Assets with fewer than 3 real points: {report.assets_with_fewer_than_3_real_points}")
        print(f"- Assets with fewer than 5 real points: {report.assets_with_fewer_than_5_real_points}")
        print(f"- Assets with fewer than 8 real points: {report.assets_with_fewer_than_8_real_points}")
        print(f"- Recent real price rows added in the last 24h: {report.recent_real_price_rows_last_24h}")
        print(f"- Recent real price rows added in the last 7d: {report.recent_real_price_rows_last_7d}")
        print(f"- Assets with at least one real price change in the last 24h: {report.assets_with_price_change_last_24h}")
        print(f"- Assets with at least one real price change in the last 7d: {report.assets_with_price_change_last_7d}")
        print(f"- Recent comparable rows in the last 24h: {report.recent_comparable_rows_last_24h}")
        print(f"- Recent rows with price change in the last 24h: {report.recent_rows_with_price_change_last_24h}")
        print(f"- Percent of recent comparable rows that changed price in the last 24h: {report.percent_recent_rows_changed_last_24h}%")
        print(f"- Recent comparable rows in the last 7d: {report.recent_comparable_rows_last_7d}")
        print(f"- Recent rows with price change in the last 7d: {report.recent_rows_with_price_change_last_7d}")
        print(f"- Percent of recent comparable rows that changed price in the last 7d: {report.percent_recent_rows_changed_last_7d}%")
        print(f"- Assets with no observed price movement across full real history: {report.assets_with_no_price_movement_full_history}")
        print(f"- Assets whose latest two real prices are unchanged: {report.assets_with_unchanged_latest_price}")
        print(f"- Average recent rows per asset in the last 24h: {report.average_recent_rows_per_asset_last_24h}")
        print(f"- Average recent rows per asset in the last 7d: {report.average_recent_rows_per_asset_last_7d}")
        print(f"- Average changed rows per asset in the last 24h: {report.average_changed_rows_per_asset_last_24h}")
        print(f"- Average changed rows per asset in the last 7d: {report.average_changed_rows_per_asset_last_7d}")
        rows_per_change_24h = report.rows_per_recent_price_change_last_24h or "N/A"
        rows_per_change_7d = report.rows_per_recent_price_change_last_7d or "N/A"
        print(f"- Comparable rows per observed change in the last 24h: {rows_per_change_24h}")
        print(f"- Comparable rows per observed change in the last 7d: {rows_per_change_7d}")
        if report.pool_reports:
            print("- Pool comparison:")
            for line in _build_pool_comparison_table(report.pool_reports):
                print(f"  {line}")
        if report.tag_reports:
            for dimension_label, lines in _build_tag_movement_sections(report.tag_reports):
                print(f"- Tag movement summary [{dimension_label}]:")
                for line in lines:
                    print(f"  {line}")
        if report.pool_reports or report.tag_reports:
            print("- Decision summary:")
            smart_pool = diagnostics_summary["smart_pool"]
            observation_stage = diagnostics_summary["observation_stage"]
            print(f"  - {smart_pool['headline']}")
            print(f"  - {smart_pool['summary']}")
            for line in smart_pool["comparison_lines"]:
                print(f"  - {line}")
            print(f"  - {smart_pool['recommendation']}")
            print(
                "  - Observation stage: "
                f"logged={observation_stage['observations_logged']}, "
                f"matched={observation_stage['observations_matched']}, "
                f"unmatched={observation_stage['observations_unmatched']}, "
                f"requires_review={observation_stage['observations_require_review']}"
            )
        definition_review_lines = _build_high_activity_definition_review_lines()
        if definition_review_lines:
            print("- High-activity definition review:")
            for line in definition_review_lines:
                print(f"  - {line}")
        if high_activity_v2_audits:
            print("- Proposed High-Activity v2 cards:")
            for line in _build_high_activity_v2_card_lines(high_activity_v2_audits):
                print(f"  - {line}")
            print("- Provider coverage audit [High-Activity v2]:")
            for line in _build_provider_coverage_audit_summary_lines(high_activity_v2_audits):
                print(f"  - {line}")
            for line in _build_provider_coverage_audit_table(high_activity_v2_audits):
                print(f"  {line}")
            print("- Current-provider decision note:")
            for line in _build_current_provider_decision_note(
                report.pool_reports,
                high_activity_v2_audits,
            ):
                print(f"  - {line}")
        if len(report.provider_reports) > 1:
            print("- Provider comparison:")
            for line in _build_provider_comparison_table(report.provider_reports):
                print(f"  {line}")
            for pool_label, lines in _build_provider_pool_comparison_sections(report.provider_reports):
                print(f"- Provider comparison by pool [{pool_label}]:")
                for line in lines:
                    print(f"  {line}")
        if report.low_coverage_assets:
            print("- Lowest-coverage tracked assets:")
            for item in report.low_coverage_assets:
                latest = item.latest_captured_at.isoformat() if item.latest_captured_at else "<none>"
                print(
                    f"  - {item.name} [{item.external_id}] "
                    f"rows={item.real_history_points} latest={latest}"
                )
        if report.unchanged_latest_assets:
            print("- Sample unchanged latest assets: " + ", ".join(report.unchanged_latest_assets))
        if report.high_activity_assets:
            print("- High-activity asset candidates:")
            for item in report.high_activity_assets:
                latest = item.latest_captured_at.isoformat() if item.latest_captured_at else "<none>"
                print(
                    f"  - {item.name} [{item.external_id}] "
                    f"changed_24h={item.changed_rows_last_24h} "
                    f"changed_7d={item.changed_rows_last_7d} "
                    f"rows_7d={item.rows_last_7d} "
                    f"distinct_prices={item.distinct_real_prices} "
                    f"latest={latest}"
                )
        else:
            print("- High-activity asset candidates: none detected yet")
        if report.low_activity_assets:
            print("- Low-activity asset candidates:")
            for item in report.low_activity_assets:
                latest = item.latest_captured_at.isoformat() if item.latest_captured_at else "<none>"
                print(
                    f"  - {item.name} [{item.external_id}] "
                    f"changed_24h={item.changed_rows_last_24h} "
                    f"changed_7d={item.changed_rows_last_7d} "
                    f"rows_7d={item.rows_last_7d} "
                    f"distinct_prices={item.distinct_real_prices} "
                    f"latest={latest}"
                )

        print("Source totals:")
        source_rows = session.execute(
            select(
                PriceHistory.source,
                func.count(PriceHistory.id).label("row_count"),
            )
            .group_by(PriceHistory.source)
            .order_by(PriceHistory.source.asc())
        ).all()
        for source, row_count in source_rows:
            print(f"- {source}: {row_count}")

        print("\nPer-asset non-sample summary:")
        asset_rows = session.execute(
            select(
                Asset.name,
                Asset.external_id,
                PriceHistory.source,
                func.count(PriceHistory.id).label("row_count"),
                func.min(PriceHistory.captured_at).label("first_captured_at"),
                func.max(PriceHistory.captured_at).label("latest_captured_at"),
            )
            .join(PriceHistory, PriceHistory.asset_id == Asset.id)
            .where(source_filter)
            .group_by(Asset.name, Asset.external_id, PriceHistory.source)
            .order_by(func.max(PriceHistory.captured_at).desc(), Asset.name.asc())
            .limit(limit)
        ).all()
        for name, external_id, source, row_count, first_captured_at, latest_captured_at in asset_rows:
            print(
                f"- {name} [{external_id}] source={source} rows={row_count} "
                f"first={first_captured_at.isoformat()} latest={latest_captured_at.isoformat()}"
            )

        print("\nMost recent non-sample rows:")
        recent_rows = session.execute(
            select(
                Asset.name,
                PriceHistory.source,
                PriceHistory.price,
                PriceHistory.currency,
                PriceHistory.captured_at,
            )
            .join(PriceHistory, PriceHistory.asset_id == Asset.id)
            .where(source_filter)
            .order_by(PriceHistory.captured_at.desc(), Asset.name.asc())
            .limit(10)
        ).all()
        for name, source, price, currency, captured_at in recent_rows:
            print(f"- {captured_at.isoformat()} | {name} | {price} {currency} | source={source}")


if __name__ == "__main__":
    print_price_history_summary()
