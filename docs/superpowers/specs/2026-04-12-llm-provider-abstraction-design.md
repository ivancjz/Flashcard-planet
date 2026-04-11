# LLM Provider Abstraction Design

**Date:** 2026-04-12
**Status:** Approved
**Scope:** Single provider protocol + Anthropic and Gemini implementations, wired into the three existing AI features

---

## 1. Overview

Add a thin provider abstraction so the three AI features (ai_mapper, signal_explainer, noise_filter) can run against either Anthropic or Gemini without changes to feature logic. The active provider is selected by `LLM_PROVIDER` env var. Current behavior is preserved exactly when `LLM_PROVIDER` is unset or `anthropic`.

---

## 2. Interface

A single file `backend/app/services/llm_provider.py` defines:

```python
class LLMProvider(Protocol):
    def generate_text(self, system: str, user: str, max_tokens: int) -> str | None: ...
```

`generate_text` is the only method. It takes a flat system string, a user message string, and a token ceiling. It returns the model's text response, or `None` if the provider is misconfigured or the call fails. All provider-specific details (SDK, auth, retry, caching) are encapsulated inside the implementation.

The name `generate_text` is intentional — it describes what happens without implying a specific interaction pattern. A structured output layer (JSON parsing, classification) may be added on top later, but that is out of scope here.

---

## 3. Implementations

### AnthropicProvider

Wraps the existing Anthropic SDK call, extracted verbatim from `ai_mapper._map_batch_with_client`. Behavior preserved:

- Reads `ANTHROPIC_API_KEY` and `ANTHROPIC_MODEL` (default `claude-sonnet-4-6`) from env.
- Returns `None` and logs if key is missing or `anthropic` package is not installed.
- Sends the system string as a single `cache_control: ephemeral` block.
- Retries up to 4 times on `RateLimitError` with exponential backoff (0.5 → 1.0 → 2.0 → 4.0 s).
- Returns joined text from all `text`-type content blocks, or `None` on any unhandled exception.

### GeminiProvider

New implementation using `google-generativeai`:

- Reads `GEMINI_API_KEY` and `GEMINI_MODEL` (default `gemini-2.0-flash`) from env.
- Returns `None` and logs if key is missing or `google.generativeai` package is not installed.
- Passes the system string as `system_instruction` to `GenerativeModel`.
- Calls `generate_content(user)` and returns `response.text`.
- No retry logic for MVP — failures return `None` and log.

### Factory

```python
def get_llm_provider() -> LLMProvider:
    if os.getenv("LLM_PROVIDER", "anthropic").lower() == "gemini":
        return GeminiProvider()
    return AnthropicProvider()
```

`LLM_PROVIDER` is read at call time (not module import time) so tests can patch it with `monkeypatch` or `os.environ`.

---

## 4. Consumer Changes

Each of the three feature files drops its inline `Anthropic` import, SDK call, and unavailability guard. They gain:

```python
from backend.app.services.llm_provider import get_llm_provider
```

And replace the SDK call with:

```python
text = get_llm_provider().generate_text(system, user, max_tokens)
```

### ai_mapper.py

- Concatenates `SYSTEM_PROMPT + "\n\n" + FEW_SHOT_EXAMPLES` into one string before calling.
- The retry loop is removed from `_map_batch_with_client` — retry is now inside `AnthropicProvider`.
- The `_pending_result` fallback on `None` response stays in `ai_mapper` — it is feature logic, not provider logic.
- The unavailability guard (`if not api_key or Anthropic is None`) is removed from `map_batch` — providers handle this internally.

### signal_explainer.py

- `_call_claude` is renamed `_call_llm`.
- Removes the `Anthropic` import and the key/import guard.
- Calls `get_llm_provider().generate_text(_SYSTEM_PROMPT, user_prompt, 256)`.

### noise_filter.py

- Removes the `Anthropic` import and the `if Anthropic is None` guard.
- Calls `get_llm_provider().generate_text(SYSTEM_PROMPT, user_text, 1024)`.
- Fallback (`return [True] * len(titles)`) stays in `filter_noise` — feature logic.

---

## 5. Configuration

| Env var | Default | Notes |
|---|---|---|
| `LLM_PROVIDER` | `anthropic` | `anthropic` or `gemini` |
| `ANTHROPIC_API_KEY` | — | Required when provider is `anthropic` |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-6` | Existing |
| `AI_BATCH_SIZE` | `20` | Existing |
| `AI_MAX_TOKENS` | `4096` | Existing |
| `GEMINI_API_KEY` | — | Required when provider is `gemini` |
| `GEMINI_MODEL` | `gemini-2.0-flash` | New |

`GEMINI_API_KEY` and `GEMINI_MODEL` are added to `backend/app/core/config.py` as optional string fields. `.env.example` is updated with both.

---

## 6. Error Handling

| Condition | Provider behaviour | Consumer behaviour |
|---|---|---|
| Key missing | Log warning, return `None` | Existing fallback (pending result / `[True]*n` / no explanation) |
| Package not installed | Log warning, return `None` | Same fallback |
| API call fails | Log warning, return `None` | Same fallback |
| Rate limit (Anthropic only) | Retry up to 4×, then `None` | Same fallback |

Consumers are unchanged — they already handle `None` gracefully.

---

## 7. Files Changed

| File | Action | Responsibility |
|---|---|---|
| `backend/app/services/llm_provider.py` | Create | Protocol, both implementations, factory |
| `backend/app/ingestion/matcher/ai_mapper.py` | Modify | Use `get_llm_provider()`, remove inline SDK call |
| `backend/app/services/signal_explainer.py` | Modify | Use `get_llm_provider()`, remove inline SDK call |
| `backend/app/ingestion/noise_filter.py` | Modify | Use `get_llm_provider()`, remove inline SDK call |
| `backend/app/core/config.py` | Modify | Add `GEMINI_API_KEY`, `GEMINI_MODEL` fields |
| `.env.example` | Modify | Document new env vars |
| `tests/test_llm_provider.py` | Create | Provider unit tests |

---

## 8. Testing

`tests/test_llm_provider.py` covers:

- `get_llm_provider()` returns `AnthropicProvider` when `LLM_PROVIDER` is unset or `"anthropic"`.
- `get_llm_provider()` returns `GeminiProvider` when `LLM_PROVIDER=gemini`.
- `AnthropicProvider.generate_text` returns `None` when `ANTHROPIC_API_KEY` is empty (no SDK call).
- `GeminiProvider.generate_text` returns `None` when `GEMINI_API_KEY` is empty (no SDK call).
- Three consumer modules (`ai_mapper`, `signal_explainer`, `noise_filter`) are importable and callable after refactor.

No live API calls in tests.

---

## 9. Out of Scope

- Streaming responses
- Structured output / JSON-mode at the provider level
- Per-feature provider override (all features share one `LLM_PROVIDER`)
- Gemini prompt caching
- Third provider (OpenAI, etc.)
