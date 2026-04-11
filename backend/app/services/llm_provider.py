"""LLM provider abstraction.

Usage:
    from backend.app.services.llm_provider import get_llm_provider

    text = get_llm_provider().generate_text(system_prompt, user_message, max_tokens)

Set LLM_PROVIDER=gemini in .env to switch to Gemini. Default is Anthropic.
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Protocol

logger = logging.getLogger(__name__)

_KNOWN_PROVIDERS = frozenset({"anthropic", "gemini"})

# --- SDK imports (soft — missing packages degrade gracefully) ---

try:
    from anthropic import Anthropic as _Anthropic
    from anthropic import RateLimitError as _AnthropicRateLimitError
except ImportError:  # pragma: no cover
    _Anthropic = None  # type: ignore[assignment, misc]
    _AnthropicRateLimitError = None  # type: ignore[assignment, misc]

try:
    import google.generativeai as _genai  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover
    _genai = None  # type: ignore[assignment]


def _log(event: str, **fields: object) -> None:
    logger.warning(json.dumps({"event": event, **fields}, default=str, sort_keys=True))


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
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            _log("anthropic_unavailable_no_key")
            return None
        if _Anthropic is None:
            _log("anthropic_unavailable_import_error")
            return None

        model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
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


# --- Gemini implementation ---

class GeminiProvider:
    """Wraps the Google Generative AI SDK (google-generativeai).

    Passes the system string as system_instruction. No retry for MVP.
    Returns None (never raises) on any failure or misconfiguration.
    """

    def generate_text(self, system: str, user: str, max_tokens: int) -> str | None:  # noqa: ARG002
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            _log("gemini_unavailable_no_key")
            return None
        if _genai is None:
            _log("gemini_unavailable_import_error")
            return None

        model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        try:
            _genai.configure(api_key=api_key)
            model = _genai.GenerativeModel(
                model_name=model_name,
                system_instruction=system,
            )
            response = model.generate_content(user)
            text = (response.text or "").strip()
            return text or None
        except Exception as exc:  # noqa: BLE001
            _log("gemini_request_failed", error_type=type(exc).__name__, message=str(exc))
            return None


# --- Factory ---

def get_llm_provider() -> LLMProvider:
    """Return the configured LLM provider.

    Reads LLM_PROVIDER from the environment at call time so tests can override it.
    Unknown values log a warning and fall back to Anthropic.
    """
    provider = os.getenv("LLM_PROVIDER", "anthropic").lower()
    if provider not in _KNOWN_PROVIDERS:
        _log("llm_provider_unknown", value=provider, fallback="anthropic")
    if provider == "gemini":
        return GeminiProvider()
    return AnthropicProvider()
