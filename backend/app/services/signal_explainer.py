"""Signal Explainer — AI Priority 3.

Generates a plain-English explanation for why an asset received its signal label.
Uses Claude (claude-sonnet-4-6) with prompt caching on the system prompt.

Entry points:
  explain_signal(db, signal)  — generate + persist explanation on the AssetSignal row
  get_or_explain(db, signal)  — return cached if fresh, else regenerate
"""
from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from backend.app.models.asset import Asset
from backend.app.models.asset_signal import AssetSignal

logger = logging.getLogger(__name__)

EXPLANATION_MAX_AGE_HOURS = int(os.getenv("EXPLANATION_MAX_AGE_HOURS", "12"))

try:
    from anthropic import Anthropic
except ImportError:  # pragma: no cover
    Anthropic = None  # type: ignore[assignment,misc]

_SYSTEM_PROMPT = """You are a trading card market analyst for Flashcard Planet, a collectibles data platform.

Given signal data for a trading card, write a 2–3 sentence plain-English explanation of why this card received its signal label.

Rules:
- Be specific: mention the actual numbers (price change %, liquidity score, sales counts).
- Never give investment advice or tell the user to buy or sell.
- Do not use jargon like "alpha", "beta", or "momentum".
- Explain what the data shows, not what it means for the future.
- Keep it concise — 2 to 3 sentences maximum.
- Signal labels: BREAKOUT = very strong move with high liquidity. MOVE = notable price change. WATCH = directional prediction but no confirmed move. IDLE = no meaningful signal.
- Respond with only the explanation text. No JSON, no headers, no bullet points."""


def _build_user_prompt(signal: AssetSignal, asset_name: str) -> str:
    delta = (
        f"{float(signal.price_delta_pct):+.1f}%"
        if signal.price_delta_pct is not None
        else "N/A"
    )
    return json.dumps({
        "card_name": asset_name,
        "signal_label": signal.label,
        "price_change_pct": delta,
        "confidence_score": signal.confidence,
        "liquidity_score": signal.liquidity_score,
        "prediction": signal.prediction or "Not enough data",
    }, ensure_ascii=False)


def _call_claude(asset_name: str, signal: AssetSignal) -> str | None:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key or Anthropic is None:
        logger.warning(
            "signal_explainer_unavailable missing_api_key=%s anthropic_imported=%s",
            not bool(api_key),
            Anthropic is not None,
        )
        return None

    client = Anthropic(api_key=api_key)
    try:
        response = client.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
            max_tokens=256,
            system=[
                {
                    "type": "text",
                    "text": _SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": _build_user_prompt(signal, asset_name),
                }
            ],
        )
        text = "".join(
            block.text
            for block in getattr(response, "content", [])
            if getattr(block, "type", None) == "text"
        ).strip()
        return text or None
    except Exception as exc:
        logger.warning("signal_explainer_request_failed error=%s", exc)
        return None


def _is_fresh(signal: AssetSignal) -> bool:
    if signal.explanation is None or signal.explained_at is None:
        return False
    cutoff = datetime.now(UTC) - timedelta(hours=EXPLANATION_MAX_AGE_HOURS)
    explained = signal.explained_at
    if explained.tzinfo is None:
        explained = explained.replace(tzinfo=UTC)
    return explained >= cutoff


def explain_signal(db: Session, signal: AssetSignal) -> str | None:
    """Generate a fresh explanation and persist it on the signal row."""
    asset = db.get(Asset, signal.asset_id)
    asset_name = asset.name if asset else str(signal.asset_id)

    text = _call_claude(asset_name, signal)
    if text:
        signal.explanation = text
        signal.explained_at = datetime.now(UTC)
        db.commit()
    return text


def get_or_explain(db: Session, signal: AssetSignal) -> str | None:
    """Return cached explanation if fresh; otherwise regenerate."""
    if _is_fresh(signal):
        return signal.explanation
    return explain_signal(db, signal)
