"""
tests/test_game.py

Covers backend/app/models/game.py:
  - Game enum values and str behaviour
  - GAME_CONFIG completeness and field correctness
  - SQLAlchemy column-type compatibility (str, Enum)
  - eBay category config and client game-param wiring
"""
from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.app.models.game import GAME_CONFIG, Game, GameMetadata


class TestGameEnum(unittest.TestCase):
    def test_pokemon_value(self):
        self.assertEqual(Game.POKEMON.value, "pokemon")

    def test_all_values_are_lowercase_strings(self):
        for member in Game:
            self.assertIsInstance(member.value, str)
            self.assertEqual(member.value, member.value.lower())

    def test_game_is_str_subclass(self):
        # str, Enum means the member itself compares equal to its value string,
        # matching the AssetClass pattern used in SQLAlchemy String columns.
        self.assertEqual(Game.POKEMON, "pokemon")
        self.assertIsInstance(Game.POKEMON, str)

    def test_all_five_members_exist(self):
        expected = {"pokemon", "yugioh", "mtg", "one_piece", "lorcana"}
        self.assertEqual({g.value for g in Game}, expected)


class TestGameConfig(unittest.TestCase):
    def test_config_covers_all_games(self):
        self.assertEqual(set(GAME_CONFIG.keys()), set(Game))

    def test_pokemon_is_live(self):
        self.assertEqual(GAME_CONFIG[Game.POKEMON].status, "live")

    def test_yugioh_is_live(self):
        self.assertEqual(GAME_CONFIG[Game.YUGIOH].status, "live")

    def test_non_live_games_are_coming_soon(self):
        live_games = {Game.POKEMON, Game.YUGIOH}
        for game in Game:
            if game not in live_games:
                self.assertEqual(
                    GAME_CONFIG[game].status,
                    "coming_soon",
                    f"{game} should be coming_soon",
                )

    def test_display_names_are_non_empty(self):
        for game, meta in GAME_CONFIG.items():
            self.assertTrue(meta.display_name, f"{game} has empty display_name")

    def test_native_franchises_are_non_empty(self):
        for game, meta in GAME_CONFIG.items():
            self.assertTrue(meta.native_franchise, f"{game} has empty native_franchise")

    def test_game_metadata_is_frozen(self):
        meta = GAME_CONFIG[Game.POKEMON]
        with self.assertRaises((AttributeError, TypeError)):
            meta.status = "beta"  # type: ignore[misc]

    def test_sqlalchemy_column_compatibility(self):
        # Game is a str subclass: Game.POKEMON == "pokemon" is True, so SQLAlchemy
        # String columns accept Game members directly without any type adapter —
        # same pattern as AssetClass used in asset.py.
        self.assertEqual(Game.POKEMON.value, "pokemon")
        self.assertEqual(Game.MTG.value, "mtg")
        # Equality against plain string — the property SQLAlchemy relies on for
        # WHERE clause comparisons when the column type is String(32).
        self.assertTrue(Game.POKEMON == "pokemon")
        self.assertTrue(Game.MTG == "mtg")


