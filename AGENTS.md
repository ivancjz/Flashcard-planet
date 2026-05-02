# AGENTS.md

> **What this file is for**
>
> This file is read automatically by Codex Cloud when reviewing pull requests in this repository. It defines the review guidelines, common bug patterns, and project-specific invariants that the reviewer should check.
>
> Human contributors and Claude Code should treat this file as the authoritative summary of "what good code looks like in Flashcard Planet" for review purposes. For full context, see `CLAUDE.md`.

---

## Project context

**Flashcard Planet** is a multi-game TCG (Trading Card Game) market intelligence platform — investment signals, price tracking, and cross-game IP analytics for Pokemon, Yu-Gi-Oh, and (planned) Magic / One Piece / Lorcana.

**Stack:** Python 3.13 + FastAPI + SQLAlchemy 2 + APScheduler + httpx + PostgreSQL 18, hosted on Railway.

**Operator:** Solo developer. Tests, alerts, and SQL evidence are the primary defenses against regressions — there is no QA team.

---

## Review guidelines

For each PR, surface **P0 and P1 issues only**. Skip nits, style preferences, and theoretical concerns.

For each finding, provide:

1. File and line number(s)
2. Why it's a problem (1–2 sentences)
3. Recommended fix
4. Whether it should block merge or is acceptable as a tradeoff (with re-evaluation conditions if accepted)

If the PR has no P0/P1 issues, write a single line: `No P0/P1 issues found.`

---

## Hard checks (must verify on every relevant PR)

These are non-negotiable invariants in this codebase. Any PR violating one of these must be flagged P0.

### 1. Scheduler discipline

- **Every scheduler job must write `scheduler_run_log`** on both success and failure paths. Silent failures are the project's single biggest historical bug class.
- Use `clock_timestamp()` in trigger functions, **never** `CURRENT_TIMESTAMP`. CURRENT_TIMESTAMP is fixed at transaction start, which causes false-reject silent data loss inside long ingest transactions.
- New scheduler jobs must use **interval triggers**, not cron triggers. Cron triggers are reset on every Railway deploy and may never fire (this is how eBay ingest historically failed to run for weeks).
- New jobs that produce no output during normal operation should still log a no-op record. "Working in no-op window" must be distinguishable from "crashed".

### 2. Data integrity

- **Every `price_history` insert must populate `market_segment`** (`'raw'`, `'graded'`, or `'unknown'`). NULL is forbidden. Check for any new ingestion paths that bypass this.
- **Signal compute must filter by `market_segment = 'raw'` by default** to prevent graded card prices from contaminating investment signals. This is a P0 for user-facing signal, prediction, alert, mover, recommendation, or ranking logic.
  **Allowed exceptions**: admin diagnostics, data-quality reports, migrations/backfills, explicitly graded-specific features, or explicitly cross-segment analysis. Exception code must be clearly named or documented so the reviewer can tell the broader segment scope is intentional.
- **Source label discipline**: `source` column values are full canonical names (`pokemon_tcg_api`, `ygoprodeck_api`, `ebay_sold`), not abbreviations. Any new source string should follow this convention.
- **Set identity** is stored in `metadata->>'set_id'` on the assets table. There is no `set_code` column — references to one are bugs.

### 3. PR safety patterns

