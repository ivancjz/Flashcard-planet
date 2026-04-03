from __future__ import annotations

from decimal import Decimal
from unittest import TestCase

from backend.app.core.tracked_pools import (
    BASE_SET_POOL_KEY,
    HIGH_ACTIVITY_TRIAL_POOL_KEY,
    TRIAL_POOL_KEY,
)
from backend.app.services.data_health_service import (
    PoolHealthSnapshot,
    ProviderHealthSnapshot,
    TagHealthSnapshot,
)
from scripts.price_history_summary import (
    CardCoverageAuditSnapshot,
    _build_current_provider_decision_note,
    _build_high_activity_trial_pool_summary,
    _build_operator_decision_summary,
    _build_pool_comparison_table,
    _build_provider_comparison_table,
    _build_provider_pool_comparison_sections,
    _build_tag_segment_summary,
    _build_tag_movement_sections,
)


def make_pool(
    *,
    key: str,
    label: str,
    total_assets: int,
    assets_with_real_history: int,
    average_depth: str,
    changed_assets_24h: int,
    changed_assets_7d: int,
    comparable_rows_24h: int,
    changed_rows_24h: int,
    comparable_rows_7d: int,
    changed_rows_7d: int,
    changed_pct_24h: str,
    changed_pct_7d: str,
    no_movement_assets: int,
    unchanged_latest_assets: int,
) -> PoolHealthSnapshot:
    return PoolHealthSnapshot(
        key=key,
        label=label,
        asset_external_id_patterns=(f"{key}-%",),
        total_assets=total_assets,
        assets_with_real_history=assets_with_real_history,
        assets_without_real_history=max(total_assets - assets_with_real_history, 0),
        average_real_history_points_per_asset=Decimal(average_depth),
        assets_with_fewer_than_3_real_points=0,
        assets_with_fewer_than_5_real_points=0,
        assets_with_fewer_than_8_real_points=0,
        recent_real_price_rows_last_24h=comparable_rows_24h + assets_with_real_history,
        recent_real_price_rows_last_7d=comparable_rows_7d + assets_with_real_history,
        recent_comparable_rows_last_24h=comparable_rows_24h,
        recent_rows_with_price_change_last_24h=changed_rows_24h,
        percent_recent_rows_changed_last_24h=Decimal(changed_pct_24h),
        recent_comparable_rows_last_7d=comparable_rows_7d,
        recent_rows_with_price_change_last_7d=changed_rows_7d,
        percent_recent_rows_changed_last_7d=Decimal(changed_pct_7d),
        assets_with_price_change_last_24h=changed_assets_24h,
        assets_with_price_change_last_7d=changed_assets_7d,
        assets_with_no_price_movement_full_history=no_movement_assets,
        assets_with_unchanged_latest_price=unchanged_latest_assets,
        average_recent_rows_per_asset_last_24h=Decimal("0.00"),
        average_recent_rows_per_asset_last_7d=Decimal("0.00"),
        average_changed_rows_per_asset_last_24h=Decimal("0.00"),
        average_changed_rows_per_asset_last_7d=Decimal("0.00"),
        rows_per_recent_price_change_last_24h=Decimal("0.00") if changed_rows_24h else None,
        rows_per_recent_price_change_last_7d=Decimal("0.00") if changed_rows_7d else None,
    )


def make_provider(
    *,
    slot: str,
    source: str,
    label: str,
    is_primary: bool,
    total_assets: int,
    assets_with_real_history: int,
    average_depth: str,
    changed_assets_24h: int,
    changed_assets_7d: int,
    comparable_rows_24h: int,
    changed_rows_24h: int,
    comparable_rows_7d: int,
    changed_rows_7d: int,
    changed_pct_24h: str,
    changed_pct_7d: str,
    no_movement_assets: int,
    unchanged_latest_assets: int,
    pool_reports: list[PoolHealthSnapshot],
) -> ProviderHealthSnapshot:
    return ProviderHealthSnapshot(
        slot=slot,
        source=source,
        label=label,
        is_primary=is_primary,
        total_assets=total_assets,
        assets_with_real_history=assets_with_real_history,
        assets_without_real_history=max(total_assets - assets_with_real_history, 0),
        average_real_history_points_per_asset=Decimal(average_depth),
        assets_with_fewer_than_3_real_points=0,
        assets_with_fewer_than_5_real_points=0,
        assets_with_fewer_than_8_real_points=0,
        recent_real_price_rows_last_24h=comparable_rows_24h + assets_with_real_history,
        recent_real_price_rows_last_7d=comparable_rows_7d + assets_with_real_history,
        recent_comparable_rows_last_24h=comparable_rows_24h,
        recent_rows_with_price_change_last_24h=changed_rows_24h,
        percent_recent_rows_changed_last_24h=Decimal(changed_pct_24h),
        recent_comparable_rows_last_7d=comparable_rows_7d,
        recent_rows_with_price_change_last_7d=changed_rows_7d,
        percent_recent_rows_changed_last_7d=Decimal(changed_pct_7d),
        assets_with_price_change_last_24h=changed_assets_24h,
        assets_with_price_change_last_7d=changed_assets_7d,
        assets_with_no_price_movement_full_history=no_movement_assets,
        assets_with_unchanged_latest_price=unchanged_latest_assets,
        average_recent_rows_per_asset_last_24h=Decimal("0.00"),
        average_recent_rows_per_asset_last_7d=Decimal("0.00"),
        average_changed_rows_per_asset_last_24h=Decimal("0.00"),
        average_changed_rows_per_asset_last_7d=Decimal("0.00"),
        rows_per_recent_price_change_last_24h=Decimal("0.00") if changed_rows_24h else None,
        rows_per_recent_price_change_last_7d=Decimal("0.00") if changed_rows_7d else None,
        pool_reports=pool_reports,
    )


