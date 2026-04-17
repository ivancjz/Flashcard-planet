"""tests/test_banner.py — unit tests for banner.py ProGate helpers."""
from __future__ import annotations

import unittest

from backend.app.core.banner import _progate_html_from_config
from backend.app.core.response_types import ProGateConfig


class TestProgateHtmlFromConfig(unittest.TestCase):
    def _locked(self, urgency: str = "medium") -> ProGateConfig:
        return ProGateConfig(
            is_locked=True,
            feature_name="Extended Price History (180 days)",
            upgrade_reason="See long-term price patterns",
            urgency=urgency,
        )

    def _unlocked(self) -> ProGateConfig:
        return ProGateConfig(is_locked=False)

    def test_unlocked_returns_content_directly(self):
        html = _progate_html_from_config(self._unlocked(), "<p>visible</p>")
        self.assertIn("<p>visible</p>", html)

    def test_unlocked_has_no_overlay(self):
        html = _progate_html_from_config(self._unlocked(), "<p>x</p>")
        self.assertNotIn("progate__overlay", html)

    def test_locked_renders_feature_name(self):
        html = _progate_html_from_config(self._locked(), "<canvas></canvas>")
        self.assertIn("Extended Price History (180 days)", html)

    def test_locked_renders_upgrade_reason(self):
        html = _progate_html_from_config(self._locked(), "<canvas></canvas>")
        self.assertIn("See long-term price patterns", html)

    def test_locked_renders_upgrade_link(self):
        html = _progate_html_from_config(self._locked(), "<canvas></canvas>")
        self.assertIn("/upgrade", html)

    def test_locked_blurs_content(self):
        html = _progate_html_from_config(self._locked(), "<canvas id='x'></canvas>")
        self.assertIn("progate__blur", html)
        self.assertIn("<canvas id='x'></canvas>", html)

    def test_high_urgency_class(self):
        html = _progate_html_from_config(self._locked("high"), "<p/>")
        self.assertIn("progate__cta--high", html)

    def test_medium_urgency_class(self):
        html = _progate_html_from_config(self._locked("medium"), "<p/>")
        self.assertIn("progate__cta--medium", html)

    def test_low_urgency_class(self):
        html = _progate_html_from_config(self._locked("low"), "<p/>")
        self.assertIn("progate__cta--low", html)

    def test_unknown_urgency_defaults_to_medium_class(self):
        config = ProGateConfig(
            is_locked=True, feature_name="X", upgrade_reason="Y", urgency="unknown_val"
        )
        html = _progate_html_from_config(config, "<p/>")
        self.assertIn("progate__cta--medium", html)


if __name__ == "__main__":
    unittest.main()
