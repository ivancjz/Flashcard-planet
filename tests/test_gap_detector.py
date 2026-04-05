from unittest import TestCase
from uuid import uuid4

from backend.app.backstage.gap_detector import AssetHistoryCoverageRow, build_gap_report


def make_row(
    *,
    asset_name: str,
    set_id: str | None,
    set_name: str | None,
    history_count: int,
) -> AssetHistoryCoverageRow:
    return AssetHistoryCoverageRow(
        asset_id=uuid4(),
        asset_name=asset_name,
        set_id=set_id,
        set_name=set_name,
        history_count=history_count,
    )


class GapDetectorTests(TestCase):
    def test_build_gap_report_prioritizes_zero_history_then_thin_history_then_partial_sets(self):
        report = build_gap_report(
            [
                make_row(asset_name="Pikachu", set_id="base1", set_name="Base Set", history_count=0),
                make_row(asset_name="Charizard", set_id="base1", set_name="Base Set", history_count=2),
                make_row(asset_name="Blastoise", set_id="base1", set_name="Base Set", history_count=7),
                make_row(asset_name="Venusaur", set_id="jungle", set_name="Jungle", history_count=0),
                make_row(asset_name="Snorlax", set_id="jungle", set_name="Jungle", history_count=1),
                make_row(asset_name="Eevee", set_id="jungle", set_name="Jungle", history_count=7),
            ],
            history_threshold=7,
            set_coverage_threshold=0.5,
        )

        self.assertEqual(report.total_assets, 6)
        self.assertEqual(report.covered_assets, 2)
        self.assertEqual(report.zero_history_assets, 2)
        self.assertEqual(report.thin_history_assets, 2)
        self.assertEqual(report.partial_sets, 2)
        self.assertEqual(
            [entry.gap_type for entry in report.priority_queue],
            [
                "zero_history",
                "zero_history",
                "thin_history",
                "thin_history",
                "partial_set",
                "partial_set",
            ],
        )
        self.assertEqual(report.priority_queue[0].asset_name, "Pikachu")
        self.assertEqual(report.priority_queue[1].asset_name, "Venusaur")
        self.assertEqual(report.priority_queue[2].asset_name, "Snorlax")
        self.assertEqual(report.priority_queue[3].asset_name, "Charizard")
        self.assertEqual(report.priority_queue[4].set_id, "base1")
        self.assertEqual(report.priority_queue[5].set_id, "jungle")

    def test_build_gap_report_does_not_flag_sets_at_exactly_fifty_percent_coverage(self):
        report = build_gap_report(
            [
                make_row(asset_name="Umbreon", set_id="sv8pt5", set_name="Prismatic Evolutions", history_count=7),
                make_row(asset_name="Espeon", set_id="sv8pt5", set_name="Prismatic Evolutions", history_count=2),
            ],
            history_threshold=7,
            set_coverage_threshold=0.5,
        )

        self.assertEqual(report.covered_assets, 1)
        self.assertEqual(report.zero_history_assets, 0)
        self.assertEqual(report.thin_history_assets, 1)
        self.assertEqual(report.partial_sets, 0)
        self.assertEqual(report.gap_count, 1)