- **Build the guard before the expansion**: if a PR introduces logic that auto-imports / auto-creates / auto-modifies many records at scheduled time, there must be an explicit guard preventing unbounded action. (Historical pattern: PR #11 added an import guard before PR #10's set expansion would have triggered 1,644 unauthorized auto-imports.)
- **Cross-PR assumption breakage**: if this PR depends on an invariant established in an earlier PR (e.g., "all rows have non-NULL market_segment because PR #24 set the default"), confirm the invariant still holds. Adding new data sources can quietly break invariants.
- **Local DB absolute counts are not trustworthy**. Trends and shapes are usable, but any claim like "this affects N rows" must be validated against production data — not local snapshots.

### 4. Test discipline (TDD is the standard)

- Bug fixes ship with at least one regression test that fails before the fix and passes after.
- New features ship with tests covering at least the happy path + one error path.
- Tests that mock a real failure mode (e.g., 429 rate limit, OAuth token expiry, DB connection drop) are preferred over unit tests of pure logic.

### 5. Six-layer verification chain

When a PR touches data flow (ingestion → signal → display), the change should be verified end-to-end across six layers:

1. **Write**: row appears in DB after the action
2. **Schema invariants**: required columns populated (segment, source, etc.)
3. **Filter**: downstream queries actually include the new rows (not silently filtered out)
4. **Compute**: derived values (signals, aggregates) reflect the new rows
5. **Display**: UI/API responses reflect the new rows
6. **Cross-source regression**: existing sources are not broken by the change

A claim of "this works" without evidence at all six layers is suspect. (Historical pattern: YGO data wrote successfully for 2 weeks but was silently filtered out at layer 3.)

---

## Common traps to flag

These are bug patterns that have appeared in this codebase before and are likely to recur. Be particularly suspicious when you see:

### "Designed but never ran"

A new scheduled job, ingest path, or background task is added, but there is no evidence it has actually executed. PRs that add scheduler jobs without a verification plan ("after merge, confirm this query in production shows new rows") fall into this trap. Three historical instances: signal sweep, eBay ingest, bulk-refresh import path.

**Flag**: any new scheduler job, ingest path, or LLM call without an obvious "how do we know this ran?" answer.

### "Merge ≠ deploy ≠ verified"

Code merged to main is not the same as deployed; deployed is not the same as verified. PRs that say "fixes #X" without an explicit production verification plan should be flagged. Historical instance: 429 rate limit fix was claimed live for ~10 hours but was actually unmerged.

**Flag**: PRs that close issues without specifying how production state will confirm the fix.

### Status state machine inconsistencies

`scheduler_run_log.status` should be one of a defined enum (e.g., `'running'`, `'success'`, `'failure'`, `'no_op'`). PRs that introduce new status values without updating consumers, or that mix string literals with enum values, are bugs. Historical instance: PR #13 originally had this issue.

**Flag**: any new code path that writes a status value not in the existing enum, or any consumer that doesn't handle a new status case.

### Missing `error_message` on failure paths

When a job fails, the failure record in `scheduler_run_log` must include enough information to diagnose without re-running. A bare `status='failure'` row is a debugging dead-end.

**Flag**: failure paths that don't capture the exception details into a structured error column.

### Threshold tuning attempts on data-freshness problems

If a PR proposes adjusting signal thresholds (e.g., adding hysteresis bands, lowering the BREAKOUT threshold), the underlying issue is often data freshness, not threshold calibration. 97.7% of historical INSUFFICIENT_DATA cases were "has_baseline_no_current" (stale prices), not "thresholds wrong".

**Flag**: threshold-tuning PRs that don't first present evidence that data freshness has been ruled out.

### Auto-imports without import guards

Any PR that causes bulk-refresh or any scheduled job to start auto-creating database rows from external data must have an explicit allowlist or guard. The historical fear: a set list expansion (PR #10) would have triggered automatic import of 1,644 cards on the next bulk-refresh run, with no review.

**Flag**: any scheduled job logic that creates records based on external API responses without a guard.

### Real data accidentally falls back to sample_seed

Price reads should prefer real provider data. `sample_seed` is only a development/demo fallback when no real rows exist for the asset/source. PRs that allow sample data to mix into production signals, alerts, or displayed live prices can create false confidence — the UI looks "alive" but the numbers are not real market data.

**Flag**: any signal, alert, price display, or history query that can include `sample_seed` rows when real provider rows exist, unless the PR is explicitly demo/dev-only.

### External ID drift creates duplicate assets

Asset identity must stay canonical across importers. New ingestion paths should not invent variant-suffixed or provider-specific `external_id` values for the same real card. The canonical form for Pokemon is the Pokemon TCG API id (e.g., `base1-4`); for YGO it's the konami_id-derived form. Inconsistent IDs create duplicate assets, fragment price history, and break signal computation.

**Flag**: import code that creates assets using inconsistent external IDs, or that does not check for existing canonical assets before insert/upsert.

### Human review bypasses transaction or double-resolution guards

Review queue mutations must be atomic and must guard against resolving the same listing twice. Accept/override paths should only write price events when the raw listing has enough data to support a valid observation (price + sold_at present).

**Flag**: review mutations that do not check `resolved_at`, do not run in one transaction, or can write a price event without raw listing price/sold timestamp.

### Free-tier pages leak Pro/live data

Free users should receive only the permitted snapshot data. The right pattern is server-side gating: do not send live values to the browser at all. Hiding live data with CSS/JS still leaks it via DevTools, view-source, or client-side state inspection.

**Flag**: templates, routes, or API responses that include Pro/live signal data for free users, even if hidden in the UI.

### Import-time side effects start background work

Importing app modules should not unexpectedly start schedulers, run ingestion, or mutate the database in tests/dev scripts. Startup behavior must be gated through explicit app lifecycle/config switches (FastAPI startup events, explicit `if __name__ == "__main__"` guards, environment-variable opt-ins).

**Flag**: module-level code that starts APScheduler jobs, calls ingestion, or writes to the database during import.

---

## Architectural conventions

These are not bugs to flag, but patterns to respect:

- **Game-agnostic abstraction**: new game integrations implement `GameDataClient` (Protocol). They do not branch on `game` in shared logic. PRs that add `if game == 'pokemon': ...` in shared paths are usually wrong.
- **Permissions are tier-gated, not feature-flagged**: Free vs Pro distinctions go through `permissions.py` Feature enum + `ProGate` macro. Hardcoded `if user.is_pro:` in templates or routes is wrong.
- **LLM provider routing**: tasks are routed by type, not by random fallback. `signal_explanation` → Anthropic, `mapping_disambiguation` → Groq, `structured_tagging` → OpenAI. PRs that hardcode a single provider for a new task are usually overlooking the routing layer.
- **Codex review is mandatory** but not blocking. Every merged PR must have a `## Codex Review` section in its description. (You are that reviewer. If your review surfaces no issues, the section will say "No P0/P1 issues found." — that's a valid section, not an absence of section.)

---

## What NOT to flag

To keep reviews high-signal:

- Style nits (spacing, naming) unless they obscure meaning
- Comments missing on obvious code
- Possible-but-unlikely edge cases (e.g., "what if Discord API returns 999?")
- Subjective architectural preferences ("this could be a class")
- Anything already discussed and resolved in `CLAUDE.md` §11 ("Known accepted tradeoffs")
- Missing tests for purely mechanical refactors that do not change behavior
- Lack of production verification for local-only tooling, scripts, or documentation-only changes
- Performance concerns without evidence that the changed path is hot, scheduled, or user-facing

**The bar for flagging anything as P0 or P1**:

> If a concern does not plausibly cause data loss, silent failure, incorrect user-facing signals, security/permission leakage, or unbounded external/API/database action, do not flag it as P0/P1.

If a finding is borderline P1 vs nice-to-have, **default to not flagging**. The operator is solo and review noise has a real cost.

---

## Output format

Use this structure:

```markdown
## Codex Review

### P0 issues (block merge)
1. **`file:line`** — Summary.
   - **Why**: ...
   - **Fix**: ...
   - **Block**: yes.

### P1 issues (should fix before merge)
1. **`file:line`** — Summary.
   - **Why**: ...
   - **Fix**: ...
   - **Block**: no, but should be fixed before merge.

### Acceptable tradeoffs / notes
- ...
```

**Omit empty sections.** Do not include "P0 issues" or "P1 issues" headings if there are no findings in that category. If only tradeoffs / notes exist, only that section appears.

If no findings at all:

```markdown
## Codex Review

No P0/P1 issues found.
```

---

*This file is updated when the review guidelines change. To propose updates, open a PR titled `chore(agents): <change>`.*
