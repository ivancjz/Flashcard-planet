# LLM Provider Abstraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `LLMProvider` protocol and `get_llm_provider()` factory so the three AI features (ai_mapper, signal_explainer, noise_filter) can run against either Anthropic or Gemini by setting `LLM_PROVIDER=gemini` in `.env` — with no change to feature logic.

**Architecture:** A single new file `backend/app/services/llm_provider.py` defines the protocol, both implementations, and the factory. Each of the three consumer files drops its inline SDK import and replaces the SDK call with `get_llm_provider().generate_text(system, user, max_tokens)`. Anthropic remains the default; existing retry and cache_control behaviour is preserved verbatim inside `AnthropicProvider`.

**Tech Stack:** Python, `anthropic>=0.40.0` (existing), `google-generativeai` (new), `unittest.mock`.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `backend/app/services/llm_provider.py` | Create | `LLMProvider` protocol, `AnthropicProvider`, `GeminiProvider`, `get_llm_provider()` factory |
| `backend/app/ingestion/noise_filter.py` | Modify | Use `get_llm_provider()`, remove inline Anthropic import |
| `backend/app/services/signal_explainer.py` | Modify | Use `get_llm_provider()`, rename `_call_claude` → `_call_llm` |
| `backend/app/ingestion/matcher/ai_mapper.py` | Modify | Use `get_llm_provider()`, add `_system_prompt()` helper, simplify `_map_batch_with_client` |
| `backend/app/core/config.py` | Modify | Add `gemini_api_key`, `gemini_model`, `llm_provider` fields |
| `.env.example` | Modify | Document `LLM_PROVIDER`, `GEMINI_API_KEY`, `GEMINI_MODEL` |
| `requirements.txt` | Modify | Add `google-generativeai>=0.8.0` |
| `tests/test_llm_provider.py` | Create | Provider factory, key-guard, and consumer fallback tests |

---

## Task 1: Create `llm_provider.py` and provider tests

**Files:**
- Create: `backend/app/services/llm_provider.py`
- Create: `tests/test_llm_provider.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_llm_provider.py`:

```python
"""Tests for LLM provider abstraction."""
from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch


class ProviderFactoryTests(unittest.TestCase):
    def test_default_provider_is_anthropic(self):
        env = {k: v for k, v in os.environ.items() if k != "LLM_PROVIDER"}
        with patch.dict(os.environ, env, clear=True):
            import backend.app.services.llm_provider as m
            self.assertIsInstance(m.get_llm_provider(), m.AnthropicProvider)

    def test_explicit_anthropic_returns_anthropic(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "anthropic"}):
            import backend.app.services.llm_provider as m
            self.assertIsInstance(m.get_llm_provider(), m.AnthropicProvider)

    def test_gemini_returns_gemini(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "gemini"}):
            import backend.app.services.llm_provider as m
            self.assertIsInstance(m.get_llm_provider(), m.GeminiProvider)

    def test_unknown_provider_falls_back_to_anthropic_and_logs(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "gpt-99"}):
            import backend.app.services.llm_provider as m
            with self.assertLogs("backend.app.services.llm_provider", level="WARNING"):
                result = m.get_llm_provider()
            self.assertIsInstance(result, m.AnthropicProvider)


class AnthropicProviderTests(unittest.TestCase):
    def test_returns_none_when_key_empty(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}):
            import backend.app.services.llm_provider as m
            result = m.AnthropicProvider().generate_text("sys", "user", 256)
            self.assertIsNone(result)

    def test_no_sdk_call_when_key_empty(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}):
            import backend.app.services.llm_provider as m
            original = m._Anthropic
            mock_cls = MagicMock()
            m._Anthropic = mock_cls
            try:
                m.AnthropicProvider().generate_text("sys", "user", 256)
                mock_cls.assert_not_called()
            finally:
                m._Anthropic = original


class GeminiProviderTests(unittest.TestCase):
    def test_returns_none_when_key_empty(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            import backend.app.services.llm_provider as m
            result = m.GeminiProvider().generate_text("sys", "user", 256)
            self.assertIsNone(result)

    def test_no_sdk_call_when_key_empty(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            import backend.app.services.llm_provider as m
            original = m._genai
            mock_genai = MagicMock()
            m._genai = mock_genai
            try:
                m.GeminiProvider().generate_text("sys", "user", 256)
                mock_genai.GenerativeModel.assert_not_called()
            finally:
                m._genai = original
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd c:/Flashcard-planet
python -m pytest tests/test_llm_provider.py -v
```

