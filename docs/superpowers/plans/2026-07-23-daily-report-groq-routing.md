# Daily Report Groq Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Groq the primary Daily Report commentary provider while retaining OpenAI as the availability fallback.

**Architecture:** Keep the existing provider implementations and `FallbackLLMProvider`. Change only the `daily_report_commentary` task route from OpenAI-first to Groq-first, prove the order and fallback behavior with routing tests, and update operator-facing configuration and verification records.

**Tech Stack:** Python 3.12, `unittest`, `pytest`, `httpx`, Pydantic settings, GitHub pull requests

---

## File Map

- `backend/app/services/llm_provider.py`: owns task-specific provider routing.
- `tests/test_llm_provider.py`: proves provider order and fallback behavior.
- `.env.example`: explains the credentials and role of each provider.
- `docs/flashcard-planet-v2/CODEX_EXECUTION_PLAN.md`: records the delivered provider decision and final verification.
- `docs/superpowers/specs/2026-07-23-daily-report-groq-routing-design.md`: approved design; no implementation edits expected.

### Task 1: Route Daily Report Commentary Through Groq First

**Files:**
- Modify: `tests/test_llm_provider.py:313-320`
- Modify: `backend/app/services/llm_provider.py:330-350`

- [ ] **Step 1: Replace the existing routing assertion and add execution-order tests**

Replace `test_daily_report_commentary_routes_to_openai_primary` and add the two
behavior tests below inside `ProviderRouterTests`:

```python
def test_daily_report_commentary_routes_to_groq_primary(self):
    import backend.app.services.llm_provider as m

    provider = m.get_llm_provider_for_task("daily_report_commentary")

    self.assertIsInstance(provider, m.FallbackLLMProvider)
    self.assertIsInstance(provider._primary, m.GroqProvider)
    self.assertIsInstance(provider._fallback, m.OpenAIProvider)

def test_daily_report_commentary_uses_groq_without_calling_openai(self):
    import backend.app.services.llm_provider as m

    groq_result = m.LLMTextResult(
        text='{"headline":"Groq"}',
        provider="groq",
        model="groq-test-model",
    )
    openai_result = m.LLMTextResult(
        text='{"headline":"OpenAI"}',
        provider="openai",
        model="openai-test-model",
    )
    with (
        patch.object(
            m.GroqProvider,
            "generate_text_result",
            return_value=groq_result,
        ) as groq_call,
        patch.object(
            m.OpenAIProvider,
            "generate_text_result",
            return_value=openai_result,
        ) as openai_call,
    ):
        provider = m.get_llm_provider_for_task("daily_report_commentary")
        result = provider.generate_text_result("system", "user", 256)

    self.assertEqual(result, groq_result)
    groq_call.assert_called_once_with("system", "user", 256)
    openai_call.assert_not_called()

def test_daily_report_commentary_falls_back_to_openai(self):
    import backend.app.services.llm_provider as m

    openai_result = m.LLMTextResult(
        text='{"headline":"OpenAI"}',
        provider="openai",
        model="openai-test-model",
    )
    with (
        patch.object(
            m.GroqProvider,
            "generate_text_result",
            return_value=None,
        ) as groq_call,
        patch.object(
            m.OpenAIProvider,
            "generate_text_result",
            return_value=openai_result,
        ) as openai_call,
    ):
        provider = m.get_llm_provider_for_task("daily_report_commentary")
        result = provider.generate_text_result("system", "user", 256)

    self.assertEqual(result, openai_result)
    groq_call.assert_called_once_with("system", "user", 256)
    openai_call.assert_called_once_with("system", "user", 256)
```

- [ ] **Step 2: Run the routing tests and verify the new expectation fails**

Run:

```powershell
python -m pytest tests/test_llm_provider.py::ProviderRouterTests -q
```

Expected: FAIL because the current route constructs `OpenAIProvider` as
`_primary` and `GroqProvider` as `_fallback`.

- [ ] **Step 3: Swap only the Daily Report task route**

Change the routing entry in `backend/app/services/llm_provider.py` to:

```python
_TASK_ROUTING: dict[str, tuple[str, str]] = {
    "signal_explanation": ("openai", "groq"),
    "mapping_disambiguation": ("groq", "openai"),
    "structured_tagging": ("openai", "groq"),
    "daily_report_commentary": ("groq", "openai"),
}
```

Do not change `_PROVIDER_MAP`, `get_llm_provider()`, another task route, the
Groq HTTP client, or the global `llm_provider` default.

- [ ] **Step 4: Run the complete provider test file**

Run:

```powershell
python -m pytest tests/test_llm_provider.py -q
```

Expected: `30 passed`.

- [ ] **Step 5: Commit the routing change**

```powershell
git add backend/app/services/llm_provider.py tests/test_llm_provider.py
git commit -m "feat: route daily report AI through Groq"
```

### Task 2: Update Provider Configuration Guidance

**Files:**
- Modify: `.env.example:53-70`
- Modify: `docs/flashcard-planet-v2/CODEX_EXECUTION_PLAN.md:99-108`

- [ ] **Step 1: Clarify task routing in the environment example**

Keep `LLM_PROVIDER=anthropic` unchanged because it is the global provider
default for callers that do not use task routing. Replace the provider comments
with:

