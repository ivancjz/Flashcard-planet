from __future__ import annotations

from datetime import UTC, datetime
from unittest import TestCase

from bot.main import (
    bot,
    build_alerts_embed,
    build_history_embed,
    build_prediction_embed,
    build_price_embed,
    build_topvalue_embed,
    format_history_timestamp,
)


class BotHistoryEmbedTests(TestCase):
    def test_core_slash_commands_still_register_on_import(self):
        command_names = {command.name for command in bot.tree.get_commands()}

        self.assertIn("price", command_names)
        self.assertIn("history", command_names)
        self.assertIn("predict", command_names)

    def test_format_history_timestamp_renders_plain_text_with_relative_suffix(self):
        now = datetime(2026, 4, 2, 14, 36, tzinfo=UTC)

        formatted = format_history_timestamp("2026-04-02T14:31:00+00:00", now=now)

        self.assertEqual(formatted, "2026-04-02 14:31 (5m ago)")

    def test_format_history_timestamp_accepts_epoch_seconds(self):
        now = datetime(2026, 4, 2, 14, 36, tzinfo=UTC)
        epoch_seconds = int(datetime(2026, 4, 2, 14, 31, tzinfo=UTC).timestamp())

        formatted = format_history_timestamp(epoch_seconds, now=now)

        self.assertEqual(formatted, "2026-04-02 14:31 (5m ago)")

    def test_build_history_embed_uses_plain_text_timestamps(self):
        now = datetime(2026, 4, 2, 14, 36, tzinfo=UTC)
        item = {
            "name": "Bulbasaur",
            "current_price": "0.18",
            "currency": "USD",
            "points_returned": 3,
            "set_name": "Scarlet & Violet 151",
            "history": [
                {"captured_at": "2026-04-02T14:31:00+00:00", "price": "0.18", "currency": "USD"},
                {"captured_at": "2026-04-02T14:26:00+00:00", "price": "0.18", "currency": "USD"},
                {"captured_at": "2026-04-02T14:21:00+00:00", "price": "0.18", "currency": "USD"},
            ],
        }

        embed = build_history_embed(item, limit=5, now=now)

        self.assertEqual(
            [(field.name, field.value) for field in embed.fields],
            [
                ("Asset", "Bulbasaur"),
                ("Set", "Scarlet & Violet 151"),
                ("Recent movement", "No change across returned points."),
                ("Current price", "0.18 USD"),
                ("Points returned", "3"),
            ],
        )
        self.assertEqual(
            embed.description,
            "\n".join(
                [
                    "`1.` 2026-04-02 14:31 (5m ago) | 0.18 USD",
                    "`2.` 2026-04-02 14:26 (10m ago) | 0.18 USD",
                    "`3.` 2026-04-02 14:21 (15m ago) | 0.18 USD",
                ]
            ),
        )
        self.assertNotIn("<t:", embed.description)

    def test_build_history_embed_summarizes_recent_changes(self):
        now = datetime(2026, 4, 2, 14, 36, tzinfo=UTC)
        item = {
            "name": "Bulbasaur",
            "current_price": "0.20",
            "currency": "USD",
            "points_returned": 5,
            "set_name": "Scarlet & Violet 151",
            "history": [
                {"captured_at": "2026-04-02T14:31:00+00:00", "price": "0.20", "currency": "USD"},
                {"captured_at": "2026-04-02T14:26:00+00:00", "price": "0.18", "currency": "USD"},
                {"captured_at": "2026-04-02T14:21:00+00:00", "price": "0.18", "currency": "USD"},
                {"captured_at": "2026-04-02T14:16:00+00:00", "price": "0.19", "currency": "USD"},
                {"captured_at": "2026-04-02T14:11:00+00:00", "price": "0.19", "currency": "USD"},
            ],
        }

        embed = build_history_embed(item, limit=5, now=now)

        recent_movement_field = next(field for field in embed.fields if field.name == "Recent movement")
        self.assertEqual(
            recent_movement_field.value,
            "2 changes across 5 returned points.\nLatest move: +0.02 USD vs previous point.",
        )

    def test_build_price_embed_uses_plain_text_captured_at(self):
        embed = build_price_embed(
            {
                "name": "Bulbasaur",
                "category": "Pokemon",
                "set_name": "Scarlet & Violet 151",
                "latest_price": "0.18",
                "currency": "USD",
                "source": "pokemon_tcg_api",
                "captured_at": "2026-04-02T14:31:00+00:00",
            },
            match_count=1,
        )

        self.assertEqual(
            embed.description,
            "**Bulbasaur**\nSet: Scarlet & Violet 151\nCategory: Pokemon",
        )
        self.assertEqual(
            [(field.name, field.value) for field in embed.fields[:2]],
            [
                ("Latest price", "0.18 USD"),
                ("Source", "pokemon_tcg_api"),
            ],
        )
        captured_at_field = next(field for field in embed.fields if field.name == "Captured at")
        self.assertIn("2026-04-02 14:31", captured_at_field.value)
        self.assertNotIn("<t:", captured_at_field.value)

    def test_build_prediction_embed_uses_plain_text_captured_at(self):
        embed = build_prediction_embed(
            {
                "name": "Bulbasaur",
                "current_price": "0.18",
                "currency": "USD",
                "set_name": "Scarlet & Violet 151",
                "prediction": "Flat",
                "up_probability": "10.00",
                "down_probability": "15.00",
                "flat_probability": "75.00",
                "points_used": 12,
                "captured_at": "2026-04-02T14:31:00+00:00",
                "reason": "Recent prices are unchanged.",
            },
            match_count=1,
        )

        self.assertEqual(embed.description, "**Bulbasaur**\nSet: Scarlet & Violet 151")
        probabilities_field = next(field for field in embed.fields if field.name == "Probabilities")
        self.assertEqual(
            probabilities_field.value,
            "Up: 10%\nDown: 15%\nFlat: 75%",
        )
        captured_at_field = next(field for field in embed.fields if field.name == "Captured at")
        self.assertIn("2026-04-02 14:31", captured_at_field.value)
        self.assertNotIn("<t:", captured_at_field.value)

    def test_build_topvalue_embed_uses_plain_text_latest_update(self):
        embed = build_topvalue_embed(
            [
                {
                    "name": "Bulbasaur",
                    "latest_price": "0.18",
                    "currency": "USD",
                    "set_name": "Scarlet & Violet 151",
                    "captured_at": "2026-04-02T14:31:00+00:00",
                }
            ],
            limit=1,
        )

        self.assertEqual(
            embed.description,
            "`1.` **Bulbasaur** - 0.18 USD\nSet: Scarlet & Violet 151",
        )
        self.assertIsNotNone(embed.footer.text)
        self.assertIn("Latest update: 2026-04-02 14:31", embed.footer.text)
        self.assertNotIn("<t:", embed.footer.text)

    def test_build_alerts_embed_uses_spaced_multiline_blocks(self):
        embed = build_alerts_embed(
            [
                {
                    "asset_name": "Bulbasaur",
                    "target_price": None,
                    "direction": None,
                    "alert_type": "PRICE_UP_THRESHOLD",
                    "threshold_percent": "5.00",
                    "is_armed": True,
                    "last_triggered_at": "2026-04-02T14:31:00+00:00",
                    "latest_price": "0.18",
                    "currency": "USD",
                    "current_prediction": "Flat",
                    "up_probability": "10.00",
                    "down_probability": "15.00",
                    "flat_probability": "75.00",
                    "last_observed_signal": None,
                }
            ]
        )

        self.assertIn("`1.` **Bulbasaur**", embed.description)
        self.assertIn("Rule: Price up 5% vs previous real price", embed.description)
        self.assertIn("Status: Active | Armed", embed.description)
        self.assertIn("Triggered: 2026-04-02 14:31", embed.description)
        self.assertIn("Latest: 0.18 USD", embed.description)
        self.assertIn("Prediction: Flat | Up 10% | Down 15% | Flat 75%", embed.description)
        self.assertNotIn("<t:", embed.description)