Expected: `ModuleNotFoundError` — `backend.app.services.llm_provider` does not exist yet.

- [ ] **Step 3: Create `backend/app/services/llm_provider.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```
cd c:/Flashcard-planet
python -m pytest tests/test_llm_provider.py -v
```

Expected: all 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/llm_provider.py tests/test_llm_provider.py
git commit -m "feat: add LLMProvider protocol with Anthropic and Gemini implementations"
```

---

## Task 2: Refactor `noise_filter.py`

**Files:**
- Modify: `backend/app/ingestion/noise_filter.py`
- Modify: `tests/test_llm_provider.py` (add consumer fallback test)

- [ ] **Step 1: Add the consumer fallback test to `tests/test_llm_provider.py`**

Append this class at the bottom of the file:

```python
class NoiseFallbackTests(unittest.TestCase):
    def test_filter_noise_returns_all_true_when_provider_returns_none(self):
        none_provider = MagicMock()
        none_provider.generate_text.return_value = None
        with patch(
            "backend.app.ingestion.noise_filter.get_llm_provider",
            return_value=none_provider,
        ):
            from backend.app.ingestion import noise_filter
            import importlib
            importlib.reload(noise_filter)
            result = noise_filter.filter_noise(["Charizard PSA 10", "50x bulk lot"])
            self.assertEqual(result, [True, True])
```

- [ ] **Step 2: Run the new test to verify it fails**

```
cd c:/Flashcard-planet
python -m pytest tests/test_llm_provider.py::NoiseFallbackTests -v
```

Expected: `FAIL` — `noise_filter` still imports from `anthropic` directly.

- [ ] **Step 3: Replace `backend/app/ingestion/noise_filter.py` entirely**

```python
from __future__ import annotations

import json
import logging

from backend.app.services.llm_provider import get_llm_provider

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You classify trading card marketplace listing titles for an ingestion pipeline.

Decide whether each title is a real individual card listing or noise.

Return true only for real individual card listings, including graded singles and raw singles.
Return false for noise, including:
- bulk lots, mystery lots, or quantity-heavy listings like "50x pokemon cards"
- accessories like sleeves, binders, deck boxes, playmats, toploaders, stands, cases
- sealed product like booster packs, booster boxes, ETBs, tins, collections, promo boxes, blisters
- non-card items like digital codes, plush, figures, posters, clothing, coins, empty boxes

Respond with strict JSON only: a single JSON array of booleans in the same order as the input titles.
true = real individual card listing
false = noise
"""


def _log_json(level: int, event: str, **fields: object) -> None:
    payload = json.dumps({"event": event, **fields}, default=str, sort_keys=True)
    if level == logging.WARNING:
        logger.warning(payload)
        return
    logger.log(level, payload)


def filter_noise(titles: list[str]) -> list[bool]:
    if not titles:
        return []
    user_payload = [{"index": i + 1, "title": t} for i, t in enumerate(titles)]
    user_text = (
        "Classify each title and return only a JSON array of booleans in the same order.\n"
        "Titles:\n" + json.dumps(user_payload, ensure_ascii=False)
    )
    text = get_llm_provider().generate_text(SYSTEM_PROMPT, user_text, 1024)
    if text is None:
        _log_json(logging.WARNING, "noise_filter_unavailable", reason="provider_returned_none")
        return [True] * len(titles)
    try:
        parsed = json.loads(text)
        if not isinstance(parsed, list):
            raise ValueError("Noise filter response must be a JSON array.")
        if len(parsed) != len(titles):
            raise ValueError("Noise filter response length did not match input length.")
        if any(type(item) is not bool for item in parsed):
            raise ValueError("Noise filter response must contain only booleans.")
        return parsed
    except Exception as exc:  # noqa: BLE001
        _log_json(
            logging.WARNING,
            "noise_filter_failed",
            error_type=type(exc).__name__,
            message=str(exc),
            titles=len(titles),
        )
        return [True] * len(titles)
```

- [ ] **Step 4: Run tests to verify they pass**

```
cd c:/Flashcard-planet
python -m pytest tests/test_llm_provider.py tests/test_noise_filter.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/ingestion/noise_filter.py tests/test_llm_provider.py
git commit -m "refactor: noise_filter uses LLM provider abstraction"
```

---

## Task 3: Refactor `signal_explainer.py`

**Files:**
- Modify: `backend/app/services/signal_explainer.py`
- Modify: `tests/test_llm_provider.py` (add consumer fallback test)

