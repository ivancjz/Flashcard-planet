"""
tests/test_game_field.py

Covers the TASK-001a game field introduction:
  a. Migration file is well-formed (has upgrade/downgrade, correct revision chain)
  b. Dual-write: build_asset_payload() in pokemon_tcg.py writes game='pokemon'
  c. Dual-write: build_asset_payload() in import_pokemon_cards.py writes game='pokemon'
  d. Asset ORM model exposes a game attribute
  e. Pydantic schemas include game field with default 'pokemon'
  f. Service-level: game propagates through AlertItemResponse / WatchlistItemResponse
"""
from __future__ import annotations

import importlib
import unittest
from decimal import Decimal
from uuid import uuid4


# ── a. Migration structure ────────────────────────────────────────────────────

class TestMigrationStructure(unittest.TestCase):
    def _load_migration(self):
        import importlib.util, pathlib
        path = pathlib.Path(__file__).parent.parent / "migrations" / "versions" / "0014_20260419_add_game_field.py"
        spec = importlib.util.spec_from_file_location("migration_0014", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_migration_exists_and_loads(self):
        mod = self._load_migration()
        self.assertEqual(mod.revision, "0014")

    def test_migration_down_revision_is_0013(self):
        mod = self._load_migration()
        self.assertEqual(mod.down_revision, "0013")

    def test_migration_has_upgrade_function(self):
        mod = self._load_migration()
        self.assertTrue(callable(mod.upgrade))

    def test_migration_has_downgrade_function(self):
        mod = self._load_migration()
        self.assertTrue(callable(mod.downgrade))


# ── b. Dual-write: pokemon_tcg.py ────────────────────────────────────────────

class TestPokemonTcgDualWrite(unittest.TestCase):
    def _make_card(self) -> dict:
        return {
            "id": "base1-4",
            "name": "Charizard",
            "number": "4",
            "set": {"id": "base1", "name": "Base Set", "releaseDate": "1999/01/09", "series": "Base"},
            "rarity": "Holo Rare",
            "subtypes": [],
            "images": {"small": "https://images.pokemontcg.io/base1/4.png"},
        }

    def test_build_asset_payload_includes_game(self):
        from backend.app.ingestion.pokemon_tcg import build_asset_payload
        payload = build_asset_payload(self._make_card(), "tcgplayer", "market")
        self.assertIn("game", payload)
        self.assertEqual(payload["game"], "pokemon")

    def test_build_asset_payload_does_not_write_category(self):
        # TASK-001c: dual-write stopped; category key must be absent from new payloads.
        from backend.app.ingestion.pokemon_tcg import build_asset_payload
        payload = build_asset_payload(self._make_card(), "tcgplayer", "market")
        self.assertNotIn("category", payload)

    def test_build_asset_payload_stores_set_total_in_nested_set(self):
        # set.total must be stored so _card_number_matches set-identity check activates
        from backend.app.ingestion.pokemon_tcg import build_asset_payload
        card = self._make_card()
        card["set"]["total"] = 102
        payload = build_asset_payload(card, "tcgplayer", "market")
        meta = payload["metadata_json"]
        self.assertIn("set", meta)
        self.assertIsInstance(meta["set"], dict)
        self.assertEqual(meta["set"]["total"], 102)

    def test_build_asset_payload_set_total_none_when_missing(self):
        # When TCG API returns no total, metadata.set.total must be None (not KeyError)
        from backend.app.ingestion.pokemon_tcg import build_asset_payload
        card = self._make_card()  # _make_card has no total field
        payload = build_asset_payload(card, "tcgplayer", "market")
        meta = payload["metadata_json"]
        self.assertIn("set", meta)
        self.assertIsNone(meta["set"].get("total"))


# ── c. Dual-write: import_pokemon_cards.py ───────────────────────────────────

class TestImportPokemonCardsDualWrite(unittest.TestCase):
    def _make_card(self) -> dict:
        return {
            "id": "base1-4",
            "name": "Charizard",
            "number": "4",
            "set": {"id": "base1", "name": "Base Set", "releaseDate": "1999-01-09", "series": "Base"},
            "rarity": "Holo Rare",
            "subtypes": ["Stage 2"],
            "images": {"small": "https://images.pokemontcg.io/base1/4.png"},
        }

    def test_build_asset_payload_includes_game(self):
        import scripts.import_pokemon_cards as script
        payload = script.build_asset_payload(self._make_card())
        self.assertIn("game", payload)
        self.assertEqual(payload["game"], "pokemon")

    def test_build_asset_payload_does_not_write_category(self):
        # TASK-001c: dual-write stopped; category key must be absent from new payloads.
        import scripts.import_pokemon_cards as script
        payload = script.build_asset_payload(self._make_card())
        self.assertNotIn("category", payload)


# ── d. Asset ORM model ────────────────────────────────────────────────────────

class TestAssetModel(unittest.TestCase):
    def test_asset_has_game_column(self):
        from backend.app.models.asset import Asset
        self.assertIn("game", Asset.__mapper__.columns.keys())

    def test_asset_game_default_is_pokemon(self):
        from backend.app.models.asset import Asset
        col = Asset.__mapper__.columns["game"]
        self.assertEqual(col.default.arg, "pokemon")

    def test_asset_game_is_not_nullable(self):
        from backend.app.models.asset import Asset
        col = Asset.__mapper__.columns["game"]
        self.assertFalse(col.nullable)


# ── e. Pydantic schemas include game ─────────────────────────────────────────

class TestPydanticSchemas(unittest.TestCase):
    def test_alert_item_response_has_game(self):
        from backend.app.schemas.alert import AlertItemResponse
        self.assertIn("game", AlertItemResponse.model_fields)

    def test_alert_item_response_game_defaults_to_pokemon(self):
        from backend.app.schemas.alert import AlertItemResponse
        field = AlertItemResponse.model_fields["game"]
        self.assertEqual(field.default, "pokemon")

    def test_asset_price_response_has_game(self):
        from backend.app.schemas.price import AssetPriceResponse
        self.assertIn("game", AssetPriceResponse.model_fields)

    def test_asset_history_response_has_game(self):
        from backend.app.schemas.price import AssetHistoryResponse
        self.assertIn("game", AssetHistoryResponse.model_fields)

    def test_top_mover_response_has_game(self):
        from backend.app.schemas.price import TopMoverResponse
        self.assertIn("game", TopMoverResponse.model_fields)

    def test_top_value_response_has_game(self):
        from backend.app.schemas.price import TopValueResponse
        self.assertIn("game", TopValueResponse.model_fields)

    def test_price_prediction_response_has_game(self):
        from backend.app.schemas.price import PricePredictionResponse
        self.assertIn("game", PricePredictionResponse.model_fields)

    def test_watchlist_item_response_has_game(self):
        from backend.app.schemas.watchlist import WatchlistItemResponse
        self.assertIn("game", WatchlistItemResponse.model_fields)


# ── f. API response serialisation ────────────────────────────────────────────

class TestApiResponseSerialisation(unittest.TestCase):
    """Verify that game flows through to serialised JSON output."""

    def test_asset_price_response_serialises_game(self):
        from datetime import UTC, datetime
        from backend.app.schemas.price import AssetPriceResponse
        resp = AssetPriceResponse(
            asset_id=uuid4(),
            asset_class="TCG",
            category="Pokemon",
            game="pokemon",
            name="Charizard",
            latest_price=Decimal("120.00"),
            currency="USD",
            source="pokemon_tcg_api",
            captured_at=datetime(2026, 4, 19, tzinfo=UTC),
        )
        data = resp.model_dump()
        self.assertEqual(data["category"], "Pokemon")
        self.assertEqual(data["game"], "pokemon")

    def test_alert_item_response_serialises_game(self):
        from datetime import UTC, datetime
        from backend.app.schemas.alert import AlertItemResponse
        resp = AlertItemResponse(
            alert_id=uuid4(),
            asset_id=uuid4(),
            asset_name="Charizard",
            category="Pokemon",
            game="pokemon",
            alert_type="PRICE_UP_THRESHOLD",
            is_active=True,
            is_armed=True,
            created_at=datetime(2026, 4, 19, tzinfo=UTC),
        )
        data = resp.model_dump()
        self.assertEqual(data["game"], "pokemon")

    def test_watchlist_item_response_serialises_game(self):
        from datetime import UTC, datetime
        from backend.app.schemas.watchlist import WatchlistItemResponse
        resp = WatchlistItemResponse(
            watchlist_id=uuid4(),
            asset_id=uuid4(),
            name="Charizard",
            category="Pokemon",
            game="pokemon",
            added_at=datetime(2026, 4, 19, tzinfo=UTC),
        )
        data = resp.model_dump()
        self.assertEqual(data["game"], "pokemon")

    def test_game_appears_alongside_category_in_response(self):
        """Both fields present simultaneously — the dual-write contract."""
        from datetime import UTC, datetime
        from backend.app.schemas.price import AssetPriceResponse
        resp = AssetPriceResponse(
            asset_id=uuid4(),
            asset_class="TCG",
            category="Pokemon",
            game="pokemon",
            name="Pikachu",
            latest_price=Decimal("5.00"),
            currency="USD",
            source="pokemon_tcg_api",
            captured_at=datetime(2026, 4, 19, tzinfo=UTC),
        )
        data = resp.model_dump()
        # The key invariant: both fields present with correct values
        self.assertEqual(data["category"], "Pokemon")
        self.assertEqual(data["game"], "pokemon")


if __name__ == "__main__":
    unittest.main()
