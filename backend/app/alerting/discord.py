"""Discord webhook alerting.

All functions are fire-and-forget: failures are logged but never re-raised.
The webhook URL is never written to logs to prevent accidental credential
exposure.
"""
from __future__ import annotations

import logging
from typing import Literal

import httpx

logger = logging.getLogger(__name__)

AlertLevel = Literal["info", "success", "warning", "error", "heartbeat"]

_EMOJI: dict[str, str] = {
    "info":      "ℹ️",
    "success":   "✅",
    "warning":   "⚠️",
    "error":     "🚨",
    "heartbeat": "💓",
}

_MAX_BODY_CHARS = 1800


def send_discord_alert(
    level: AlertLevel,
    title: str,
    body: str = "",
    *,
    settings=None,
) -> bool:
    """Post an alert to the configured Discord webhook.

    Returns True on success, False on any failure (URL not configured,
    network error, non-2xx response).  Never raises.
    """
    if settings is None:
        from backend.app.core.config import get_settings
        settings = get_settings()

    url: str | None = settings.discord_alert_webhook_url
    if not url:
        logger.debug("discord_alert_skipped level=%s title=%r (webhook not configured)", level, title)
        return False

    emoji = _EMOJI.get(level, "📢")
    content = f"{emoji} **{title}**"
    if body:
        content += f"\n```\n{body[:_MAX_BODY_CHARS]}\n```"

    try:
        response = httpx.post(url, json={"content": content}, timeout=5.0)
        response.raise_for_status()
        logger.info("discord_alert_sent level=%s title=%r", level, title)
        return True
    except httpx.HTTPStatusError as exc:
        logger.error(
            "discord_alert_failed level=%s title=%r http_status=%s",
            level, title, exc.response.status_code,
        )
        return False
    except Exception as exc:
        logger.error(
            "discord_alert_failed level=%s title=%r error_type=%s",
            level, title, type(exc).__name__,
        )
        return False
