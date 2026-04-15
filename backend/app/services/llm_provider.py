"""LLM provider abstraction.

Usage:
    from backend.app.services.llm_provider import get_llm_provider

    text = get_llm_provider().generate_text(system_prompt, user_message, max_tokens)

Set LLM_PROVIDER=groq in .env to switch to Groq. Default is Anthropic.
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Protocol

import httpx

from backend.app.core.config import settings

logger = logging.getLogger(__name__)

_KNOWN_PROVIDERS = frozenset({"anthropic", "groq"})
_httpx_client_cls = httpx.Client


def _setting_value(name: str, attr: str, default: str = "") -> str:
    value = os.getenv(name)
    if value not in (None, ""):
        return value
    configured = getattr(settings, attr, "")
    if isinstance(configured, str) and configured:
        return configured
    return default

# --- SDK imports (soft — missing packages degrade gracefully) ---

try:
    from anthropic import Anthropic as _Anthropic
    from anthropic import RateLimitError as _AnthropicRateLimitError
except ImportError:  # pragma: no cover
    _Anthropic = None  # type: ignore[assignment, misc]
    _AnthropicRateLimitError = None  # type: ignore[assignment, misc]


def _log(event: str, level: int = logging.WARNING, **fields: object) -> None:
    logger.log(level, json.dumps({"event": event, **fields}, default=str, sort_keys=True))


# --- Protocol ---

class LLMProvider(Protocol):
    def generate_text(self, system: str, user: str, max_tokens: int) -> str | None:
        """Call the LLM and return the text response, or None on any failure."""
        ...


# --- Anthropic implementation ---

class AnthropicProvider:
    """Wraps the Anthropic Messages API.

    Preserves cache_control on the system prompt and retries on rate-limit errors.
    Returns None (never raises) on any failure or misconfiguration.
    """

    def generate_text(self, system: str, user: str, max_tokens: int) -> str | None:
        api_key = _setting_value("ANTHROPIC_API_KEY", "anthropic_api_key")
        if not api_key:
            _log("anthropic_unavailable_no_key", level=logging.INFO)
            return None
        if _Anthropic is None:
            _log("anthropic_unavailable_import_error", level=logging.INFO)
            return None

        model = _setting_value("ANTHROPIC_MODEL", "anthropic_model", "claude-sonnet-4-6")
        client = _Anthropic(api_key=api_key)
        delays = [0.5, 1.0, 2.0, 4.0]
        last_error: Exception | None = None

        for attempt, delay in enumerate([0.0, *delays], start=1):
            if delay:
                time.sleep(delay)
            try:
                response = client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    system=[
                        {
                            "type": "text",
                            "text": system,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                    messages=[
                        {
                            "role": "user",
                            "content": [{"type": "text", "text": user}],
                        }
                    ],
                )
                text = "".join(
                    block.text
                    for block in getattr(response, "content", [])
                    if getattr(block, "type", None) == "text"
                ).strip()
                return text or None
            except Exception as exc:  # noqa: BLE001
                if (
                    _AnthropicRateLimitError is not None
                    and isinstance(exc, _AnthropicRateLimitError)
                    and attempt <= len(delays)
                ):
                    last_error = exc
                    continue
                _log("anthropic_request_failed", error_type=type(exc).__name__, message=str(exc))
                return None

        _log(
            "anthropic_rate_limited",
            error_type=type(last_error).__name__ if last_error else "UnknownError",
            message=str(last_error or ""),
        )
        return None


class GroqProvider:
    """Wraps Groq's OpenAI-compatible chat completions API.

    Uses httpx directly (no SDK dependency). No retry for MVP.
    Returns None (never raises) on any failure or misconfiguration.
    """

    def generate_text(self, system: str, user: str, max_tokens: int) -> str | None:
        api_key = _setting_value("GROQ_API_KEY", "groq_api_key")
        if not api_key:
            _log("groq_unavailable_no_key", level=logging.INFO)
            return None

        model = _setting_value("GROQ_MODEL", "groq_model", "llama-3.3-70b-versatile")
        base_url = _setting_value("GROQ_BASE_URL", "groq_base_url", "https://api.groq.com/openai/v1")
        try:
            with _httpx_client_cls(base_url=base_url, timeout=30.0) as client:
                response = client.post(
                    "/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        "max_tokens": max_tokens,
                    },
                )
                response.raise_for_status()
                payload = response.json()
                text = payload["choices"][0]["message"]["content"].strip()
                return text or None
        except Exception as exc:  # noqa: BLE001
            _log("groq_request_failed", error_type=type(exc).__name__, message=str(exc))
            return None



# --- Factory ---

def get_llm_provider() -> LLMProvider:
    """Return the configured LLM provider.

    Reads LLM_PROVIDER from the environment at call time so tests can override it.
    Unknown values log a warning and fall back to Anthropic.
    """
    provider = _setting_value("LLM_PROVIDER", "llm_provider", "anthropic").lower()
    if provider not in _KNOWN_PROVIDERS:
        _log("llm_provider_unknown", value=provider, fallback="anthropic")
    if provider == "groq":
        return GroqProvider()
    return AnthropicProvider()