- [ ] **Step 1: Add the consumer fallback test to `tests/test_llm_provider.py`**

Append this class at the bottom of the file:

```python
class SignalExplainerFallbackTests(unittest.TestCase):
    def test_explain_signal_returns_none_and_skips_commit_when_provider_returns_none(self):
        import uuid
        none_provider = MagicMock()
        none_provider.generate_text.return_value = None
        with patch(
            "backend.app.services.signal_explainer.get_llm_provider",
            return_value=none_provider,
        ):
            from backend.app.services import signal_explainer
            import importlib
            importlib.reload(signal_explainer)
            db = MagicMock()
            asset_mock = MagicMock()
            asset_mock.name = "Charizard"
            db.get.return_value = asset_mock
            signal = MagicMock()
            signal.asset_id = uuid.uuid4()
            signal.label = "IDLE"
            signal.price_delta_pct = None
            signal.confidence = 50
            signal.liquidity_score = 30
            signal.prediction = None
            result = signal_explainer.explain_signal(db, signal)
            self.assertIsNone(result)
            db.commit.assert_not_called()
```

- [ ] **Step 2: Run the new test to verify it fails**

```
cd c:/Flashcard-planet
python -m pytest tests/test_llm_provider.py::SignalExplainerFallbackTests -v
```

Expected: `FAIL` — `signal_explainer` still imports `Anthropic` directly.

- [ ] **Step 3: Replace `backend/app/services/signal_explainer.py` entirely**

```python
"""Signal Explainer — AI Priority 3.

Generates a plain-English explanation for why an asset received its signal label.
Uses the configured LLM provider (default: Anthropic claude-sonnet-4-6).

Entry points:
  explain_signal(db, signal)  — generate + persist explanation on the AssetSignal row
  get_or_explain(db, signal)  — return cached if fresh, else regenerate
"""
from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from backend.app.models.asset import Asset
from backend.app.models.asset_signal import AssetSignal
from backend.app.services.llm_provider import get_llm_provider

logger = logging.getLogger(__name__)

EXPLANATION_MAX_AGE_HOURS = int(os.getenv("EXPLANATION_MAX_AGE_HOURS", "12"))

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
    return json.dumps(
        {
            "card_name": asset_name,
            "signal_label": signal.label,
            "price_change_pct": delta,
            "confidence_score": signal.confidence,
            "liquidity_score": signal.liquidity_score,
            "prediction": signal.prediction or "Not enough data",
        },
        ensure_ascii=False,
    )


def _call_llm(asset_name: str, signal: AssetSignal) -> str | None:
    return get_llm_provider().generate_text(
        _SYSTEM_PROMPT,
        _build_user_prompt(signal, asset_name),
        256,
    )


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
    text = _call_llm(asset_name, signal)
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
```

- [ ] **Step 4: Run tests to verify they pass**

```
cd c:/Flashcard-planet
python -m pytest tests/test_llm_provider.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/signal_explainer.py tests/test_llm_provider.py
git commit -m "refactor: signal_explainer uses LLM provider abstraction"
```

---

## Task 4: Refactor `ai_mapper.py`

**Files:**
- Modify: `backend/app/ingestion/matcher/ai_mapper.py`
- Modify: `tests/test_llm_provider.py` (add consumer fallback test)

- [ ] **Step 1: Add the consumer fallback test to `tests/test_llm_provider.py`**

Append this class at the bottom of the file:

```python
class AiMapperFallbackTests(unittest.TestCase):
    def test_map_batch_returns_pending_results_when_provider_returns_none(self):
        none_provider = MagicMock()
        none_provider.generate_text.return_value = None
        with patch(
            "backend.app.ingestion.matcher.ai_mapper.get_llm_provider",
            return_value=none_provider,
        ):
            from backend.app.ingestion.matcher import ai_mapper
            import importlib
            importlib.reload(ai_mapper)
            results = ai_mapper.map_batch(["Charizard VMAX PSA 10", "Pikachu Alt Art"])
            self.assertEqual(len(results), 2)
            self.assertTrue(all(r.status == "pending" for r in results))
```

- [ ] **Step 2: Run the new test to verify it fails**

```
cd c:/Flashcard-planet
python -m pytest tests/test_llm_provider.py::AiMapperFallbackTests -v
```

Expected: `FAIL` — `ai_mapper` still imports from `anthropic` directly.

- [ ] **Step 3: Replace `backend/app/ingestion/matcher/ai_mapper.py` entirely**

