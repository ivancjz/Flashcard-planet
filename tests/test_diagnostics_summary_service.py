from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest import TestCase
from unittest.mock import Mock, patch

from backend.app.core.price_sources import ConfiguredPriceProvider
from backend.app.core.tracked_pools import (
    BASE_SET_POOL_KEY,
    HIGH_ACTIVITY_TRIAL_POOL_KEY,
    HIGH_ACTIVITY_V2_POOL_KEY,
    TRIAL_POOL_KEY,
)
from backend.app.ingestion.pokemon_tcg import IngestionResult
from backend.app.models.observation_match_log import ObservationMatchLog
from backend.app.services.data_health_service import DataHealthReport, PoolHealthSnapshot
from backend.app.services.diagnostics_summary_service import (
    _build_recent_observation_stage,
    build_standardized_diagnostics_summary,
)


def make_pool(
    *,
    key: str,
    label: str,
    total_assets: int,
    assets_with_real_history: int,
    changed_assets_7d: int,
    changed_pct_7d: str,
    no_movement_assets: int,
) -> PoolHealthSnapshot:
    return PoolHealthSnapshot(
        key=key,
        label=label,
        asset_external_id_patterns=(f"{key}:%",),
        total_assets=total_assets,
        assets_with_real_history=assets_with_real_history,
        assets_without_real_history=max(total_assets - assets_with_real_history, 0),
        average_real_history_points_per_asset=Decimal("12.00"),
        assets_with_fewer_than_3_real_points=0,
        assets_with_fewer_than_5_real_points=0,
        assets_with_fewer_than_8_real_points=0,
        recent_real_price_rows_last_24h=40,
        recent_real_price_rows_last_7d=160,
        recent_comparable_rows_last_24h=20,
        recent_rows_with_price_change_last_24h=5,
        percent_recent_rows_changed_last_24h=Decimal("25.00"),
        recent_comparable_rows_last_7d=80,
        recent_rows_with_price_change_last_7d=10,
        percent_recent_rows_changed_last_7d=Decimal(changed_pct_7d),
        assets_with_price_change_last_24h=4,
        assets_with_price_change_last_7d=changed_assets_7d,
        assets_with_no_price_movement_full_history=no_movement_assets,
        assets_with_unchanged_latest_price=3,
        average_recent_rows_per_asset_last_24h=Decimal("1.00"),
        average_recent_rows_per_asset_last_7d=Decimal("2.00"),
        average_changed_rows_per_asset_last_24h=Decimal("0.25"),
        average_changed_rows_per_asset_last_7d=Decimal("0.50"),
        rows_per_recent_price_change_last_24h=Decimal("4.00"),
        rows_per_recent_price_change_last_7d=Decimal("8.00"),
    )


def make_report(pool_reports: list[PoolHealthSnapshot]) -> DataHealthReport:
    return DataHealthReport(
        total_assets=140,
        assets_with_real_history=132,
        assets_without_real_history=8,
        average_real_history_points_per_asset=Decimal("11.50"),
        assets_with_fewer_than_3_real_points=2,
        assets_with_fewer_than_5_real_points=3,
        assets_with_fewer_than_8_real_points=6,
        recent_real_price_rows_last_24h=320,
        recent_real_price_rows_last_7d=1400,
        recent_comparable_rows_last_24h=160,
        recent_rows_with_price_change_last_24h=24,
        percent_recent_rows_changed_last_24h=Decimal("15.00"),
        recent_comparable_rows_last_7d=740,
        recent_rows_with_price_change_last_7d=80,
        percent_recent_rows_changed_last_7d=Decimal("10.81"),
        assets_with_price_change_last_24h=40,
        assets_with_price_change_last_7d=90,
        assets_with_no_price_movement_full_history=18,
        assets_with_unchanged_latest_price=20,
        average_recent_rows_per_asset_last_24h=Decimal("2.42"),
        average_recent_rows_per_asset_last_7d=Decimal("10.61"),
        average_changed_rows_per_asset_last_24h=Decimal("0.18"),
        average_changed_rows_per_asset_last_7d=Decimal("0.61"),
        rows_per_recent_price_change_last_24h=Decimal("6.67"),
        rows_per_recent_price_change_last_7d=Decimal("9.25"),
        pool_reports=pool_reports,
        tag_reports=[],
        provider_reports=[],
    )