def make_tag_report(
    *,
    dimension: str,
    dimension_label: str,
    tag_value: str,
    total_assets: int,
    assets_with_real_history: int,
    average_depth: str,
    changed_assets_24h: int,
    changed_assets_7d: int,
    comparable_rows_24h: int,
    changed_rows_24h: int,
    comparable_rows_7d: int,
    changed_rows_7d: int,
    changed_pct_24h: str,
    changed_pct_7d: str,
    no_movement_assets: int,
    unchanged_latest_assets: int,
) -> TagHealthSnapshot:
    return TagHealthSnapshot(
        dimension=dimension,
        dimension_label=dimension_label,
        tag_value=tag_value,
        total_assets=total_assets,
        assets_with_real_history=assets_with_real_history,
        average_real_history_points_per_asset=Decimal(average_depth),
        assets_with_price_change_last_24h=changed_assets_24h,
        assets_with_price_change_last_7d=changed_assets_7d,
        recent_comparable_rows_last_24h=comparable_rows_24h,
        recent_rows_with_price_change_last_24h=changed_rows_24h,
        percent_recent_rows_changed_last_24h=Decimal(changed_pct_24h),
        recent_comparable_rows_last_7d=comparable_rows_7d,
        recent_rows_with_price_change_last_7d=changed_rows_7d,
        percent_recent_rows_changed_last_7d=Decimal(changed_pct_7d),
        assets_with_no_price_movement_full_history=no_movement_assets,
        assets_with_unchanged_latest_price=unchanged_latest_assets,
    )


def make_card_audit(
    *,
    card_id: str,
    name: str,
    rows: int,
    changed_rows_24h: int,
    changed_rows_7d: int,
    distinct_prices: int,
    weak_coverage_candidate: bool,
    assessment: str,
) -> CardCoverageAuditSnapshot:
    return CardCoverageAuditSnapshot(
        card_id=card_id,
        name=name,
        external_id=f"pokemontcg:{card_id}:holofoil",
        latest_price=Decimal("100.00"),
        real_history_points=rows,
        changed_rows_last_24h=changed_rows_24h,
        changed_rows_last_7d=changed_rows_7d,
        distinct_real_prices=distinct_prices,
        asset_match_count=1,
        first_captured_at=None,
        latest_captured_at=None,
        fetch_consistent=not weak_coverage_candidate,
        history_depth_increasing=not weak_coverage_candidate,
        prices_ever_changed=(distinct_prices > 1),
        weak_coverage_candidate=weak_coverage_candidate,
        assessment=assessment,
        note=assessment,
    )