```python
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, Field, ValidationError

from backend.app.ingestion.matcher.rule_engine import normalize_listing_title
from backend.app.services.llm_provider import get_llm_provider

logger = logging.getLogger(__name__)


def _log_json(level: int, event: str, **fields: object) -> None:
    logger.log(level, json.dumps({"event": event, **fields}, default=str, sort_keys=True))


_SYSTEM_PROMPT = """You are an expert trading card identifier for Flashcard Planet.
Given raw eBay listing titles, extract structured card identity fields.

Rules:
- game is always "Pokemon" for this pipeline
- grade_company: PSA / BGS / CGC / SGC only, null if raw
- grade_score: numeric only, null if ungraded
- variant: SAR / IR / UR / HR / FA / Alt Art / Rainbow / Full Art, null if standard
- language: EN / JP / KR / ZH / DE / FR, default EN if unclear
- confidence: 0.0-1.0
- card_number: exact format like 199/165 or null if unknown
- Respond with strict JSON only.
"""

_FEW_SHOT_EXAMPLES = """[
  {
    "title": "Pokemon Charizard ex SAR 199/165 SV151 PSA 10",
    "result": {
      "name": "Charizard ex",
      "set_name": "Scarlet & Violet 151",
      "card_number": "199/165",
      "variant": "SAR",
      "grade_company": "PSA",
      "grade_score": 10.0,
      "language": "EN",
      "confidence": 0.97
    }
  },
  {
    "title": "PIKACHU FULL ART PROMO JAPANESE MINT",
    "result": {
      "name": "Pikachu",
      "set_name": null,
      "card_number": null,
      "variant": "Full Art",
      "grade_company": null,
      "grade_score": null,
      "language": "JP",
      "confidence": 0.61
    }
  }
]"""


def _system_prompt() -> str:
    """Return the combined system + few-shot string passed to the provider."""
    return _SYSTEM_PROMPT + "\n\n" + _FEW_SHOT_EXAMPLES


class AiListingPayload(BaseModel):
    title: str
    name: str | None = None
    set_name: str | None = None
    card_number: str | None = None
    variant: str | None = None
    language: str | None = None
    grade_company: str | None = None
    grade_score: float | None = None
    confidence: float = Field(ge=0.0, le=1.0)


class AiBatchPayload(BaseModel):
    results: list[AiListingPayload]


@dataclass(slots=True)
class AiMatchResult:
    raw_title: str
    normalized_title: str
    name: str | None
    set_name: str | None
    card_number: str | None
    variant: str | None
    language: str | None
    grade_company: str | None
    grade_score: Decimal | None
    confidence: Decimal
    status: str
    method: str


def map_batch(titles: list[str]) -> list[AiMatchResult]:
    if not titles:
        return []
    batch_size = max(int(os.getenv("AI_BATCH_SIZE", "20")), 1)
    mapped: list[AiMatchResult] = []
    for start in range(0, len(titles), batch_size):
        batch = titles[start : start + batch_size]
        mapped.extend(_map_batch(batch))
    return mapped


def _map_batch(titles: list[str]) -> list[AiMatchResult]:
    user_prompt = json.dumps({
        "titles": [{"index": i + 1, "title": t} for i, t in enumerate(titles)],
        "instructions": 'Return JSON object {"results": [...]} with one result per title in the same order.',
    })
    text = get_llm_provider().generate_text(
        _system_prompt(),
        user_prompt,
        int(os.getenv("AI_MAX_TOKENS", "4096")),
    )
    if text is None:
        return [_pending_result(t) for t in titles]
    try:
        parsed = AiBatchPayload.model_validate(json.loads(text))
        return _to_results(parsed, titles)
    except ValidationError as exc:
        _log_json(logging.WARNING, "ai_mapper_validation_failed", error=str(exc))
        return [_pending_result(t) for t in titles]
    except json.JSONDecodeError as exc:
        _log_json(logging.WARNING, "ai_mapper_json_decode_failed", error=str(exc))
        return [_pending_result(t) for t in titles]
    except Exception as exc:  # noqa: BLE001
        _log_json(logging.WARNING, "ai_mapper_request_failed", error_type=type(exc).__name__, message=str(exc))
        return [_pending_result(t) for t in titles]


def _to_results(payload: AiBatchPayload, titles: list[str]) -> list[AiMatchResult]:
    indexed = {item.title: item for item in payload.results}
    results: list[AiMatchResult] = []
    for title in titles:
        item = indexed.get(title)
        if item is None:
            results.append(_pending_result(title))
            continue
        grade_score: Decimal | None = None
        if item.grade_score is not None:
            try:
                grade_score = Decimal(str(item.grade_score))
            except InvalidOperation:
                grade_score = None
        confidence = Decimal(str(item.confidence)).quantize(Decimal("0.001"))
        status = (
            "mapped"
            if confidence >= Decimal(os.getenv("AI_CONFIDENCE_THRESHOLD_REVIEW", "0.50"))
            else "review"
        )
        results.append(
            AiMatchResult(
                raw_title=title,
                normalized_title=normalize_listing_title(title),
                name=item.name,
                set_name=item.set_name,
                card_number=item.card_number,
                variant=item.variant,
                language=item.language or "EN",
                grade_company=item.grade_company,
                grade_score=grade_score,
                confidence=confidence,
                status=status,
                method="ai",
            )
        )
    return results


def _pending_result(title: str) -> AiMatchResult:
    return AiMatchResult(
        raw_title=title,
        normalized_title=normalize_listing_title(title),
        name=None,
        set_name=None,
        card_number=None,
        variant=None,
        language="EN",
        grade_company=None,
        grade_score=None,
        confidence=Decimal("0.000"),
        status="pending",
        method="ai",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```
