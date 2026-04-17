import unittest
from unittest.mock import patch
from urllib.parse import urlparse, parse_qs


class TestMakeWebLink(unittest.TestCase):
    def setUp(self):
        import bot.link_builder as lb
        self._orig_base_url = lb.BASE_URL
        lb.BASE_URL = "http://localhost:8000"

    def tearDown(self):
        import bot.link_builder as lb
        lb.BASE_URL = self._orig_base_url

    def _parse(self, url: str) -> tuple[str, dict]:
        parsed = urlparse(url)
        return parsed.path, parse_qs(parsed.query)

    def test_required_utm_params_present(self):
        from bot.link_builder import make_web_link
        url = make_web_link("/cards", {"command_type": "slash_command", "campaign": "card_discovery"})
        path, qs = self._parse(url)
        self.assertEqual(path, "/cards")
        self.assertEqual(qs["utm_source"], ["discord"])
        self.assertEqual(qs["utm_medium"], ["slash_command"])
        self.assertEqual(qs["utm_campaign"], ["card_discovery"])
        self.assertEqual(qs["from"], ["discord"])

    def test_optional_signal_type(self):
        from bot.link_builder import make_web_link
        url = make_web_link("/signals", {
            "command_type": "price_alert",
            "campaign": "card_discovery",
            "signal_type": "BREAKOUT",
        })
        _, qs = self._parse(url)
        self.assertEqual(qs["utm_content"], ["BREAKOUT"])

    def test_optional_card_id(self):
        from bot.link_builder import make_web_link
        url = make_web_link("/cards/abc123", {
            "command_type": "price_alert",
            "campaign": "card_discovery",
            "card_id": "abc123",
        })
        _, qs = self._parse(url)
        self.assertEqual(qs["ref"], ["abc123"])

    def test_optional_user_tier(self):
        from bot.link_builder import make_web_link
        url = make_web_link("/dashboard", {
            "command_type": "slash_command",
            "campaign": "engagement",
            "user_tier": "pro",
        })
        _, qs = self._parse(url)
        self.assertEqual(qs["tier"], ["pro"])

    def test_no_signal_type_no_utm_content(self):
        from bot.link_builder import make_web_link
        url = make_web_link("/cards", {"command_type": "slash_command", "campaign": "card_discovery"})
        _, qs = self._parse(url)
        self.assertNotIn("utm_content", qs)

    def test_base_url_used(self):
        import bot.link_builder as lb
        lb.BASE_URL = "https://flashcardplanet.com"
        from bot.link_builder import make_web_link
        url = make_web_link("/cards", {"command_type": "slash_command", "campaign": "card_discovery"})
        self.assertTrue(url.startswith("https://flashcardplanet.com/cards?"))

    def test_path_preserved(self):
        from bot.link_builder import make_web_link
        url = make_web_link("/dashboard", {"command_type": "slash_command", "campaign": "engagement"})
        path, _ = self._parse(url)
        self.assertEqual(path, "/dashboard")