class PriceHistorySummaryTests(TestCase):
    def test_pool_comparison_table_shows_side_by_side_metrics(self):
        base_pool = make_pool(
            key=BASE_SET_POOL_KEY,
            label="Base Set",
            total_assets=69,
            assets_with_real_history=60,
            average_depth="8.50",
            changed_assets_24h=6,
            changed_assets_7d=18,
            comparable_rows_24h=30,
            changed_rows_24h=3,
            comparable_rows_7d=120,
            changed_rows_7d=18,
            changed_pct_24h="10.00",
            changed_pct_7d="15.00",
            no_movement_assets=21,
            unchanged_latest_assets=28,
        )
        trial_pool = make_pool(
            key=TRIAL_POOL_KEY,
            label="Scarlet & Violet 151 Trial",
            total_assets=25,
            assets_with_real_history=20,
            average_depth="9.25",
            changed_assets_24h=8,
            changed_assets_7d=12,
            comparable_rows_24h=22,
            changed_rows_24h=6,
            comparable_rows_7d=80,
            changed_rows_7d=20,
            changed_pct_24h="27.27",
            changed_pct_7d="25.00",
            no_movement_assets=4,
            unchanged_latest_assets=6,
        )
        high_activity_pool = make_pool(
            key=HIGH_ACTIVITY_TRIAL_POOL_KEY,
            label="High-Activity Trial",
            total_assets=33,
            assets_with_real_history=28,
            average_depth="9.90",
            changed_assets_24h=12,
            changed_assets_7d=18,
            comparable_rows_24h=26,
            changed_rows_24h=8,
            comparable_rows_7d=100,
            changed_rows_7d=30,
            changed_pct_24h="30.77",
            changed_pct_7d="30.00",
            no_movement_assets=3,
            unchanged_latest_assets=5,
        )

        lines = _build_pool_comparison_table([base_pool, trial_pool, high_activity_pool])

        self.assertIn("Metric", lines[0])
        self.assertIn("Base Set", lines[0])
        self.assertIn("Scarlet & Violet 151 Trial", lines[0])
        self.assertIn("High-Activity Trial", lines[0])
        self.assertTrue(
            any(
                "Assets with real history" in line
                and "60 of 69" in line
                and "20 of 25" in line
                and "28 of 33" in line
                for line in lines
            )
        )
        self.assertTrue(
            any(
                "Percent of comparable rows changed in last 24h" in line
                and "10.00% (3/30)" in line
                and "27.27% (6/22)" in line
                and "30.77% (8/26)" in line
                for line in lines
            )
        )

    def test_provider_comparison_helpers_are_ready_for_future_multi_provider_runs(self):
        provider_1_pools = [
            make_pool(
                key=BASE_SET_POOL_KEY,
                label="Base Set",
                total_assets=69,
                assets_with_real_history=60,
                average_depth="8.50",
                changed_assets_24h=6,
                changed_assets_7d=18,
                comparable_rows_24h=30,
                changed_rows_24h=3,
                comparable_rows_7d=120,
                changed_rows_7d=18,
                changed_pct_24h="10.00",
                changed_pct_7d="15.00",
                no_movement_assets=21,
                unchanged_latest_assets=28,
            ),
            make_pool(
                key=HIGH_ACTIVITY_TRIAL_POOL_KEY,
                label="High-Activity Trial",
                total_assets=33,
                assets_with_real_history=28,
                average_depth="9.90",
                changed_assets_24h=12,
                changed_assets_7d=18,
                comparable_rows_24h=26,
                changed_rows_24h=8,
                comparable_rows_7d=100,
                changed_rows_7d=30,
                changed_pct_24h="30.77",
                changed_pct_7d="30.00",
                no_movement_assets=3,
                unchanged_latest_assets=5,
            ),
        ]
        provider_2_pools = [
            make_pool(
                key=BASE_SET_POOL_KEY,
                label="Base Set",
                total_assets=69,
                assets_with_real_history=58,
                average_depth="8.10",
                changed_assets_24h=8,
                changed_assets_7d=20,
                comparable_rows_24h=32,
                changed_rows_24h=5,
                comparable_rows_7d=126,
                changed_rows_7d=24,
                changed_pct_24h="15.63",
                changed_pct_7d="19.05",
                no_movement_assets=18,
                unchanged_latest_assets=24,
            ),
            make_pool(
                key=HIGH_ACTIVITY_TRIAL_POOL_KEY,
                label="High-Activity Trial",
                total_assets=33,
                assets_with_real_history=29,
                average_depth="10.20",
                changed_assets_24h=18,
                changed_assets_7d=22,
                comparable_rows_24h=28,
                changed_rows_24h=12,
                comparable_rows_7d=108,
                changed_rows_7d=36,
                changed_pct_24h="42.86",
                changed_pct_7d="33.33",
                no_movement_assets=2,
                unchanged_latest_assets=4,
            ),
        ]
        provider_1 = make_provider(
            slot="provider_1",
            source="pokemon_tcg_api",
            label="Pokemon TCG API",
            is_primary=True,
            total_assets=127,
            assets_with_real_history=108,
            average_depth="8.90",
            changed_assets_24h=20,
            changed_assets_7d=36,
            comparable_rows_24h=56,
            changed_rows_24h=11,
            comparable_rows_7d=220,
            changed_rows_7d=48,
            changed_pct_24h="19.64",
            changed_pct_7d="21.82",
            no_movement_assets=24,
            unchanged_latest_assets=33,
            pool_reports=provider_1_pools,
        )
        provider_2 = make_provider(
            slot="provider_2",
            source="future_provider",
            label="Future Provider",
            is_primary=False,
            total_assets=127,
            assets_with_real_history=110,
            average_depth="9.30",
            changed_assets_24h=26,
            changed_assets_7d=42,
            comparable_rows_24h=60,
            changed_rows_24h=17,
            comparable_rows_7d=234,
            changed_rows_7d=60,
            changed_pct_24h="28.33",
            changed_pct_7d="25.64",
            no_movement_assets=20,
            unchanged_latest_assets=29,
            pool_reports=provider_2_pools,
        )

        provider_lines = _build_provider_comparison_table([provider_1, provider_2])
        provider_pool_sections = _build_provider_pool_comparison_sections([provider_1, provider_2])

        self.assertIn("Pokemon TCG API (provider_1, primary)", provider_lines[0])
        self.assertIn("Future Provider (provider_2)", provider_lines[0])
        self.assertTrue(
            any(
                "Percent of comparable rows changed in last 24h" in line
                and "19.64% (11/56)" in line
                and "28.33% (17/60)" in line
                for line in provider_lines
            )
        )
        self.assertEqual(provider_pool_sections[0][0], "Base Set")
        self.assertTrue(
            any(
                "15.63% (5/32)" in line and "10.00% (3/30)" in line
                for line in provider_pool_sections[0][1]
            )
        )

    def test_tag_movement_sections_group_reports_by_dimension(self):
        tag_reports = [
            make_tag_report(
                dimension="rarity",
                dimension_label="Rarity",
                tag_value="Illustration / Special Art Rare",
                total_assets=12,
                assets_with_real_history=10,
                average_depth="9.40",
                changed_assets_24h=5,
                changed_assets_7d=7,
                comparable_rows_24h=20,
                changed_rows_24h=8,
                comparable_rows_7d=72,
                changed_rows_7d=24,
                changed_pct_24h="40.00",
                changed_pct_7d="33.33",
                no_movement_assets=1,
                unchanged_latest_assets=2,
            ),
            make_tag_report(
                dimension="rarity",
                dimension_label="Rarity",
                tag_value="Common",
                total_assets=40,
                assets_with_real_history=35,
                average_depth="8.10",
                changed_assets_24h=2,
                changed_assets_7d=6,
                comparable_rows_24h=28,
                changed_rows_24h=2,
                comparable_rows_7d=120,
                changed_rows_7d=10,
                changed_pct_24h="7.14",
                changed_pct_7d="8.33",
                no_movement_assets=20,
                unchanged_latest_assets=23,
            ),
            make_tag_report(
                dimension="high_activity_candidate",
                dimension_label="High-Activity Candidate",
                tag_value="High-Activity Candidate",
                total_assets=33,
                assets_with_real_history=28,
                average_depth="9.90",
                changed_assets_24h=12,
                changed_assets_7d=18,
                comparable_rows_24h=26,
                changed_rows_24h=8,
                comparable_rows_7d=100,
                changed_rows_7d=30,
                changed_pct_24h="30.77",
                changed_pct_7d="30.00",
                no_movement_assets=3,
                unchanged_latest_assets=5,
            ),
        ]

        sections = _build_tag_movement_sections(tag_reports)

        self.assertEqual(sections[0][0], "Rarity")
        self.assertIn("Illustration / Special Art Rare", sections[0][1][2])
        self.assertTrue(
            any("40.00% (8/20)" in line for line in sections[0][1])
        )
        self.assertEqual(sections[1][0], "High-Activity Candidate")
        self.assertTrue(
            any("30.77% (8/26)" in line for line in sections[1][1])
        )

    def test_pool_summary_marks_high_activity_pool_as_more_active_when_it_beats_both(self):
        base_pool = make_pool(
            key=BASE_SET_POOL_KEY,
            label="Base Set",
            total_assets=69,
            assets_with_real_history=60,
            average_depth="8.00",
            changed_assets_24h=6,
            changed_assets_7d=18,
            comparable_rows_24h=40,
            changed_rows_24h=4,
            comparable_rows_7d=160,
            changed_rows_7d=20,
            changed_pct_24h="10.00",
            changed_pct_7d="12.50",
            no_movement_assets=20,
            unchanged_latest_assets=30,
        )
        trial_pool = make_pool(
            key=TRIAL_POOL_KEY,
            label="Scarlet & Violet 151 Trial",
            total_assets=25,
            assets_with_real_history=20,
            average_depth="7.00",
            changed_assets_24h=8,
            changed_assets_7d=12,
            comparable_rows_24h=24,
            changed_rows_24h=6,
            comparable_rows_7d=90,
            changed_rows_7d=18,
            changed_pct_24h="25.00",
            changed_pct_7d="20.00",
            no_movement_assets=3,
            unchanged_latest_assets=4,
        )
        high_activity_pool = make_pool(
            key=HIGH_ACTIVITY_TRIAL_POOL_KEY,
            label="High-Activity Trial",
            total_assets=33,
            assets_with_real_history=30,
            average_depth="8.25",
            changed_assets_24h=16,
            changed_assets_7d=20,
            comparable_rows_24h=32,
            changed_rows_24h=11,
            comparable_rows_7d=120,
            changed_rows_7d=36,
            changed_pct_24h="34.38",
            changed_pct_7d="30.00",
            no_movement_assets=2,
            unchanged_latest_assets=3,
        )

        status, activity_line = _build_high_activity_trial_pool_summary(
            [base_pool, trial_pool, high_activity_pool]
        )

        self.assertEqual(status, "positive")
        self.assertEqual(
            activity_line,
            "High-Activity Trial vs pools: more active than Base Set and Scarlet & Violet 151 Trial.",
        )

    def test_pool_summary_stays_conservative_when_high_activity_depth_is_too_thin(self):
        base_pool = make_pool(
            key=BASE_SET_POOL_KEY,
            label="Base Set",
            total_assets=69,
            assets_with_real_history=60,
            average_depth="10.00",
            changed_assets_24h=5,
            changed_assets_7d=12,
            comparable_rows_24h=30,
            changed_rows_24h=3,
            comparable_rows_7d=140,
            changed_rows_7d=14,
            changed_pct_24h="10.00",
            changed_pct_7d="10.00",
            no_movement_assets=18,
            unchanged_latest_assets=26,
        )
        trial_pool = make_pool(
            key=TRIAL_POOL_KEY,
            label="Scarlet & Violet 151 Trial",
            total_assets=25,
            assets_with_real_history=20,
            average_depth="4.00",
            changed_assets_24h=8,
            changed_assets_7d=14,
            comparable_rows_24h=18,
            changed_rows_24h=5,
            comparable_rows_7d=70,
            changed_rows_7d=16,
            changed_pct_24h="27.78",
            changed_pct_7d="22.86",
            no_movement_assets=2,
            unchanged_latest_assets=3,
        )
        high_activity_pool = make_pool(
            key=HIGH_ACTIVITY_TRIAL_POOL_KEY,
            label="High-Activity Trial",
            total_assets=33,
            assets_with_real_history=28,
            average_depth="6.50",
            changed_assets_24h=12,
            changed_assets_7d=18,
            comparable_rows_24h=26,
            changed_rows_24h=9,
            comparable_rows_7d=100,
            changed_rows_7d=32,
            changed_pct_24h="34.62",
            changed_pct_7d="32.00",
            no_movement_assets=2,
            unchanged_latest_assets=3,
        )

        status, activity_line = _build_high_activity_trial_pool_summary(
            [base_pool, trial_pool, high_activity_pool]
        )

        self.assertEqual(status, "insufficient")
        self.assertIn("history depth", activity_line)

    def test_pool_summary_flags_when_high_activity_is_not_better(self):
        base_pool = make_pool(
            key=BASE_SET_POOL_KEY,
            label="Base Set",
            total_assets=69,
            assets_with_real_history=60,
            average_depth="9.00",
            changed_assets_24h=7,
            changed_assets_7d=16,
            comparable_rows_24h=32,
            changed_rows_24h=5,
            comparable_rows_7d=140,
            changed_rows_7d=24,
            changed_pct_24h="15.63",
            changed_pct_7d="17.14",
            no_movement_assets=16,
            unchanged_latest_assets=22,
        )
        trial_pool = make_pool(
            key=TRIAL_POOL_KEY,
            label="Scarlet & Violet 151 Trial",
            total_assets=25,
            assets_with_real_history=22,
            average_depth="9.20",
            changed_assets_24h=6,
            changed_assets_7d=13,
            comparable_rows_24h=24,
            changed_rows_24h=4,
            comparable_rows_7d=84,
            changed_rows_7d=18,
            changed_pct_24h="16.67",
            changed_pct_7d="21.43",
            no_movement_assets=5,
            unchanged_latest_assets=7,
        )
        high_activity_pool = make_pool(
            key=HIGH_ACTIVITY_TRIAL_POOL_KEY,
            label="High-Activity Trial",
            total_assets=33,
            assets_with_real_history=30,
            average_depth="9.50",
            changed_assets_24h=4,
            changed_assets_7d=10,
            comparable_rows_24h=30,
            changed_rows_24h=3,
            comparable_rows_7d=120,
            changed_rows_7d=15,
            changed_pct_24h="10.00",
            changed_pct_7d="12.50",
            no_movement_assets=10,
            unchanged_latest_assets=12,
        )

        status, activity_line = _build_high_activity_trial_pool_summary(
            [base_pool, trial_pool, high_activity_pool]
        )

        self.assertEqual(status, "negative")
        self.assertEqual(
            activity_line,
            "High-Activity Trial vs pools: not more active than Base Set and Scarlet & Violet 151 Trial.",
        )

    def test_tag_segment_summary_marks_both_priority_segments_as_stronger(self):
        tag_reports = [
            make_tag_report(
                dimension="collectible_chase",
                dimension_label="Collectible / Chase",
                tag_value="Chase / Collectible",
                total_assets=28,
                assets_with_real_history=24,
                average_depth="9.50",
                changed_assets_24h=10,
                changed_assets_7d=15,
                comparable_rows_24h=24,
                changed_rows_24h=9,
                comparable_rows_7d=90,
                changed_rows_7d=28,
                changed_pct_24h="37.50",
                changed_pct_7d="31.11",
                no_movement_assets=3,
                unchanged_latest_assets=5,
            ),
            make_tag_report(
                dimension="collectible_chase",
                dimension_label="Collectible / Chase",
                tag_value="Standard",
                total_assets=90,
                assets_with_real_history=80,
                average_depth="8.60",
                changed_assets_24h=8,
                changed_assets_7d=16,
                comparable_rows_24h=44,
                changed_rows_24h=5,
                comparable_rows_7d=170,
                changed_rows_7d=20,
                changed_pct_24h="11.36",
                changed_pct_7d="11.76",
                no_movement_assets=42,
                unchanged_latest_assets=50,
            ),
            make_tag_report(
                dimension="high_activity_candidate",
                dimension_label="High-Activity Candidate",
                tag_value="High-Activity Candidate",
                total_assets=33,
                assets_with_real_history=28,
                average_depth="9.90",
                changed_assets_24h=12,
                changed_assets_7d=18,
                comparable_rows_24h=26,
                changed_rows_24h=8,
                comparable_rows_7d=100,
                changed_rows_7d=30,
                changed_pct_24h="30.77",
                changed_pct_7d="30.00",
                no_movement_assets=3,
                unchanged_latest_assets=5,
            ),
            make_tag_report(
                dimension="high_activity_candidate",
                dimension_label="High-Activity Candidate",
                tag_value="Standard Activity",
                total_assets=85,
                assets_with_real_history=76,
                average_depth="8.30",
                changed_assets_24h=6,
                changed_assets_7d=14,
                comparable_rows_24h=42,
                changed_rows_24h=4,
                comparable_rows_7d=160,
                changed_rows_7d=19,
                changed_pct_24h="9.52",
                changed_pct_7d="11.88",
                no_movement_assets=40,
                unchanged_latest_assets=47,
            ),
        ]

        status, line = _build_tag_segment_summary(tag_reports)

        self.assertEqual(status, "positive")
        self.assertEqual(
            line,
            "Tags vs rest: Collectible / Chase and High-Activity Candidate are both showing stronger movement than the rest.",
        )

    def test_operator_decision_summary_recommends_current_provider_when_high_activity_segments_move(self):
        pool_reports = [
            make_pool(
                key=BASE_SET_POOL_KEY,
                label="Base Set",
                total_assets=69,
                assets_with_real_history=60,
                average_depth="8.50",
                changed_assets_24h=6,
                changed_assets_7d=18,
                comparable_rows_24h=30,
                changed_rows_24h=3,
                comparable_rows_7d=120,
                changed_rows_7d=18,
                changed_pct_24h="10.00",
                changed_pct_7d="15.00",
                no_movement_assets=21,
                unchanged_latest_assets=28,
            ),
            make_pool(
                key=TRIAL_POOL_KEY,
                label="Scarlet & Violet 151 Trial",
                total_assets=25,
                assets_with_real_history=20,
                average_depth="9.25",
                changed_assets_24h=8,
                changed_assets_7d=12,
                comparable_rows_24h=22,
                changed_rows_24h=6,
                comparable_rows_7d=80,
                changed_rows_7d=20,
                changed_pct_24h="27.27",
                changed_pct_7d="25.00",
                no_movement_assets=4,
                unchanged_latest_assets=6,
            ),
            make_pool(
                key=HIGH_ACTIVITY_TRIAL_POOL_KEY,
                label="High-Activity Trial",
                total_assets=33,
                assets_with_real_history=28,
                average_depth="9.90",
                changed_assets_24h=12,
                changed_assets_7d=18,
                comparable_rows_24h=26,
                changed_rows_24h=8,
                comparable_rows_7d=100,
                changed_rows_7d=30,
                changed_pct_24h="30.77",
                changed_pct_7d="30.00",
                no_movement_assets=3,
                unchanged_latest_assets=5,
            ),
        ]
        tag_reports = [
            make_tag_report(
                dimension="collectible_chase",
                dimension_label="Collectible / Chase",
                tag_value="Chase / Collectible",
                total_assets=28,
                assets_with_real_history=24,
                average_depth="9.50",
                changed_assets_24h=10,
                changed_assets_7d=15,
                comparable_rows_24h=24,
                changed_rows_24h=9,
                comparable_rows_7d=90,
                changed_rows_7d=28,
                changed_pct_24h="37.50",
                changed_pct_7d="31.11",
                no_movement_assets=3,
                unchanged_latest_assets=5,
            ),
            make_tag_report(
                dimension="collectible_chase",
                dimension_label="Collectible / Chase",
                tag_value="Standard",
                total_assets=90,
                assets_with_real_history=80,
                average_depth="8.60",
                changed_assets_24h=8,
                changed_assets_7d=16,
                comparable_rows_24h=44,
                changed_rows_24h=5,
                comparable_rows_7d=170,
                changed_rows_7d=20,
                changed_pct_24h="11.36",
                changed_pct_7d="11.76",
                no_movement_assets=42,
                unchanged_latest_assets=50,
            ),
            make_tag_report(
                dimension="high_activity_candidate",
                dimension_label="High-Activity Candidate",
                tag_value="High-Activity Candidate",
                total_assets=33,
                assets_with_real_history=28,
                average_depth="9.90",
                changed_assets_24h=12,
                changed_assets_7d=18,
                comparable_rows_24h=26,
                changed_rows_24h=8,
                comparable_rows_7d=100,
                changed_rows_7d=30,
                changed_pct_24h="30.77",
                changed_pct_7d="30.00",
                no_movement_assets=3,
                unchanged_latest_assets=5,
            ),
            make_tag_report(
                dimension="high_activity_candidate",
                dimension_label="High-Activity Candidate",
                tag_value="Standard Activity",
                total_assets=85,
                assets_with_real_history=76,
                average_depth="8.30",
                changed_assets_24h=6,
                changed_assets_7d=14,
                comparable_rows_24h=42,
                changed_rows_24h=4,
                comparable_rows_7d=160,
                changed_rows_7d=19,
                changed_pct_24h="9.52",
                changed_pct_7d="11.88",
                no_movement_assets=40,
                unchanged_latest_assets=47,
            ),
        ]

        lines = _build_operator_decision_summary(pool_reports, tag_reports)

        self.assertEqual(
            lines,
            [
                "High-Activity Trial vs pools: more active than Base Set and Scarlet & Violet 151 Trial.",
                "Tags vs rest: Collectible / Chase and High-Activity Candidate are both showing stronger movement than the rest.",
                "Recommendation: continue with the current provider and smarter pool selection.",
            ],
        )

    def test_operator_decision_summary_recommends_provider_2_when_all_segments_stay_flat(self):
        pool_reports = [
            make_pool(
                key=BASE_SET_POOL_KEY,
                label="Base Set",
                total_assets=69,
                assets_with_real_history=60,
                average_depth="9.00",
                changed_assets_24h=7,
                changed_assets_7d=16,
                comparable_rows_24h=32,
                changed_rows_24h=5,
                comparable_rows_7d=140,
                changed_rows_7d=24,
                changed_pct_24h="15.63",
                changed_pct_7d="17.14",
                no_movement_assets=16,
                unchanged_latest_assets=22,
            ),
            make_pool(
                key=TRIAL_POOL_KEY,
                label="Scarlet & Violet 151 Trial",
                total_assets=25,
                assets_with_real_history=22,
                average_depth="9.20",
                changed_assets_24h=6,
                changed_assets_7d=13,
                comparable_rows_24h=24,
                changed_rows_24h=4,
                comparable_rows_7d=84,
                changed_rows_7d=18,
                changed_pct_24h="16.67",
                changed_pct_7d="21.43",
                no_movement_assets=5,
                unchanged_latest_assets=7,
            ),
            make_pool(
                key=HIGH_ACTIVITY_TRIAL_POOL_KEY,
                label="High-Activity Trial",
                total_assets=33,
                assets_with_real_history=30,
                average_depth="9.50",
                changed_assets_24h=4,
                changed_assets_7d=10,
                comparable_rows_24h=30,
                changed_rows_24h=3,
                comparable_rows_7d=120,
                changed_rows_7d=15,
                changed_pct_24h="10.00",
                changed_pct_7d="12.50",
                no_movement_assets=10,
                unchanged_latest_assets=12,
            ),
        ]
        tag_reports = [
            make_tag_report(
                dimension="collectible_chase",
                dimension_label="Collectible / Chase",
                tag_value="Chase / Collectible",
                total_assets=28,
                assets_with_real_history=24,
                average_depth="9.20",
                changed_assets_24h=2,
                changed_assets_7d=5,
                comparable_rows_24h=20,
                changed_rows_24h=1,
                comparable_rows_7d=86,
                changed_rows_7d=8,
                changed_pct_24h="5.00",
                changed_pct_7d="9.30",
                no_movement_assets=12,
                unchanged_latest_assets=15,
            ),
            make_tag_report(
                dimension="collectible_chase",
                dimension_label="Collectible / Chase",
                tag_value="Standard",
                total_assets=90,
                assets_with_real_history=80,
                average_depth="8.80",
                changed_assets_24h=10,
                changed_assets_7d=18,
                comparable_rows_24h=44,
                changed_rows_24h=6,
                comparable_rows_7d=170,
                changed_rows_7d=24,
                changed_pct_24h="13.64",
                changed_pct_7d="14.12",
                no_movement_assets=38,
                unchanged_latest_assets=43,
            ),
            make_tag_report(
                dimension="high_activity_candidate",
                dimension_label="High-Activity Candidate",
                tag_value="High-Activity Candidate",
                total_assets=33,
                assets_with_real_history=28,
                average_depth="9.30",
                changed_assets_24h=3,
                changed_assets_7d=7,
                comparable_rows_24h=24,
                changed_rows_24h=2,
                comparable_rows_7d=102,
                changed_rows_7d=10,
                changed_pct_24h="8.33",
                changed_pct_7d="9.80",
                no_movement_assets=11,
                unchanged_latest_assets=13,
            ),
            make_tag_report(
                dimension="high_activity_candidate",
                dimension_label="High-Activity Candidate",
                tag_value="Standard Activity",
                total_assets=85,
                assets_with_real_history=76,
                average_depth="8.60",
                changed_assets_24h=9,
                changed_assets_7d=17,
                comparable_rows_24h=40,
                changed_rows_24h=6,
                comparable_rows_7d=152,
                changed_rows_7d=22,
                changed_pct_24h="15.00",
                changed_pct_7d="14.47",
                no_movement_assets=34,
                unchanged_latest_assets=40,
            ),
        ]

        lines = _build_operator_decision_summary(pool_reports, tag_reports)

        self.assertEqual(
            lines,
            [
                "High-Activity Trial vs pools: not more active than Base Set and Scarlet & Violet 151 Trial.",
                "Tags vs rest: Collectible / Chase and High-Activity Candidate are not showing stronger movement than the rest.",
                "Recommendation: prepare provider #2.",
            ],
        )

    def test_current_provider_decision_note_prefers_v2_when_coverage_is_healthy(self):
        pool_reports = [
            make_pool(
                key=HIGH_ACTIVITY_TRIAL_POOL_KEY,
                label="High-Activity Trial",
                total_assets=33,
                assets_with_real_history=33,
                average_depth="60.58",
                changed_assets_24h=28,
                changed_assets_7d=32,
                comparable_rows_24h=1547,
                changed_rows_24h=28,
                comparable_rows_7d=1966,
                changed_rows_7d=53,
                changed_pct_24h="1.81",
                changed_pct_7d="2.70",
                no_movement_assets=1,
                unchanged_latest_assets=33,
            ),
            make_pool(
                key="high_activity_v2_pool",
                label="High-Activity v2",
                total_assets=13,
                assets_with_real_history=13,
                average_depth="61.31",
                changed_assets_24h=11,
                changed_assets_7d=13,
                comparable_rows_24h=619,
                changed_rows_24h=11,
                comparable_rows_7d=784,
                changed_rows_7d=19,
                changed_pct_24h="1.78",
                changed_pct_7d="2.42",
                no_movement_assets=0,
                unchanged_latest_assets=13,
            ),
        ]
        audits = [
            make_card_audit(
                card_id="sv8pt5-161",
                name="Umbreon ex",
                rows=62,
                changed_rows_24h=1,
                changed_rows_7d=1,
                distinct_prices=2,
                weak_coverage_candidate=False,
                assessment="Healthy / movement observed",
            ),
            make_card_audit(
                card_id="sv8pt5-156",
                name="Sylveon ex",
                rows=62,
                changed_rows_24h=0,
                changed_rows_7d=1,
                distinct_prices=2,
                weak_coverage_candidate=False,
                assessment="Healthy / movement observed",
            ),
        ]

        lines = _build_current_provider_decision_note(pool_reports, audits)

        self.assertIn("pool design looks weaker than provider coverage", lines[0])
        self.assertIn("0 of 2 look weak on coverage", lines[0])
        self.assertIn("0/13 vs 1/33", lines[1])
        self.assertEqual(
            lines[2],
            "Recommendation: replace the current High-Activity Trial with High-Activity v2 and keep observing before any provider #2 decision.",
        )