cd c:/Flashcard-planet
python -m pytest tests/test_llm_provider.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/ingestion/matcher/ai_mapper.py tests/test_llm_provider.py
git commit -m "refactor: ai_mapper uses LLM provider abstraction, add _system_prompt() helper"
```

---

## Task 5: Config, env, requirements, and final verification

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `.env.example`
- Modify: `requirements.txt`

- [ ] **Step 1: Add Gemini fields to `backend/app/core/config.py`**

Add these three lines after `admin_api_key: str = ""` (line 75):

```python
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    llm_provider: str = "anthropic"
```

The full Settings class around the insertion point should look like:

```python
    admin_api_key: str = ""
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    llm_provider: str = "anthropic"
    secret_key: str = Field(default="change-me-in-production-use-a-long-random-string")
```

- [ ] **Step 2: Add entries to `.env.example`**

Add a new section after the last line of `.env.example`:

```
# AI provider selection
# Set to "gemini" to use Google Gemini instead of Anthropic.
# Default is "anthropic".
LLM_PROVIDER=anthropic

# Anthropic (default provider)
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-sonnet-4-6

# Google Gemini (alternate provider)
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.0-flash
```

- [ ] **Step 3: Add `google-generativeai` to `requirements.txt`**

Add this line after `anthropic>=0.40.0`:

```
google-generativeai>=0.8.0
```

- [ ] **Step 4: Install the new dependency**

```
cd c:/Flashcard-planet
pip install google-generativeai>=0.8.0
```

Expected: package installs successfully.

- [ ] **Step 5: Run the full test suite**

```
cd c:/Flashcard-planet
python -m pytest tests/ -v
```

Expected: all tests PASS, no regressions.

- [ ] **Step 6: Commit and push**

```bash
git add backend/app/core/config.py .env.example requirements.txt
git commit -m "config: add GEMINI_API_KEY, GEMINI_MODEL, LLM_PROVIDER settings"
git push
```

---

## Self-Review

**Spec coverage:**
- ✅ `LLMProvider` protocol with `generate_text(system, user, max_tokens) -> str | None` — Task 1
- ✅ `AnthropicProvider` — preserves cache_control, retry, key guard — Task 1
- ✅ `GeminiProvider` — key guard, import guard, three distinct log events — Task 1
- ✅ Unknown `LLM_PROVIDER` value logs warning and falls back — Task 1 (`get_llm_provider`)
- ✅ Empty string normalised to `None` — Task 1 (both providers do `.strip()` and `return text or None`)
- ✅ `_system_prompt()` helper in `ai_mapper` — Task 4
- ✅ `noise_filter` consumer fallback test — Task 2
- ✅ `signal_explainer` consumer fallback test — Task 3
- ✅ `ai_mapper` consumer fallback test — Task 4
- ✅ Config fields — Task 5
- ✅ `.env.example` documentation — Task 5
- ✅ `google-generativeai` in `requirements.txt` — Task 5

**No placeholders found.**

**Type consistency:** `generate_text(system: str, user: str, max_tokens: int) -> str | None` used identically in Protocol definition (Task 1), `AnthropicProvider` (Task 1), `GeminiProvider` (Task 1), and all three consumer call sites (Tasks 2–4).
