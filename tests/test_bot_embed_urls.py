# tests/test_bot_embed_urls.py
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch


def _parse_url(url: str):
    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(url)
    return parsed.path, parse_qs(parsed.query)


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestEmbedUrls(unittest.TestCase):
    def _make_interaction(self):
        interaction = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup.send = AsyncMock()
        interaction.user = MagicMock()
        interaction.user.id = 12345
        return interaction

    def test_price_embed_url_set(self):
        interaction = self._make_interaction()
        fake_results = [{"name": "Pikachu", "latest_price": "10.00", "currency": "USD",
                         "liquidity_score": None, "liquidity_label": None,
                         "sales_count_7d": None, "sales_count_30d": None,
                         "days_since_last_sale": None, "source_count": None,
                         "alert_confidence": None, "alert_confidence_label": None,
                         "percent_change": None, "source": "ebay", "captured_at": None,
                         "image_url": None, "category": None, "set_name": None}]
        with patch("bot.main.client") as mock_client, \
             patch("bot.main.make_web_link", return_value="http://localhost:8000/cards?utm_source=discord") as mock_link:
            mock_client.fetch_price = AsyncMock(return_value=fake_results)
            from bot.main import price
            run(price.callback(interaction, name="Pikachu"))
        mock_link.assert_called_once()
        self.assertEqual(mock_link.call_args[0][0], "/cards")
        self.assertEqual(mock_link.call_args[0][1]["command_type"], "slash_command")
        self.assertEqual(mock_link.call_args[0][1]["campaign"], "card_discovery")
        sent_embed = interaction.followup.send.call_args[1]["embed"]
        self.assertEqual(sent_embed.url, "http://localhost:8000/cards?utm_source=discord")

    def test_predict_embed_url_set(self):
        interaction = self._make_interaction()
        fake_results = [{"name": "Pikachu", "current_price": "10.00", "currency": "USD",
                         "prediction": "Up", "up_probability": "70", "down_probability": "10",
                         "flat_probability": "20", "points_used": 5, "captured_at": None,
                         "reason": "test", "image_url": None, "set_name": None}]
        with patch("bot.main.client") as mock_client, \
             patch("bot.main.make_web_link", return_value="http://localhost:8000/cards?utm_source=discord") as mock_link:
            mock_client.fetch_prediction = AsyncMock(return_value=fake_results)
            from bot.main import predict
            run(predict.callback(interaction, name="Pikachu"))
        mock_link.assert_called_once()
        self.assertEqual(mock_link.call_args[0][0], "/cards")
        self.assertEqual(mock_link.call_args[0][1]["campaign"], "card_discovery")

    def test_history_embed_url_set(self):
        interaction = self._make_interaction()
        fake_result = {"name": "Pikachu", "history": [], "points_returned": 0,
                       "current_price": None, "currency": None, "image_url": None,
                       "set_name": None, "liquidity_score": None, "liquidity_label": None,
                       "sales_count_7d": None, "sales_count_30d": None,
                       "days_since_last_sale": None, "source_count": None,
                       "alert_confidence": None, "alert_confidence_label": None}
        with patch("bot.main.client") as mock_client, \
             patch("bot.main.make_web_link", return_value="http://localhost:8000/cards?utm_source=discord") as mock_link:
            mock_client.fetch_history = AsyncMock(return_value=fake_result)
            from bot.main import history
            run(history.callback(interaction, name="Pikachu", limit=5))
        mock_link.assert_called_once()
        self.assertEqual(mock_link.call_args[0][0], "/cards")

    def test_topmovers_embed_url_set(self):
        interaction = self._make_interaction()
        fake_movers = [{"name": "Pikachu", "percent_change": "5.0", "latest_price": "10.00",
                        "liquidity_score": None, "liquidity_label": None,
                        "alert_confidence": None, "alert_confidence_label": None,
                        "sales_count_7d": None, "sales_count_30d": None,
                        "days_since_last_sale": None, "source_count": None}]
        with patch("bot.main.client") as mock_client, \
             patch("bot.main.make_web_link", return_value="http://localhost:8000/dashboard?utm_source=discord") as mock_link:
            mock_client.fetch_top_movers = AsyncMock(return_value=fake_movers)
            from bot.main import topmovers
            run(topmovers.callback(interaction, limit=5))
        mock_link.assert_called_once()
        self.assertEqual(mock_link.call_args[0][0], "/dashboard")
        self.assertEqual(mock_link.call_args[0][1]["campaign"], "card_discovery")

    def test_topvalue_embed_url_set(self):
        interaction = self._make_interaction()
        fake_items = [{"name": "Pikachu", "latest_price": "10.00", "currency": "USD",
                       "set_name": None, "category": None, "captured_at": None}]
        with patch("bot.main.client") as mock_client, \
             patch("bot.main.make_web_link", return_value="http://localhost:8000/dashboard?utm_source=discord") as mock_link:
            mock_client.fetch_top_value = AsyncMock(return_value=fake_items)
            from bot.main import topvalue
            run(topvalue.callback(interaction, limit=10))
        mock_link.assert_called_once()
        self.assertEqual(mock_link.call_args[0][0], "/dashboard")

    def test_watchlist_embed_url_set(self):
        interaction = self._make_interaction()
        fake_items = [{"name": "Pikachu", "threshold_up_percent": None,
                       "threshold_down_percent": None, "target_price": None}]
        with patch("bot.main.client") as mock_client, \
             patch("bot.main.make_web_link", return_value="http://localhost:8000/dashboard?utm_source=discord") as mock_link:
            mock_client.fetch_watchlist = AsyncMock(return_value=fake_items)
            from bot.main import watchlist
            run(watchlist.callback(interaction))
        mock_link.assert_called_once()
        self.assertEqual(mock_link.call_args[0][0], "/dashboard")
        self.assertEqual(mock_link.call_args[0][1]["campaign"], "engagement")

    def test_alerts_embed_url_set(self):
        interaction = self._make_interaction()
        with patch("bot.main.client") as mock_client, \
             patch("bot.main.make_web_link", return_value="http://localhost:8000/dashboard?utm_source=discord") as mock_link:
            mock_client.fetch_alerts = AsyncMock(return_value=[])
            from bot.main import alerts
            run(alerts.callback(interaction))
        mock_link.assert_called_once()
        self.assertEqual(mock_link.call_args[0][0], "/dashboard")
        self.assertEqual(mock_link.call_args[0][1]["campaign"], "engagement")

    def test_watch_tier_error_embed_url_points_to_upgrade(self):
        from bot.api_client import TierError
        interaction = self._make_interaction()
        with patch("bot.main.client") as mock_client, \
             patch("bot.main.make_web_link", return_value="http://localhost:8000/upgrade-from-discord?utm_source=discord") as mock_link:
            mock_client.create_watch = AsyncMock(side_effect=TierError("limit", "/upgrade"))
            from bot.main import watch
            run(watch.callback(interaction, asset_name="Pikachu",
                               threshold_up_percent=None, threshold_down_percent=None,
                               target_price=None, predict_signal_change=None,
                               predict_up_probability_above=None, predict_down_probability_above=None))
        mock_link.assert_called_once()
        self.assertEqual(mock_link.call_args[0][0], "/upgrade-from-discord")
        self.assertEqual(mock_link.call_args[0][1]["campaign"], "pro_conversion")

    def test_alerthistory_embed_url_set(self):
        interaction = self._make_interaction()
        with patch("bot.main.client") as mock_client, \
             patch("bot.main.make_web_link", return_value="http://localhost:8000/dashboard?utm_source=discord") as mock_link:
            mock_client.fetch_alert_history = AsyncMock(return_value=[])
            from bot.main import alerthistory
            run(alerthistory.callback(interaction, limit=10, asset_name=None))
        mock_link.assert_called_once()
        self.assertEqual(mock_link.call_args[0][0], "/dashboard")
        self.assertEqual(mock_link.call_args[0][1]["campaign"], "engagement")
