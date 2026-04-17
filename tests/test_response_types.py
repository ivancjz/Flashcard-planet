import pytest
from backend.app.core.response_types import ProGateConfig, CardDetailResponse, SignalsResponse
from decimal import Decimal
from datetime import datetime, timezone


class TestProGateConfig:
    def test_unlocked_config_returns_no_web_cta(self):
        cfg = ProGateConfig(is_locked=False)
        result = cfg.to_web_config()
        assert result["is_locked"] is False
        assert "ctaText" not in result

    def test_locked_config_to_web_config(self):
        cfg = ProGateConfig(
            is_locked=True,
            feature_name="Extended Price History",
            upgrade_reason="See long-term price patterns",
            urgency="medium",
        )
        result = cfg.to_web_config()
        assert result["maskType"] == "blur"
        assert result["ctaText"] == "Unlock Extended Price History — Pro Only"
        assert result["urgency"] == "medium"
        assert result["cssClass"] == "pro-gate-medium"

    def test_locked_config_to_bot_config(self):
        cfg = ProGateConfig(
            is_locked=True,
            feature_name="Extended Price History",
            upgrade_reason="See long-term price patterns",
            urgency="high",
        )
        result = cfg.to_bot_config()
        assert result["locked_message"] == "🔥 See long-term price patterns (Pro Only)"
        assert result["cta_text"] == "Upgrade to Pro for full access"
        assert result["upgrade_link"] == "/upgrade-from-discord"

    def test_bot_emoji_matches_urgency_medium(self):
        cfg = ProGateConfig(is_locked=True, upgrade_reason="x", urgency="medium")
        assert cfg.to_bot_config()["locked_message"].startswith("📈")

    def test_bot_emoji_matches_urgency_low(self):
        cfg = ProGateConfig(is_locked=True, upgrade_reason="x", urgency="low")
        assert cfg.to_bot_config()["locked_message"].startswith("💡")

    def test_unlocked_config_to_bot_config_returns_none(self):
        cfg = ProGateConfig(is_locked=False)
        assert cfg.to_bot_config() is None


class TestCardDetailResponse:
    def test_can_be_constructed_with_required_fields(self):
        response = CardDetailResponse(
            card_name="Charizard Base Set",
            external_id="base1-4",
            current_price=Decimal("150.00"),
            price_history=[],
            sample_size=47,
            match_confidence_avg=Decimal("0.85"),
            data_age="Updated 3 hours ago",
            source_breakdown={"eBay": 70, "TCG": 30},
            access_tier="free",
            pro_gate_config=None,
        )
        assert response.card_name == "Charizard Base Set"
        assert response.sample_size == 47


class TestSignalsResponse:
    def test_can_be_constructed(self):
        response = SignalsResponse(
            signals=[],
            total_eligible=10,
            access_tier="free",
            pro_gate_config=None,
        )
        assert response.total_eligible == 10
