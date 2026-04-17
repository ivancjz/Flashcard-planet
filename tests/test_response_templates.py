# tests/test_response_templates.py
import unittest
from unittest.mock import MagicMock, patch


def _make_card_data(
    *,
    name: str = "Pikachu",
    id: str = "pika-001",
    change: float = 5.2,
    sample_size=None,
    match_confidence=None,
    pro_gate_config=None,
):
    card = MagicMock()
    card.name = name
    card.id = id
    card.change = change
    card.sample_size = sample_size
    card.match_confidence = match_confidence
    card.pro_gate_config = pro_gate_config
    return card


class TestResponseTemplatesPriceAlert(unittest.TestCase):
    def setUp(self):
        import bot.link_builder as lb
        self._orig = lb.BASE_URL
        lb.BASE_URL = "http://localhost:8000"

    def tearDown(self):
        import bot.link_builder as lb
        lb.BASE_URL = self._orig

    def test_basic_structure_returned(self):
        from bot.main import ResponseTemplates
        result = ResponseTemplates.price_alert(_make_card_data())
        self.assertIn("embed", result)
        self.assertIn("title", result["embed"])
        self.assertIn("description", result["embed"])
        self.assertIn("url", result["embed"])

    def test_title_contains_card_name(self):
        from bot.main import ResponseTemplates
        result = ResponseTemplates.price_alert(_make_card_data(name="Charizard"))
        self.assertIn("Charizard", result["embed"]["title"])

    def test_description_contains_price_change(self):
        from bot.main import ResponseTemplates
        result = ResponseTemplates.price_alert(_make_card_data(change=7.5))
        self.assertIn("7.5", result["embed"]["description"])

    def test_sample_size_included_when_present(self):
        from bot.main import ResponseTemplates
        result = ResponseTemplates.price_alert(_make_card_data(sample_size=42))
        self.assertIn("42", result["embed"]["description"])
        self.assertIn("sales", result["embed"]["description"])

    def test_sample_size_omitted_when_none(self):
        from bot.main import ResponseTemplates
        result = ResponseTemplates.price_alert(_make_card_data(sample_size=None))
        self.assertNotIn("sales", result["embed"]["description"])

    def test_high_confidence_shows_checkmark(self):
        from bot.main import ResponseTemplates
        result = ResponseTemplates.price_alert(_make_card_data(match_confidence=95))
        self.assertIn("✅", result["embed"]["description"])
        self.assertIn("95", result["embed"]["description"])

    def test_low_confidence_shows_warning(self):
        from bot.main import ResponseTemplates
        result = ResponseTemplates.price_alert(_make_card_data(match_confidence=75))
        self.assertIn("⚠️", result["embed"]["description"])

    def test_pro_gate_locked_appends_upgrade_message(self):
        from bot.main import ResponseTemplates
        gate = MagicMock()
        gate.is_locked = True
        gate.to_bot_config.return_value = {
            "locked_message": "🔥 See long-term patterns (Pro Only)",
            "cta_text": "Upgrade to Pro",
            "upgrade_link": "/upgrade-from-discord",
        }
        result = ResponseTemplates.price_alert(_make_card_data(pro_gate_config=gate))
        self.assertIn("Pro Only", result["embed"]["description"])

    def test_pro_gate_unlocked_no_upgrade_message(self):
        from bot.main import ResponseTemplates
        gate = MagicMock()
        gate.is_locked = False
        result = ResponseTemplates.price_alert(_make_card_data(pro_gate_config=gate))
        self.assertNotIn("Pro Only", result["embed"]["description"])

    def test_url_uses_make_web_link_with_card_id(self):
        from bot.main import ResponseTemplates
        with patch("bot.main.make_web_link", return_value="http://test/cards/pika-001?utm_source=discord") as mock_link:
            result = ResponseTemplates.price_alert(_make_card_data(id="pika-001"))
        mock_link.assert_called_once()
        args = mock_link.call_args
        self.assertIn("pika-001", args[0][0])
        self.assertEqual(args[0][1]["command_type"], "price_alert")
        self.assertEqual(args[0][1]["card_id"], "pika-001")
        self.assertEqual(result["embed"]["url"], "http://test/cards/pika-001?utm_source=discord")
