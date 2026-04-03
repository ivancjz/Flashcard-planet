from __future__ import annotations

from unittest import TestCase

from backend.app.models.asset import Asset
from backend.app.services.asset_tagging import (
    CHASE_TAG_LABEL,
    HIGH_ACTIVITY_TAG_LABEL,
    MODERN_ERA_LABEL,
    OLDER_ERA_LABEL,
    classify_asset_tags,
    get_asset_tag_values,
)


def make_asset(
    *,
    external_id: str,
    provider_card_id: str,
    rarity: str | None,
    year: int | None,
    language: str = "EN",
    variant: str = "Holofoil",
) -> Asset:
    return Asset(
        asset_class="TCG",
        category="Pokemon",
        name="Test Card",
        set_name="Test Set",
        card_number="1",
        year=year,
        language=language,
        variant=variant,
        grade_company=None,
        grade_score=None,
        external_id=external_id,
        metadata_json={
            "provider": "pokemon_tcg_api",
            "provider_card_id": provider_card_id,
            "rarity": rarity,
        },
        notes=None,
    )


class AssetTaggingTests(TestCase):
    def test_modern_high_rarity_card_is_classified_as_chase_and_high_activity_candidate(self):
        asset = make_asset(
            external_id="pokemontcg:sv8pt5-160:holofoil",
            provider_card_id="sv8pt5-160",
            rarity="Special Illustration Rare",
            year=2025,
        )

        profile = classify_asset_tags(asset)
        tags = get_asset_tag_values(asset)

        self.assertEqual(profile.rarity, "Illustration / Special Art Rare")
        self.assertEqual(profile.language, "English")
        self.assertTrue(profile.collectible_chase)
        self.assertEqual(profile.era, MODERN_ERA_LABEL)
        self.assertTrue(profile.high_activity_candidate)
        self.assertEqual(tags["collectible_chase"], CHASE_TAG_LABEL)
        self.assertEqual(tags["high_activity_candidate"], HIGH_ACTIVITY_TAG_LABEL)

    def test_vintage_holo_stays_collectible_but_not_high_activity_candidate_by_default(self):
        asset = make_asset(
            external_id="pokemontcg:base1-4:holofoil",
            provider_card_id="base1-4",
            rarity="Rare Holo",
            year=1999,
        )

        profile = classify_asset_tags(asset)

        self.assertEqual(profile.rarity, "Holo / Classic Rare")
        self.assertTrue(profile.collectible_chase)
        self.assertEqual(profile.era, OLDER_ERA_LABEL)
        self.assertFalse(profile.high_activity_candidate)
