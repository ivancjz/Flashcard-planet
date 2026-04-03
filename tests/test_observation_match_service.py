from decimal import Decimal
from unittest import TestCase
from unittest.mock import Mock

from backend.app.models.asset import Asset
from backend.app.services.observation_match_service import (
    MATCH_STATUS_MATCHED_CANONICAL,
    MATCH_STATUS_MATCHED_CREATED,
    MATCH_STATUS_MATCHED_EXISTING,
    MATCH_STATUS_UNMATCHED_AMBIGUOUS,
    MATCH_STATUS_UNMATCHED_NO_PRICE,
    build_canonical_key,
    stage_observation_match,
)


def make_asset(
    *,
    external_id: str,
    provider_card_id: str,
    asset_id: int = 123,
    metadata_json: dict | None = None,
    notes: str = "Imported from Pokemon TCG API.",
) -> Asset:
    asset = Asset(
        asset_class="TCG",
        category="Pokemon",
        name="Umbreon ex",
        set_name="Prismatic Evolutions",
        card_number="161",
        year=2025,
        language="EN",
        variant="Holofoil",
        grade_company=None,
        grade_score=None,
        external_id=external_id,
        metadata_json=metadata_json
        or {
            "provider": "pokemon_tcg_api",
            "provider_card_id": provider_card_id,
            "rarity": "Special Illustration Rare",
        },
        notes=notes,
    )
    asset.id = asset_id
    return asset


def make_asset_payload(*, external_id: str, provider_card_id: str) -> dict[str, object]:
    return {
        "asset_class": "TCG",
        "category": "Pokemon",
        "name": "Umbreon ex",
        "set_name": "Prismatic Evolutions",
        "card_number": "161",
        "year": 2025,
        "language": "EN",
        "variant": "Holofoil",
        "grade_company": None,
        "grade_score": None,
        "external_id": external_id,
        "metadata_json": {
            "provider": "pokemon_tcg_api",
            "provider_card_id": provider_card_id,
            "rarity": "Special Illustration Rare",
        },
        "notes": "Imported from Pokemon TCG API.",
    }


