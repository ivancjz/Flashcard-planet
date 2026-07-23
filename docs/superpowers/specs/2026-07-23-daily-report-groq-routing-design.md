# Daily Report Groq Routing Design

**Date:** 2026-07-23

**Status:** Approved

**Phase:** Flashcard Planet v2, Phase 5 AI Intelligence Engine
**Pull request:** #84

---

## 1. Context

Flashcard Planet already has a shared LLM provider abstraction with Anthropic,
Groq, and OpenAI implementations. Daily Report commentary resolves its provider
through the task-specific `daily_report_commentary` route.

The existing route selects OpenAI first and Groq second. The product decision is
to use Groq as the primary provider for Daily Report commentary while preserving
OpenAI as an operational fallback.

## 2. Decision

Route Daily Report commentary as:

```text
Groq primary -> OpenAI fallback
```

The change is scoped to the `daily_report_commentary` task route. It does not
change the global LLM default or the routing of signal explanations, mapping
disambiguation, structured tagging, or any other task.

## 3. Alternatives Considered

### 3.1 Groq Primary with OpenAI Fallback

Selected. It makes Groq the normal execution path while retaining availability
when Groq is unavailable or returns no usable result.

### 3.2 Groq Only

Rejected. This would meet the provider preference but would turn a temporary
Groq outage or missing key into an immediate Daily Report commentary failure.

### 3.3 Make Groq the Global Default

Rejected. This would alter unrelated AI workflows and expand the risk and test
surface beyond the Daily Report requirement.

## 4. Configuration

The implementation continues to use the existing settings:

- `GROQ_API_KEY`: required for the primary provider
- `GROQ_MODEL`: optional model override
- `GROQ_BASE_URL`: optional API base URL override
- `OPENAI_API_KEY`: optional fallback credential
- `OPENAI_MODEL`: optional fallback model override

No secret is added to source control. If Groq is not configured, the existing
fallback wrapper may try OpenAI. If neither provider is available, the current
typed `provider_unavailable` failure path remains unchanged.

The Daily Report AI scheduler remains default-off. Provider routing does not
enable the feature or trigger a live provider call by itself.

## 5. Runtime Flow

```text
Daily Report intelligence service
        |
        v
Resolve daily_report_commentary task
        |
        v
GroqProvider.generate_text_result(...)
        |
        +---- valid result ----> strict commentary validation
        |
        +---- unavailable -----> OpenAIProvider.generate_text_result(...)
                                      |
                                      v
                               strict commentary validation
```

Provider selection does not bypass any evidence, numeric, citation, policy, or
publication validation. The persisted internal metadata records the provider
and model that actually produced the accepted response.

## 6. Error Handling

- A missing Groq key returns no result and allows the fallback.
- Groq request, HTTP, parsing, or empty-response failures return no result and
  allow the fallback.
- A Groq response that reaches the commentary validator but violates the output
  contract is recorded through the existing validation failure path. It is not
  retried through another provider because fallback is a transport/provider
  availability boundary, not a policy-validation escape hatch.
- Provider exceptions and response bodies remain excluded from public API
  responses.

## 7. Test Requirements

1. The Daily Report route resolves `GroqProvider` as primary.
2. The same route resolves `OpenAIProvider` as fallback.
3. A successful Groq result is returned without calling OpenAI.
4. A missing or failed Groq result calls OpenAI once.
5. Result metadata identifies the provider and model that produced the text.
6. Existing commentary validation, orchestration, scheduler, API, and frontend
   behavior remains unchanged.

## 8. Documentation Changes

Update the Phase 5 execution record and PR description to state that Daily
Report commentary uses Groq first and OpenAI only as fallback. Retain the note
that no production or staging provider call was made during verification unless
a separately approved live smoke test occurs.

## 9. Acceptance Criteria

- `daily_report_commentary` is configured as `("groq", "openai")`.
- Focused provider and Daily Report tests pass.
- The implementation does not change another task route or the global default.
- No credentials or provider response content are committed.
- PR #84 accurately describes the Groq-first route.

