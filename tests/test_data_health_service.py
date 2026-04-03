from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest import TestCase
from unittest.mock import Mock

from backend.app.models.asset import Asset
from backend.app.services.data_health_service import _collect_asset_tag_metric_records


def make_asset(*, asset_id: int, external_id: str, provider_card_id: str) -> Asset:
    asset = Asset(
        asset_class="TCG",
        category="Pokemon",
        name="Test Card",
        set_name="Test Set",
        card_number="1",
        year=2025,
        language="EN",
        variant="Holofoil",
        grade_company=None,
        grade_score=None,
        external_id=external_id,
        metadata_json={
            "provider": "pokemon_tcg_api",
            "provider_card_id": provider_card_id,
            "rarity": "Special Illustration Rare",
        },
        notes=None,
    )
    asset.id = asset_id
    return asset


class DataHealthServiceTests(TestCase):
    def test_collect_asset_tag_metric_records_handles_naive_and_aware_datetimes(self):
        asset = make_asset(
            asset_id=1,
            external_id="pokemontcg:sv8pt5-160:holofoil",
            provider_card_id="sv8pt5-160",
        )
        now = datetime.now(UTC)
        history_rows = [
            (asset.id, "100.00", (now - timedelta(hours=2)).replace(tzinfo=None)),
            (asset.id, "101.00", now - timedelta(minutes=30)),
        ]

        tracked_assets_result = Mock()
        tracked_assets_result.scalars.return_value.all.return_value = [asset]
        history_rows_result = Mock()
        history_rows_result.all.return_value = history_rows

        session = Mock()
        session.execute.side_effect = [tracked_assets_result, history_rows_result]

        records = _collect_asset_tag_metric_records(session, source_filter=True)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].recent_real_rows_last_24h, 2)
        self.assertEqual(records[0].recent_rows_with_price_change_last_24h, 1)
        self.assertEqual(records[0].recent_comparable_rows_last_24h, 1)