class ObservationMatchServiceTests(TestCase):
    def test_build_canonical_key_stays_stable_for_identity_fields(self):
        canonical_key = build_canonical_key(
            {
                "asset_class": "TCG",
                "category": "Pokemon",
                "name": "Umbreon ex",
                "set_name": "Prismatic Evolutions",
                "card_number": "161",
                "year": 2025,
                "language": "EN",
                "variant": "Holofoil",
                "grade_company": None,
                "grade_score": None,
            }
        )

        self.assertEqual(
            canonical_key,
            "asset_class=tcg|category=pokemon|name=umbreon ex|set_name=prismatic evolutions|card_number=161|year=2025|language=en|variant=holofoil|grade_company=<none>|grade_score=<none>",
        )

    def test_stage_observation_match_logs_unmatched_observation_when_no_asset_payload_exists(self):
        session = Mock()

        result = stage_observation_match(
            session,
            provider="pokemon_tcg_api",
            external_item_id="sv8pt5-161",
            raw_title="Umbreon ex",
            raw_set_name="Prismatic Evolutions",
            raw_card_number="161",
            raw_language="EN",
            asset_payload=None,
            unmatched_reason="No usable price snapshot.",
        )

        self.assertFalse(result.can_write_price_history)
        self.assertIsNone(result.matched_asset)
        self.assertEqual(result.observation_log.match_status, MATCH_STATUS_UNMATCHED_NO_PRICE)
        self.assertEqual(result.observation_log.reason, "No usable price snapshot.")
        session.add.assert_called_once()
        session.flush.assert_called_once()

    def test_stage_observation_match_reuses_existing_asset_when_external_id_matches(self):
        existing_asset = make_asset(
            external_id="pokemontcg:sv8pt5-161:holofoil",
            provider_card_id="sv8pt5-161",
        )
        session = Mock()
        session.scalar.return_value = existing_asset

        result = stage_observation_match(
            session,
            provider="pokemon_tcg_api",
            external_item_id="sv8pt5-161",
            raw_title="Umbreon ex",
            raw_set_name="Prismatic Evolutions",
            raw_card_number="161",
            raw_language="EN",
            asset_payload=make_asset_payload(
                external_id="pokemontcg:sv8pt5-161:holofoil",
                provider_card_id="sv8pt5-161",
            ),
        )

        self.assertTrue(result.can_write_price_history)
        self.assertFalse(result.asset_created)
        self.assertEqual(result.matched_asset.id, existing_asset.id)
        self.assertEqual(result.observation_log.match_status, MATCH_STATUS_MATCHED_EXISTING)
        self.assertEqual(result.observation_log.confidence, Decimal("1.00"))

    def test_stage_observation_match_marks_ambiguous_canonical_candidates_for_review(self):
        session = Mock()
        session.scalar.return_value = None
        execute_result = Mock()
        execute_result.scalars.return_value.all.return_value = [
            make_asset(
                external_id="pokemontcg:sv8pt5-161:holofoil",
                provider_card_id="sv8pt5-161",
                asset_id=1,
            ),
            make_asset(
                external_id="pokemontcg:sv8pt5-161:normal",
                provider_card_id="sv8pt5-161",
                asset_id=2,
            ),
        ]
        session.execute.return_value = execute_result

        result = stage_observation_match(
            session,
            provider="pokemon_tcg_api",
            external_item_id="sv8pt5-161",
            raw_title="Umbreon ex",
            raw_set_name="Prismatic Evolutions",
            raw_card_number="161",
            raw_language="EN",
            asset_payload=make_asset_payload(
                external_id="pokemontcg:sv8pt5-161:alternate",
                provider_card_id="sv8pt5-161",
            ),
        )

        self.assertFalse(result.can_write_price_history)
        self.assertIsNone(result.matched_asset)
        self.assertEqual(result.observation_log.match_status, MATCH_STATUS_UNMATCHED_AMBIGUOUS)
        self.assertTrue(result.observation_log.requires_review)
        self.assertEqual(result.observation_log.confidence, Decimal("0.00"))

    def test_stage_observation_match_reuses_canonical_asset_without_overwriting_provider_identity(self):
        existing_asset = make_asset(
            external_id="pokemontcg:sv8pt5-161:holofoil",
            provider_card_id="sv8pt5-161",
            metadata_json={
                "provider": "pokemon_tcg_api",
                "provider_card_id": "sv8pt5-161",
                "provider_price_type": "holofoil",
            },
            notes="Existing canonical asset.",
        )
        session = Mock()
        session.scalar.return_value = None
        execute_result = Mock()
        execute_result.scalars.return_value.all.return_value = [existing_asset]
        session.execute.return_value = execute_result

        result = stage_observation_match(
            session,
            provider="pokemon_tcg_api",
            external_item_id="sv8pt5-161",
            raw_title="Umbreon ex",
            raw_set_name="Prismatic Evolutions",
            raw_card_number="161",
            raw_language="EN",
            asset_payload=make_asset_payload(
                external_id="pokemontcg:sv8pt5-161:market",
                provider_card_id="sv8pt5-161",
            ),
        )

        self.assertTrue(result.can_write_price_history)
        self.assertEqual(result.observation_log.match_status, MATCH_STATUS_MATCHED_CANONICAL)
        self.assertTrue(result.observation_log.requires_review)
        self.assertEqual(result.matched_asset.external_id, "pokemontcg:sv8pt5-161:holofoil")
        self.assertEqual(
            result.matched_asset.metadata_json["provider_price_type"],
            "holofoil",
        )
        self.assertEqual(result.matched_asset.notes, "Existing canonical asset.")

    def test_stage_observation_match_creates_asset_when_no_matches_exist(self):
        session = Mock()
        session.scalar.return_value = None
        execute_result = Mock()
        execute_result.scalars.return_value.all.return_value = []
        session.execute.return_value = execute_result

        def add_side_effect(instance):
            if isinstance(instance, Asset) and instance.id is None:
                instance.id = 999

        session.add.side_effect = add_side_effect

        result = stage_observation_match(
            session,
            provider="pokemon_tcg_api",
            external_item_id="sv8pt5-161",
            raw_title="Umbreon ex",
            raw_set_name="Prismatic Evolutions",
            raw_card_number="161",
            raw_language="EN",
            asset_payload=make_asset_payload(
                external_id="pokemontcg:sv8pt5-161:holofoil",
                provider_card_id="sv8pt5-161",
            ),
        )

        self.assertTrue(result.can_write_price_history)
        self.assertTrue(result.asset_created)
        self.assertEqual(result.observation_log.match_status, MATCH_STATUS_MATCHED_CREATED)
        self.assertIsInstance(result.matched_asset, Asset)
