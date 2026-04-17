from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

_URGENCY_EMOJI = {"high": "🔥", "medium": "📈", "low": "💡"}
_URGENCY_CSS = {"high": "pro-gate-high", "medium": "pro-gate-medium", "low": "pro-gate-low"}


@dataclass(frozen=True)
class ProGateConfig:
    is_locked: bool
    feature_name: str = ""
    upgrade_reason: str = ""
    urgency: str = "medium"

    def to_web_config(self) -> dict:
        if not self.is_locked:
            return {"is_locked": False}
        return {
            "is_locked": True,
            "maskType": "blur",
            "ctaText": f"Unlock {self.feature_name} — Pro Only",
            "urgency": self.urgency,
            "cssClass": _URGENCY_CSS.get(self.urgency, "pro-gate-medium"),
        }

    def to_bot_config(self) -> dict | None:
        if not self.is_locked:
            return None
        emoji = _URGENCY_EMOJI.get(self.urgency, "📈")
        return {
            "locked_message": f"{emoji} {self.upgrade_reason} (Pro Only)",
            "cta_text": "Upgrade to Pro for full access",
            "upgrade_link": "/upgrade-from-discord",
        }


@dataclass(frozen=True)
class CardDetailResponse:
    card_name: str
    external_id: str
    current_price: Decimal | None
    price_history: list[Any]
    sample_size: int
    match_confidence_avg: Decimal | None
    data_age: str
    source_breakdown: dict[str, int]
    access_tier: str
    pro_gate_config: ProGateConfig | None


@dataclass(frozen=True)
class SignalsResponse:
    signals: list
    total_eligible: int
    access_tier: str
    pro_gate_config: ProGateConfig | None
