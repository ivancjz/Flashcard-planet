# Codex CLI CI Feasibility Report

**Date:** 2026-05-02
**Task:** TASK-103a
**Codex version tested:** 0.128.0
**Conclusion:** Codex CLI can run headlessly in CI — but requires an OpenAI API key to do so. The current ChatGPT OAuth session cannot be used in CI. See §4 for the recommendation.

---

## 1. Auth mechanism

`~/.codex/auth.json` structure:

```json
{
  "auth_mode": "chatgpt",
  "OPENAI_API_KEY": null,
  "tokens": {
    "id_token": "...",
    "access_token": "...",
    "refresh_token": "rt_g...",
    "account_id": "..."
  },
  "last_refresh": "..."
}
```

Current auth uses **ChatGPT OAuth** (device-auth flow), not an API key. The `OPENAI_API_KEY` field is null.

Codex also supports API key auth via `codex login --with-api-key` which reads a key from stdin:

```bash
echo "$OPENAI_API_KEY" | codex login --with-api-key
```

This would write an `auth.json` with `auth_mode: api_key` and `OPENAI_API_KEY` populated.

---

## 2. Can the auth be stored in GitHub Actions Secrets?

| Auth form | Storable in GH Secret? | Notes |
|---|---|---|
| OpenAI API key (`sk-...`) | **Yes** | Designed for programmatic use. Store as `OPENAI_API_KEY` secret, inject as env var. |
| ChatGPT OAuth access_token | No | Short-lived JWT (~1 hour). Expires before CI ever uses it. |
| ChatGPT OAuth refresh_token (`rt_g...`) | Technically yes, but unsafe | Would need a custom refresh step before each run. OpenAI does not publish a stable endpoint for this; it could break silently. Not designed for CI. |

**Answer:** API key auth is the only viable path for CI.

---

## 3. Does Codex exec run headless?

**Yes.** Confirmed with two tests:

**Test 1 — stdin pipe, no TTY:**
```bash
echo "Say only: HEADLESS_OK" | codex exec --ephemeral
# Output: HEADLESS_OK
```

**Test 2 — `codex exec review` against a branch:**
```bash
codex exec review --base main --ephemeral -o /tmp/review.txt
cat /tmp/review.txt
# Output: review text (or "diff is empty" when no changes)
```

`codex exec review --base <branch> --ephemeral -o <file>` is exactly what a GitHub Action needs:
- `--base main` → reviews changes since branching from main
- `--ephemeral` → no disk state written (safe for parallel CI runners)
- `-o <file>` → captures output without needing to parse stdout

The `--json` flag also exists for structured output if needed.

**One caveat:** The model `gpt-4o-mini` is blocked for ChatGPT accounts. With an API key, all OpenAI models are accessible. For cost control, the Action should pin a specific model (e.g., `o4-mini`) via `-m`.

---

## 4. Recommendation for TASK-103b

**Path A — OpenAI API key + `codex exec review` (recommended):**

If Ivan can provide an OpenAI API key:

1. Store key as GitHub Actions secret `OPENAI_API_KEY`
2. In the workflow, before running Codex:
   ```bash
   echo "$OPENAI_API_KEY" | codex login --with-api-key
   ```
3. Run the review:
   ```bash
   codex exec review --base main --ephemeral -m o4-mini -o /tmp/review.txt
   ```
4. Post `/tmp/review.txt` as a PR comment via `gh pr comment`

This is clean, stable, and designed for CI. The `codex exec review` command is purpose-built for this use case.

**Estimated cost:** o4-mini reviews a typical PR diff in under 10k tokens. At ~$0.002/1k input tokens, a review costs well under $0.05. 100 PRs/month = <$5/month.

---

**Path B — Claude Code self-review (fallback if no OpenAI API key):**

Use `claude -p "Review this diff for correctness and security: $(git diff main)"` via the Anthropic API (Claude Code already has `ANTHROPIC_API_KEY`).

Tradeoff: loses true independence (same model that wrote the code reviews it), but preserves the review gate. A well-structured prompt asking Claude to "play adversarial reviewer" recovers most of the value.

---

**Path C — Do not do:**

- Storing and rotating ChatGPT OAuth refresh tokens in CI: fragile, not supported by OpenAI, breaks silently.
- Using the current ChatGPT session: access tokens expire in ~1 hour.

---

## 5. What TASK-103b needs from the operator

One decision before implementation can start:

> **"Do you have an OpenAI API key, or are you willing to create one ($5 credit to start)?"**
>
> - If **yes** → Path A. Provide the key as a GitHub Actions secret named `OPENAI_API_KEY`.
> - If **no** → Path B. Claude self-review with an adversarial prompt.

Either path can be implemented in under half a day once the decision is made.

---

## Appendix: commands tested

```bash
# Version
codex --version
# → codex-cli 0.128.0

# Auth status
codex login status
# → Logged in using ChatGPT

# Headless exec
echo "Say only: HEADLESS_OK" | codex exec --ephemeral
# → HEADLESS_OK  ✓

# Headless review
codex exec review --base main --ephemeral -o /tmp/test_review.txt
# → review text written to file  ✓
```