class DiagnosticsSummaryServiceTests(TestCase):
    @patch("backend.app.services.diagnostics_summary_service._build_recent_observation_stage")
    @patch("backend.app.services.diagnostics_summary_service.get_primary_price_source")
    @patch("backend.app.services.diagnostics_summary_service.get_configured_price_providers")
    @patch("backend.app.services.diagnostics_summary_service.get_data_health_report")
    def test_standardized_summary_centers_high_activity_v2_and_uses_run_counts(
        self,
        get_data_health_report_mock,
        get_configured_price_providers_mock,
        get_primary_price_source_mock,
        build_recent_observation_stage_mock,
    ):
        pools = [
            make_pool(
                key=BASE_SET_POOL_KEY,
                label="Base Set",
                total_assets=69,
                assets_with_real_history=60,
                changed_assets_7d=18,
                changed_pct_7d="15.00",
                no_movement_assets=21,
            ),
            make_pool(
                key=TRIAL_POOL_KEY,
                label="Scarlet & Violet 151 Trial",
                total_assets=25,
                assets_with_real_history=22,
                changed_assets_7d=16,
                changed_pct_7d="18.00",
                no_movement_assets=4,
            ),
            make_pool(
                key=HIGH_ACTIVITY_TRIAL_POOL_KEY,
                label="High-Activity Trial",
                total_assets=33,
                assets_with_real_history=33,
                changed_assets_7d=29,
                changed_pct_7d="2.70",
                no_movement_assets=1,
            ),
            make_pool(
                key=HIGH_ACTIVITY_V2_POOL_KEY,
                label="High-Activity v2",
                total_assets=13,
                assets_with_real_history=13,
                changed_assets_7d=13,
                changed_pct_7d="2.42",
                no_movement_assets=0,
            ),
        ]
        get_data_health_report_mock.return_value = make_report(pools)
        get_configured_price_providers_mock.return_value = [
            ConfiguredPriceProvider(
                slot="provider_1",
                source="pokemon_tcg_api",
                label="Pokemon TCG API",
                is_primary=True,
            )
        ]
        get_primary_price_source_mock.return_value = "pokemon_tcg_api"
        build_recent_observation_stage_mock.return_value = {
            "window": "24h",
            "observations_logged": 99,
            "observations_matched": 98,
            "observations_unmatched": 1,
            "observations_require_review": 0,
            "match_status_counts": {"matched_existing": 98, "unmatched_ambiguous": 1},
            "recent_review_items": [],
        }
        db = Mock()
        db.scalar.side_effect = [4, 7]
        ingestion_result = IngestionResult(
            cards_requested=13,
            cards_processed=12,
            cards_failed=0,
            cards_skipped_no_price=1,
            assets_created=2,
            assets_updated=10,
            price_points_inserted=12,
            price_points_changed=7,
            price_points_unchanged=5,
            observations_logged=13,
            observations_matched=12,
            observations_unmatched=1,
            observations_require_review=2,
            observation_match_status_counts={
                "matched_existing": 10,
                "matched_canonical": 2,
                "unmatched_no_price": 1,
            },
        )

        summary = build_standardized_diagnostics_summary(
            db,
            ingestion_result=ingestion_result,
            scope_key=HIGH_ACTIVITY_V2_POOL_KEY,
            scope_label="High-Activity v2",
        )

        self.assertEqual(summary["scope"]["key"], HIGH_ACTIVITY_V2_POOL_KEY)
        self.assertEqual(summary["provider"]["source"], "pokemon_tcg_api")
        self.assertEqual(summary["provider"]["label"], "Pokemon TCG API")
        self.assertEqual(summary["smart_pool"]["key"], HIGH_ACTIVITY_V2_POOL_KEY)
        self.assertEqual(
            summary["smart_pool"]["headline"],
            "High-Activity v2 is the main smart observation reference.",
        )
        self.assertEqual(summary["observation_stage"]["observations_logged"], 13)
        self.assertEqual(summary["observation_stage"]["observations_matched"], 12)
        self.assertEqual(summary["observation_stage"]["observations_unmatched"], 1)
        self.assertEqual(summary["observation_stage"]["observations_require_review"], 2)
        self.assertEqual(summary["signal_layer"]["watchlists"], 4)
        self.assertEqual(summary["signal_layer"]["active_alerts"], 7)
        self.assertTrue(
            any("Against Base Set" in line for line in summary["smart_pool"]["comparison_lines"])
        )
        self.assertTrue(
            any(
                "Against High-Activity Trial" in line
                for line in summary["smart_pool"]["comparison_lines"]
            )
        )

    def test_recent_observation_stage_counts_full_review_total_not_just_recent_sample(self):
        db = Mock()
        grouped_rows_result = Mock()
        grouped_rows_result.all.return_value = [
            ("matched_existing", 3),
            ("unmatched_ambiguous", 2),
        ]

        recent_logs = [
            ObservationMatchLog(
                provider="pokemon_tcg_api",
                external_item_id="sv8pt5-161",
                match_status="matched_existing",
                confidence=Decimal("1.00"),
                reason="ok",
                requires_review=False,
                created_at=datetime.now(UTC),
            ),
            ObservationMatchLog(
                provider="pokemon_tcg_api",
                external_item_id="sv8pt5-162",
                match_status="unmatched_ambiguous",
                confidence=Decimal("0.00"),
                reason="needs review",
                requires_review=True,
                created_at=datetime.now(UTC),
            ),
        ]
        recent_logs_result = Mock()
        recent_logs_result.scalars.return_value.all.return_value = recent_logs

        review_logs_result = Mock()
        review_logs_result.scalars.return_value.all.return_value = [
            ObservationMatchLog(
                provider="pokemon_tcg_api",
                external_item_id="sv8pt5-162",
                raw_title="Sylveon ex",
                match_status="unmatched_ambiguous",
                confidence=Decimal("0.00"),
                reason="needs review",
                requires_review=True,
                created_at=datetime.now(UTC),
            ),
            ObservationMatchLog(
                provider="pokemon_tcg_api",
                external_item_id="sv8pt5-165",
                raw_title="Dragapult ex",
                match_status="matched_canonical",
                confidence=Decimal("0.90"),
                reason="external id differs",
                requires_review=True,
                created_at=datetime.now(UTC),
            ),
        ]

        db.execute.side_effect = [
            grouped_rows_result,
            recent_logs_result,
            review_logs_result,
        ]
        db.scalar.return_value = 5

        stage = _build_recent_observation_stage(
            db,
            provider="pokemon_tcg_api",
            recent_observation_limit=5,
        )

        self.assertEqual(stage["observations_logged"], 5)
        self.assertEqual(stage["observations_matched"], 3)
        self.assertEqual(stage["observations_unmatched"], 2)
        self.assertEqual(stage["observations_require_review"], 5)
        self.assertEqual(len(stage["recent_review_items"]), 2)