class TestRealEbayClientGameParam(unittest.IsolatedAsyncioTestCase):
    """RealEbayClient uses GAME_CONFIG to build eBay requests."""

    def _make_async_client(self, *, category_id_in_response: bool = True) -> MagicMock:
        token_resp = MagicMock()
        token_resp.raise_for_status.return_value = None
        token_resp.json.return_value = {"access_token": "tok"}

        get_resp = MagicMock()
        get_resp.status_code = 200
        get_resp.text = ""
        get_resp.raise_for_status.return_value = None
        get_resp.json.return_value = {"itemSummaries": []}

        async_client = AsyncMock()
        async_client.post = AsyncMock(return_value=token_resp)
        async_client.get = AsyncMock(return_value=get_resp)

        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=async_client)
        ctx.__aexit__ = AsyncMock(return_value=False)
        return ctx, async_client

    async def test_pokemon_fetch_uses_category_2536(self):
        from backend.app.ingestion.ebay.real_client import RealEbayClient

        ctx, mock_client = self._make_async_client()
        with (
            patch("backend.app.ingestion.ebay.real_client.httpx.AsyncClient", return_value=ctx),
            patch("backend.app.ingestion.ebay.real_client.settings") as mock_settings,
        ):
            mock_settings.ebay_app_id = "app-id"
            mock_settings.ebay_cert_id = "cert-id"
            mock_settings.ebay_search_keywords = None

            client = RealEbayClient()
            await client.fetch_sold_listings(game=Game.POKEMON, limit=5)

        # Both Finding and Browse calls should use category 2536
        for call in mock_client.get.call_args_list:
            params = call.kwargs.get("params") or (call.args[1] if len(call.args) > 1 else {})
            category = params.get("categoryId") or params.get("category_ids")
            if category is not None:
                self.assertEqual(category, "2536")

    async def test_yugioh_fetch_uses_category_183454(self):
        from backend.app.ingestion.ebay.real_client import RealEbayClient

        ctx, mock_client = self._make_async_client()
        with (
            patch("backend.app.ingestion.ebay.real_client.httpx.AsyncClient", return_value=ctx),
            patch("backend.app.ingestion.ebay.real_client.settings") as mock_settings,
        ):
            mock_settings.ebay_app_id = "app-id"
            mock_settings.ebay_cert_id = "cert-id"
            mock_settings.ebay_search_keywords = None

            client = RealEbayClient()
            await client.fetch_sold_listings(game=Game.YUGIOH, limit=5)

        for call in mock_client.get.call_args_list:
            params = call.kwargs.get("params") or (call.args[1] if len(call.args) > 1 else {})
            category = params.get("categoryId") or params.get("category_ids")
            if category is not None:
                self.assertEqual(category, "183454")

    async def test_one_piece_fetch_omits_category_id(self):
        from backend.app.ingestion.ebay.real_client import RealEbayClient

        ctx, mock_client = self._make_async_client()
        with (
            patch("backend.app.ingestion.ebay.real_client.httpx.AsyncClient", return_value=ctx),
            patch("backend.app.ingestion.ebay.real_client.settings") as mock_settings,
        ):
            mock_settings.ebay_app_id = "app-id"
            mock_settings.ebay_cert_id = "cert-id"
            mock_settings.ebay_search_keywords = None

            client = RealEbayClient()
            await client.fetch_sold_listings(game=Game.ONE_PIECE, limit=5)

        for call in mock_client.get.call_args_list:
            params = call.kwargs.get("params") or (call.args[1] if len(call.args) > 1 else {})
            self.assertNotIn("categoryId", params)
            self.assertNotIn("category_ids", params)


class TestGameConfigEbay(unittest.TestCase):
    def test_pokemon_ebay_category_id(self):
        self.assertEqual(GAME_CONFIG[Game.POKEMON].ebay_category_id, "2536")

    def test_yugioh_ebay_category_id(self):
        self.assertEqual(GAME_CONFIG[Game.YUGIOH].ebay_category_id, "183454")

    def test_mtg_ebay_category_id(self):
        self.assertEqual(GAME_CONFIG[Game.MTG].ebay_category_id, "38292")

    def test_one_piece_ebay_category_id_is_none(self):
        # No dedicated eBay sub-category for One Piece TCG as of 2025-Q4.
        self.assertIsNone(GAME_CONFIG[Game.ONE_PIECE].ebay_category_id)

    def test_lorcana_ebay_category_id_is_none(self):
        # No dedicated eBay sub-category for Lorcana as of 2025-Q4.
        self.assertIsNone(GAME_CONFIG[Game.LORCANA].ebay_category_id)

    def test_pokemon_search_terms_non_empty(self):
        self.assertTrue(GAME_CONFIG[Game.POKEMON].ebay_search_terms)

    def test_all_live_games_have_search_terms(self):
        for game, meta in GAME_CONFIG.items():
            if meta.status == "live":
                self.assertTrue(
                    meta.ebay_search_terms,
                    f"{game} is live but has no ebay_search_terms",
                )

    def test_ebay_category_id_is_string_or_none(self):
        for game, meta in GAME_CONFIG.items():
            self.assertIsInstance(
                meta.ebay_category_id,
                (str, type(None)),
                f"{game}.ebay_category_id should be str or None",
            )


if __name__ == "__main__":
    unittest.main()