```dotenv
# Groq (Daily Report AI primary provider)
GROQ_API_KEY=
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_BASE_URL=https://api.groq.com/openai/v1

# OpenAI (Daily Report AI fallback and selected-task provider)
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
OPENAI_BASE_URL=https://api.openai.com/v1
```

- [ ] **Step 2: Record the Groq-first decision in the Phase 5 delivery list**

Add this bullet after the provider metadata bullet in
`docs/flashcard-planet-v2/CODEX_EXECUTION_PLAN.md`:

```markdown
- Routed Daily Report commentary through Groq first with OpenAI as the availability fallback. The shared global provider default and all other task routes remain unchanged.
```

- [ ] **Step 3: Check documentation for contradictory provider statements**

Run:

```powershell
rg -n "Daily Report AI primary|daily_report_commentary.*openai|OpenAI first|Groq first" .env.example docs/flashcard-planet-v2 docs/superpowers/specs/2026-07-23-daily-report-groq-routing-design.md
```

Expected: the current configuration and Phase 5 delivery record identify Groq
as primary. Historical design and implementation plan documents may still
describe the route that was chosen at their original date; do not rewrite those
historical records.

- [ ] **Step 4: Commit the configuration documentation**

```powershell
git add .env.example docs/flashcard-planet-v2/CODEX_EXECUTION_PLAN.md
git commit -m "docs: document Groq-first report commentary"
```

### Task 3: Verify, Record Results, and Update PR #84

**Files:**
- Modify: `docs/flashcard-planet-v2/CODEX_EXECUTION_PLAN.md:110-120`
- Update: GitHub PR #84 description

- [ ] **Step 1: Run the focused Daily Report backend suite**

Run:

```powershell
python -m pytest tests/test_daily_report_intelligence_migration.py tests/test_daily_report_evidence.py tests/test_daily_report_commentary.py tests/test_daily_report_intelligence_repository.py tests/test_daily_report_intelligence_repository_postgres.py tests/test_daily_report_intelligence_service.py tests/test_daily_market_report_service.py tests/test_daily_market_report_api.py tests/test_daily_market_report_scheduler.py tests/test_scheduler_startup.py tests/test_llm_provider.py -q
```

Expected: `263 passed, 1 skipped`. The skipped test requires
`TEST_POSTGRES_DATABASE_URL` and has already passed separately against a
migrated PostgreSQL 16 plus pgvector database.

- [ ] **Step 2: Run the complete backend suite**

Run:

```powershell
python -m pytest -q
```

Expected: `1557 passed, 1 skipped, 3 failed`. The only failures must be:

```text
tests/test_ebay_ingestion_deadline.py::DeadlineTriggerTests::test_meta_json_carries_deadline_flag
tests/test_ebay_scheduler.py::test_run_ebay_ingestion_skipped_when_disabled
tests/test_ebay_scheduler.py::test_run_ebay_ingestion_skipped_missing_credentials
```

These three failures were reproduced on merged baseline `adc262b`. Stop if any
provider, Daily Report, or additional test fails.

- [ ] **Step 3: Update exact verification counts**

Replace the Phase 5 backend verification counts with:

```markdown
- 263 focused backend tests passed and one environment-gated PostgreSQL test skipped, covering persistence, evidence contracts, validation, repository state transitions, cross-session orchestration, API boundaries, scheduling, startup, Groq-first routing, fallback behavior, and provider metadata. The skipped test passed separately against a migrated disposable PostgreSQL 16 plus pgvector database.
- The complete backend suite produced 1557 passes, one environment-gated skip, and three existing eBay scheduler failures. All three failures were reproduced unchanged on the pre-Phase-5 merged baseline commit `adc262b`; no Daily Report AI or provider-routing test failed.
```

If the observed totals differ while the test set is otherwise correct, record
the observed totals instead of copying these expected numbers.

- [ ] **Step 4: Confirm no secret or generated content entered the diff**

Run:

```powershell
git diff --check
```

Expected: exit code `0`.

Run:

```powershell
git status --short
```

Expected: only the verification record is modified.

- [ ] **Step 5: Commit the verification record**

```powershell
git add docs/flashcard-planet-v2/CODEX_EXECUTION_PLAN.md
git commit -m "docs: record Groq routing verification"
```

- [ ] **Step 6: Push the branch**

```powershell
git push
```

Expected: `feat/daily-report-ai-commentary` advances on `origin` without a
force push.

- [ ] **Step 7: Update Draft PR #84**

Update the PR summary and safety sections to say:

```markdown
- Route Daily Report commentary through Groq first, with OpenAI used only when Groq is unavailable.
- Continue recording the actual provider and model internally while omitting both from public responses.
- No production or staging Groq call was made during verification.
```

Update the focused and full-backend verification counts to the exact results
from Steps 1 and 2. Preserve the existing baseline eBay failure disclosure.

- [ ] **Step 8: Confirm the PR remains clean and mergeable**

Run:

```powershell
gh pr view 84 --repo ivancjz/Flashcard-planet --json url,isDraft,mergeable,mergeStateStatus,headRefName,baseRefName
```

Expected: Draft PR #84 targets `main`, uses
`feat/daily-report-ai-commentary`, and reports `MERGEABLE` with
`mergeStateStatus` equal to `CLEAN`.

