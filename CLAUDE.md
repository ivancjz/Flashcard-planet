# CLAUDE.md — Flashcard Planet Project Context

This file is the project context for any Claude instance working on this codebase (primarily Claude Code operating in `C:\Flashcard-planet`). Read this first. Then read `.claude/session-handoff-<latest date>.md` for the most recent operational state.

---

## 1. What this project is

**Flashcard Planet** is a TCG (Trading Card Game) investment signals SaaS, targeting retail TCG investors who want price movement alerts and AI-powered analysis. Pokémon TCG is the first game live; Yu-Gi-Oh is scaffolded; MTG / One Piece are roadmap.

- **Operator**: Ivan (solo dev, Melbourne, AEST). GitHub: `ivancjz`.
- **Stack**: Python 3.13 + FastAPI + SQLAlchemy 2 + Alembic + APScheduler + httpx + Postgres 18. Web-first product; Discord is an outbound alert delivery channel via REST API webhook only.
- **Hosting**: Railway. Hobby plan. ~AUD 300/month. Daily automated backups via GitHub Actions → `ivancjz/flashcard-planet-backups` (GitHub Releases). See §7 for details.
- **Deploy**: GitHub main → Railway auto-deploy.
- **Branch strategy**: `feat/*` or `fix/*` → PR → self-review → merge main → auto-deploy.

### Business state
- Zero paying users as of 2026-04-22.
- Core value proposition: price signals (breakout / move / watch / idle) + future AI analysis.
- Monetization plan: subscription + ads. Neither live yet.

---

## 2. Architecture quick reference

### Key modules
- `backend/app/main.py` — FastAPI app entry. Routers mounted here.
- `backend/app/api/` — REST API routers.
- `backend/app/backstage/` — Scheduler + admin routes. `routes.py` has `APIRouter(prefix="/admin")` with `require_admin_key` dependency.
- `backend/app/backstage/scheduler.py` — APScheduler job definitions. `_STARTUP_DELAY` dict controls first-run offsets.
- `backend/app/ingestion/` — `pokemon_tcg.py` (Pokemon TCG API), `ebay_sold.py` (eBay — see critical note below), `ygo.py` (Yu-Gi-Oh scaffold).
- `backend/app/services/signal_service.py` — Signal computation. Dual-window algorithm (baseline ≥7d + current ≤24h). See `SWEEP_BATCH_SIZE` at file top.
- `backend/app/models/` — SQLAlchemy models.
- `backend/app/alerting/discord.py` — Discord alert delivery via REST API webhook. This is the only Discord integration point. No bot process; no Gateway connection.
- `scripts/import_pokemon_cards.py` — CLI for manual Pokemon set imports.

### Models you'll touch most
- `Asset` — card identity. Columns: `asset_class, game, name, set_name, card_number, year, language, variant, grade_company, grade_score`. UniqueConstraint on all 10.
- `PriceHistory` — price observations. Columns: `id, asset_id (FK), source, currency, price (Numeric 12,2), captured_at`. Indices on `captured_at` and `asset_id`. **No index on `source`.**
  - `source` values: `'pokemon_tcg_api'` or `'ebay_sold'` (lowercase, underscore). **Don't write `'ebay'` or `'pokemon'`.**
  - **`price_history` must contain only market/sold price observations — not ask/listing prices.** eBay Browse API data (ask prices) must NOT be written here. See eBay critical note below.
- `SchedulerRunLog` — job audit log. Columns: `id, job_name, started_at, finished_at, status, records_written, errors, error_message, meta_json`. Status values: `'running'` (default), `'success'`, `'partial'`, `'warning'`, `'error'`, `'failed'`.
- `AssetSignal` / `AssetSignalHistory` — signal outputs. Label values: `BREAKOUT, MOVE, WATCH, IDLE, INSUFFICIENT_DATA`.

### eBay API status — critical, read before touching ebay_sold.py

**eBay Finding API is decommissioned (2025-02-05, date unverified — see note).** Endpoint: `https://svcs.ebay.com/services/search/FindingService/v1`. Returns HTTP 500 + `errorId=10001, domain=Security` on every call, including the first call of a fresh run. This is not quota exhaustion — it is a permanently rejected legacy endpoint. The Finding API used a legacy auth method (`SECURITY-APPNAME` query param, not Bearer token) on the legacy `svcs.ebay.com` domain. It is gone.

**Verification evidence (forensic audit 2026-05-14):** Full HTTP response body confirmed via direct probe:
```
HTTP 500 — 485 bytes
<errorId>10001</errorId><domain>Security</domain><subdomain>RateLimiter</subdomain>
<message>Service call has exceeded the number of times the operation is allowed to be called</message>
<parameter name="Param1">findCompletedItems</parameter>
<parameter name="Param2">FindingService</parameter>
```
The official meaning of errorId 10001 is "rate limit exceeded." However: this error fires on the **first call of a fresh session**, with zero prior calls in the window. Genuine quota exhaustion resets daily and succeeds on the first post-reset call. First-call failure is behaviorally inconsistent with real rate limiting — it is consistent with the endpoint permanently rejecting all traffic. **The date 2025-02-05 is from internal notes (commit `9a6e9e6` context); no official eBay developer announcement was located.** The behavioral conclusion (endpoint permanently blocked) is verified. The specific decommission date is not.

**The April 27 13:33 UTC "cliff" explained:** `last_ebay_sold_captured_at = 2026-04-27 13:33:14` is NOT the moment eBay ingest stopped writing. It is the timestamp of the last **valid** (non-future-dated) row. Commit `4d63362` (2026-04-27 13:43 UTC, 10 minutes after that timestamp) deleted 749 future-dated rows (captured_at up to 2026-05-06) and added a filter to reject them going forward. Before this fix, eBay auctions with future end times were being written to `price_history`. The "cliff" is the deletion of those rows, not a stop in eBay activity. The Finding API was already returning 10001 by this date (commit `9a6e9e6`, 2026-04-29, explicitly documents "YGO spike failed with all 14 assets returning ebay_api_error (errorId 10001)").

**Scheduler run gap April 27–May 8:** No `scheduler_run_log` entries exist for `ebay-ingestion` during this 11-day window despite multiple deploys. Root cause not fully confirmed from available data (no direct DB row-level access). Most likely cause: `46af80b` (2026-04-30) introduced a broken budget counter that caused the job to crash before `start_run()`, fixed by `f4bcd8d` (2026-05-01). April 28–29 gap cause undetermined. Runs resumed May 9 after a scheduler restart from the `signal-history-prune` job deploy (`72c0e1c`). All runs since May 9 write 0 records because the Finding API returns 10001 immediately.

**eBay Browse API (`api.ebay.com/buy/browse/v1`) returns active listings, not sold prices.** Browse API data is ask/listing price. It must NOT be written to `price_history`. If Browse API data is ever ingested, it goes to a separate `listing_snapshot` table (not yet built) with explicit labelling as ask price.

**`_parse_insights_items` in `ebay_sold.py` is dead code** — never called from the ingestion flow. Do not wire it up without architecture approval.

**eBay sold-price channel permanently deprecated.** Browse API ask-price feasibility tested 2026-05-14 (Q1, n=30 cards, 5,914 listings): 90% of high/mid-tier sample is grade-mixed, median IQR 189%/129%. Ask price is not a viable sold-price substitute on cards that matter for signal output. Going forward: Pokemon TCG API is the sole sold-price source for Pokémon. Yu-Gi-Oh sold-price source remains unresolved — see §13 Active experiments.

**Historical `ebay_sold` data contamination (verified 2026-05-14):** 1,380 rows, 2026-04-21 to 2026-04-27, are grade-mix contaminated and contain junk prices (verified $11k+ junk outliers, sealed product mixed in, international condition strings unfiltered). Do NOT use as signal threshold calibration baseline. Retain rows for audit trail; exclude from analytical use. Affected analyses: any signal engine threshold derived pre-2026-05-13 may be biased.

**Code-level exclusion enforced 2026-05-14** in `signal_service._compute_delta_batch` (baseline + current window WHERE clauses) and `liquidity_service.get_liquidity_snapshots` (sales metrics zeroed, `history_depth` excludes ebay_sold rows). Latent contamination of 426 Pokémon assets (baseline computation when `pokemon_tcg_api` data is sparse) is now blocked at code level, not relying on date arithmetic. `signal_delta_source_weights` default updated to remove `ebay_sold=2.0` to prevent latent-trap re-introduction. Related: Issue B (still pending 7-day SQL evidence) may have masked latent contamination risk.

### YGO data source semantics — critical, read before any YGO expansion work

**Verified 2026-05-07:** YGOPRODeck returned byte-identical prices on all 67 seeded YGO assets (POTE + TOCH, both 2020–22 sets) across 14 days of daily polling. `baseline_price == current_price` on every card, including Destiny HERO at $326.73. Signal engine correctly classifies all 67 as IDLE (`delta=0`). This is not an engine bug.

**What is NOT confirmed:** Whether YGOPRODeck updates prices for newer/higher-velocity sets (post-2023) at a useful frequency. The zero-update pattern may be set-specific (POTE/TOCH genuinely flat) or source-specific (YGOPRODeck's refresh cadence for older sets is too low). Unknown without testing newer sets.

**Implication for TASK-101:** Criterion 2 (BREAKOUT/MOVE/WATCH for at least one YGO asset) is unreachable on currently-seeded sets. Unblocked only if discovery test below passes.

**TASK-201 (YGO set expansion) is NOT a known unlock.** Do not add sets before the discovery test. Expanding to 300+ assets that also return static prices wastes ingest budget and DB space. **Required first:** poll 10 high-velocity 2024–2025 YGO sets (e.g., LEDE, PHNI, AGOV, DUNE, INFO) for 7 days, query `/admin/diag/price-variance?source=ygoprodeck_api`. Decision rule: if ≥30% of sampled assets show ≥2 distinct prices in 7 days → TASK-201 viable. Otherwise → YGO is blocked on an alternative price source (PriceCharting, Marketplace Insights, or other).

### CardMarket data source — YGO price signal input

**What it is:** CardMarket is the dominant EU trading card marketplace. They publish a public price guide daily at `https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_3.json` (~16 MB). The file contains `avg1` (1-day), `avg7` (7-day), `avg30` (30-day), and `trend` price averages per product in EUR, with no authentication wall. CardMarket's public announcement language states prices may be "used however you see fit."

**Use posture (decided 2026-05-14):** backend signal input only. CardMarket prices are not displayed directly to users in alerts, dashboards, or any user-facing surface. Discord alerts say "YGO signal detected" without quoting CardMarket figures. Due diligence basis: public announcement language ("use however you see fit"), public S3 file with no auth wall, no commercial redistribution of raw prices. ToS clarification email path was considered and declined — accepted residual grey-area risk with mitigations above.

**Source values in `price_history`:** `cardmarket_avg1`, `cardmarket_avg7`, `cardmarket_avg30`, `cardmarket_trend`. Do NOT blend these — each tracked independently. Signal engine uses `avg7` as primary, `avg30` as baseline.

**Known limitations:** EUR-denominated only (signal delta uses relative % so currency unit is irrelevant for classification, but display features must never show raw CardMarket prices to avoid currency confusion). EU/US price gap is non-trivial for vintage cards — seed list should avoid cards where EU/US gap exceeds 30%.

### Scheduler jobs
All 5 use `interval` trigger + startup resume via `prepare_scheduler_for_startup`. **No cron triggers** (removed 2026-04-22 after discovering cron × frequent deploys = perpetual miss).

| job_name | Interval | `_STARTUP_DELAY` |
|---|---|---|
| `scheduled-ingestion` | 1h | 120s |
| `bulk-set-price-refresh` | 1h | 300s |
| `signal-sweep` | 15m | 600s |
| `ebay-ingestion` | 24h | 660s |
| `alert-heartbeat` | 10m | 720s |

**All 6 scheduler jobs now write to `scheduler_run_log`.** Every job uses unconditional `start_run` before the try block and `finish_run`/`prune_old_runs` in a `finally` clause, guaranteeing a DB row on every exit path including disabled kill-switches and exceptions.

### Auth
`require_admin_key` in `backend/app/backstage/routes.py` is the canonical admin dependency. Dual path: `X-Admin-Key` header OR session user in `ADMIN_EMAILS` allowlist. **Do not introduce HTTPBasic or other auth schemes** — reuse `require_admin_key`.

---

## 2.5. CLI tools available to you

The operator's local environment has these CLIs installed and authenticated. **Use them directly** — do not ask the operator to copy/paste dashboard screenshots, do not write Python wrappers for what a one-liner can do, do not assume you don't have access until you've tried.

### Railway CLI (`railway`)

Authenticated against the operator's Railway account. Linked to the Flashcard Planet project.

**Use it for:**

- **Inspect production env vars**: `railway variables` — confirms whether a feature flag (e.g., `EBAY_SCHEDULED_INGEST_ENABLED`, `DEV_PRO_EMAILS`) is actually set in production. Faster and more reliable than asking the operator to check the dashboard.
- **Run one-off SQL against production**: `railway run psql $DATABASE_URL -c "SELECT count(*) FROM assets WHERE game='ygo';"` — for verification queries that don't fit in the diagnostic endpoint pattern.
- **Tail production logs**: `railway logs --service backend` — when a deploy might have failed silently or you need to see a stack trace.
- **Trigger manual deploys** (rarely): `railway up` — only when CI is broken and the operator explicitly asks.
- **Run scripts in production environment**: `railway run python -m scripts.<name>` — connects to production DB with proper env vars without leaking credentials.

**Do NOT use it for:**

- Modifying production env vars (`railway variables set ...`) without explicit operator instruction. Env vars are configuration decisions, not code.
- Restarting services unprompted. If a deploy is misbehaving, report and wait.
- Touching any other Railway project. The operator may have other projects in their account; you operate only on Flashcard Planet.

**Verifying it's available:** `railway whoami` should return the operator's email.

### GitHub CLI (`gh`)

Authenticated as `ivancjz`. Has read/write access to `ivancjz/Flashcard-planet` and `ivancjz/flashcard-planet-backups` (private backup repo).

**Use it for:**

- **Open PRs**: `gh pr create --title "..." --body "..."` — instead of writing instructions for the operator to do it manually. The PR template / body should still follow CLAUDE.md §3 commit message conventions.
- **Read PR / issue state**: `gh pr list`, `gh pr view <num>`, `gh issue list` — when you need to know what's open without asking.
- **Check workflow runs**: `gh run list --workflow daily-backup.yml` — verify Codex Cloud reviews posted, daily backup ran, etc.
- **Download artifacts / releases**: `gh release download --repo ivancjz/flashcard-planet-backups <tag>` — for restore drills, debugging, or manual backup retrieval.
- **Comment on PRs**: `gh pr comment <num> --body "..."` — when leaving notes for the operator or for Codex Cloud follow-up.
- **Trigger workflow_dispatch**: `gh workflow run daily-backup.yml` — to manually run the daily backup, useful for first-time setup verification or after a failure.

**Do NOT use it for:**

- Force-pushing to main (`gh ...` won't do this directly, but git can — see CLAUDE.md §3 git workflow rules).
- Closing issues / PRs without operator approval if they aren't your own.
- Modifying repository settings (`gh repo edit ...`) — settings are operator decisions.
- Touching any repo other than `ivancjz/Flashcard-planet` and `ivancjz/flashcard-planet-backups`.

**Verifying it's available:** `gh auth status` should show authenticated as `ivancjz`.

### Codex CLI (`codex exec`)

Already documented in §4. Used for fallback PR review when Codex Cloud is unavailable. Pre-authenticated.

---

### General CLI usage rules

These three CLIs (`railway`, `gh`, `codex`) plus standard tools (`git`, `psql`, `docker`, `bash`, `python`) are your direct execution surface. Default to using them rather than:

- Asking the operator for screenshots
- Writing Python scripts to do what a CLI one-liner does
- Assuming you can't access something until you've tried

**When in doubt, run the read-only command first** (`railway variables`, `gh pr list`, `psql ... -c "SELECT ..."`) and report what you found. Read-only operations are essentially free.

**When you'd modify state with a CLI** (set an env var, push a commit, restart a service), follow the same rules as for code changes:

- Verify-not-assume — confirm the current state before writing
- Report what you ran in the "Verified by" block
- For irreversible actions, get explicit operator confirmation

**Pattern to avoid:** writing `os.environ.get(...)` checks inside a Python REPL when `railway variables` would answer the question in 1 second from outside the application. The CLIs exist precisely so you don't have to write throwaway code for state inspection.

**Pattern to embrace:** every time you'd say "operator, can you check X in the Railway dashboard?" — first ask yourself if `railway` CLI can answer it. 90% of the time it can.

---

## 3. Critical conventions (do not violate without explicit operator approval)

### Git workflow
- Branches always `feat/<description>` or `fix/<description>`.
- **One commit = one concern.** Day 1 merged a "bulk-refresh guard + 429 fixes" tangle and it cost us 10 hours of confusion. Keep PRs focused.
- **Before `git commit`, always run `git status` and `git diff --staged`** to verify only files relevant to the current concern are staged. If unrelated changes are in the working tree (e.g., a different task in progress), `git stash` them first, commit the focused change, then `git stash pop`. The 2026-05-02 c1dc319 incident bundled DEV_PRO_EMAILS permission changes into a backup-script commit because both were in the working tree simultaneously — caught by self-review, not by CI.
- Operator trusts you to push to main directly. **Do not abuse this** — push only after PR self-review + codex review gate (see §4).
- Every commit message must include: what, why, and verification evidence. Format:
  ```
  <type>(<scope>): <subject>

  <what changed and why>

  Verified:
  - <specific evidence: test run / SQL output / log line>
  ```

### "Verified-not-assumed" rule
This is the most important behavior expectation. Every time you report task completion, you **must** include this block:

```
Task: <what was done>
Commit: <hash>
Deployed: <Railway deployment timestamp, or "pending" / "local only">
Verified by: <specific evidence — logs / curl / SQL count / pytest output>
Known gaps: <what you could NOT verify, and why>
```

**If you cannot produce concrete "Verified by" evidence, you did not finish the task.** Say so. The operator prefers "loud failures" over "silent successes." See §6 for history of why this rule exists.

### Dead config
Any setting / env var / class attribute that is declared but not read is **debt**. Either activate it or delete it. Do not leave it "just in case" — the operator's report (see §7) documents three historical instances of this pattern causing real confusion.

Current known dead configs: none. Keep it that way.

### Code patterns to follow
- **HTTP retries**: use the pattern from `fetch_card` — read `Retry-After` header first, fallback to `[2.0, 5.0, 15.0]` exponential. See `_parse_retry_after` and `_compute_retry_delay` in `backend/app/ingestion/pokemon_tcg.py`.
- **Ingestion error handling**: per-card `except ProviderUnavailableError: continue` (not `break`). Collect failed IDs, emit single `logger.error` summary at end of loop.
- **Rate limiting**: use `data_client.rate_limit_per_second` as authoritative. `time.sleep(1.0 / data_client.rate_limit_per_second)` in the outer loop's `finally`.
- **Scheduler jobs**: `interval` trigger + `next_run_time=None` + entry in `_STARTUP_DELAY`. **Never `cron`**.
- **"Stale data" diagnosis**: before assuming a scheduler job stopped writing data, first query `price_history` directly by `source` and time range. `scheduler_run_log` showing null/old means the job isn't *logging*, not necessarily that it isn't *running*. The two are independent until all jobs are fully instrumented. Pattern: `SELECT DATE(captured_at AT TIME ZONE 'UTC'), COUNT(*) FROM price_history WHERE source='X' AND captured_at >= NOW() - INTERVAL '7 days' GROUP BY 1 ORDER BY 1 DESC`.
- **NULL census before filter rollouts**: any new `WHERE` clause that excludes data based on a column value (e.g., `WHERE market_segment = 'raw'`) requires a pre-rollout NULL census across the entire affected table, grouped by source: `SELECT source, COUNT(*) FROM <table> WHERE <column> IS NULL GROUP BY source`. The rollout is safe only when this returns zero rows or only sources that the filter intentionally excludes. Verifying "the target rows look right" is not enough — silent-exclusion filters are about what gets dropped, and the dropped set must be enumerated explicitly. PR #26 exposed this: PR B's `market_segment = 'raw'` filter silently dropped all YGO rows because they had `market_segment = NULL`, and PR B's pre-merge SQL had only verified `pokemon_tcg_api` was correct.
- **Local DB absolute counts are not authoritative**: when a local audit surfaces an unexpected number (e.g., "22,654 NULL rows"), do not act on the number — first run the same query on production. Local DBs can be arbitrarily stale relative to production migrations and backfills. Trends, shapes, and source lists from local DB are usable; absolute counts are not. The default response to an alarming local count is "production audit before deciding scope," not "expand the PR scope to fix the local number."
- **Trigger functions: `clock_timestamp()` not `CURRENT_TIMESTAMP`**: in PL/pgSQL trigger functions that compare against "now", always use `clock_timestamp()` (wall-clock, advances during the transaction). `CURRENT_TIMESTAMP` / `NOW()` are pinned to transaction start — a 10-minute ingest transaction using `CURRENT_TIMESTAMP` would false-reject valid rows captured mid-transaction, producing silent data loss that looks identical to "eBay API missed some listings."
- **Cross-PR assumption tracking**: when a PR's correctness depends on an assumption established by a previous PR (e.g., "PR A guaranteed `market_segment` is set on all rows"), the new PR's verification step must re-run the SQL that established that assumption — not assume it still holds. PRs are merged at different times against different data; assumptions drift. List the inherited assumptions in the PR description's "Assumptions" section, with the SQL used to verify each.
- **Cross-path consistency for external service fixes**: any PR touching rate limiting, retry, backoff, or error handling for an external API must audit ALL ingestion paths that call the same service — not just the function being fixed. PR #12 fixed 429 handling in `pokemon_tcg.py` but missed `_run_bulk_set_price_refresh` in `scheduler.py` (same API, same failure mode, different path). Every such PR must include a "Paths audited" section in its description listing every code path that calls the affected service. For Pokemon TCG API: `scheduled-ingestion` and `bulk-set-price-refresh` paths in `scheduler.py` plus direct calls in `pokemon_tcg.py`. Scope = the external service, not the function.
- **Enum extension verification**: when a PR adds a new value to any enum (e.g. `Tier.PLUS`, a new `subscription_status`), grep the entire codebase for all sites that handle that enum before merging: TypeScript type definitions and union types, ternary / switch coercion sites (frontend + backend), database CHECK constraints, API serialisation/deserialisation, UI badge/conditional-rendering components, and tests that hard-reference the enum. List the updated sites in the PR description under "Enum sites updated". A new value silently falling through to a default is P0 if a paying user sees the free-tier UI; P1 if a feature flag is silently disabled. **Flag any PR that adds an enum value but omits this grep step.**

---

## 4. Codex review gate (mandatory)

Codex Cloud (included in ChatGPT Plus subscription) provides independent automated code review on every PR. Review guidelines for Codex are in `AGENTS.md`.

### When to trigger codex review

**Every PR before merge to main.** Not optional. Even small changes.

The only exception: changes that touch **zero production code paths** — e.g., README edits, `.gitignore` tweaks, adding a test for existing (unchanged) behavior. If in doubt, review anyway.

### How to trigger

**Automated (primary path):** Codex Cloud posts a `## Codex Review` comment on every PR automatically (configured by operator via chatgpt.com → Codex settings). No action needed — wait ~5–10 minutes after opening a PR.

**Manual fallback** (when no Codex Cloud comment appears after 10 minutes, or for local pre-PR review):

Option A — trigger via PR comment:
```
@codex review
```

Option B — run locally and paste into PR description:
```bash
codex exec review --base main --ephemeral -o /tmp/review.txt && cat /tmp/review.txt
```

Capture the output under a `## Codex Review` heading in the PR description.

Claude Code must run the fallback itself — **do not delegate to the operator**.

### Diagnostic endpoints as PR deliverables

For any PR whose verification requires multiple SQL queries or that introduces a new invariant the operator will need to re-check periodically, add a temporary admin endpoint under `/admin/diag/<pr-name>-verify` that packages the verification queries into a single JSON response. Mark it with a sentinel comment specifying a removal condition (a concrete event like "after X is confirmed" or a date — whichever is more precise) and add an entry to the backlog file. Rationale: SQL checklists run by the operator manually have a non-zero error rate (mistyped queries, skipped checks, results in inconsistent shapes); a single endpoint with structured output is more reliable for both the immediate verification and any repeat checks within the next few weeks. Removal is part of the next operational cleanup PR, not optional.

Pattern from PR #26 / #28: `ygo-verify-26` returned `{A_pass, B_pass, C_*, D_*, E_*}`, each a specific check. The operator could re-run the endpoint at different times (immediately post-deploy, after first yugioh-ingestion, after first signal-sweep) without re-typing SQL.

**Naming caveat**: avoid `*_pass` field names for checks that legitimately return false during normal operation (e.g., "YGO has graduated from INSUFFICIENT_DATA" returns false on day 1 by design). Use descriptive names like `D_signals_present` or `D_signals_graduated_pct` so the result is informative regardless of value. False is not a failure if false is the expected day-1 state.

**Scope**: `/admin/diag/<pr-name>-verify` is for read-only verification SQL. One-shot write operations (backfills, repairs) live under `/admin/trigger/<action>` and are a separate category — they do not replace the diagnostic endpoint and are not removed on the same schedule.

### Secrets

The operator chose to rely on "secrets don't enter the diff in the first place" as the primary defense. This is Claude Code's responsibility:
- Never commit `.env`, credentials, API keys, or DB passwords.
- Before triggering codex review, sanity-check the diff does not contain anything that looks like a secret (`sk-*`, AWS keys, Bearer tokens, connection strings with embedded passwords).
- If you're unsure, ask the operator before running `codex exec`.

### How to handle codex findings

Codex returns free-text review. Three categories:

1. **Genuine issue you agree with** → fix it, re-run codex, proceed.
2. **False positive or already-considered tradeoff** → reply in the PR description explaining why, proceed. Don't silently ignore.
3. **Disagreement (you think codex is wrong, or it's a judgment call)** → **stop. Report to operator.** The operator will decide whether to loop in claude.ai for a third opinion. See §5.

**Never merge over a codex objection without explicit operator approval.**

---

## 5. Three-way collaboration protocol

The operator coordinates three independent AI instances:

- **claude.ai** (Anthropic consumer product, web interface) — strategic discussions, report maintenance, architecture decisions
- **Claude Code** (this instance) — in-repo operations, code changes, runtime diagnostics
- **Codex CLI** (OpenAI, local) — independent code review, correctness check

You (Claude Code) are not in direct communication with the other two. The operator is the router.

### What to do when

| Situation | Action |
|---|---|
| Pure code task inside known patterns | Do it, codex review, report back |
| Architecture / design decision with multiple valid options | Report to operator *before* coding, propose options |
| Disagreement with codex review finding | Report to operator, propose your counter-argument, wait |
| Operator asks "what does claude.ai think?" | Prepare a concise summary of your position (so operator can relay it) |
| You think the operator's request conflicts with CLAUDE.md | Point it out once. If the operator confirms, proceed (they override the doc) |

### When to ask for claude.ai input explicitly

- Major refactors affecting 3+ files
- Schema migrations (especially destructive ones)
- Decisions about data integrity or business logic (e.g., how to downsample price history)
- If you and codex disagree on a non-trivial call

In these cases, **pause**, write a summary of your analysis + codex's position, and ask the operator to consult claude.ai.

### Format when reporting to operator (for relay to claude.ai)

```
## Topic
<1-2 sentence framing>

## My position (Claude Code)
<your analysis>

## Codex review
<codex findings>

## Where we disagree (if applicable)
<specific points>

## Options
<enumerated choices with tradeoffs>

## My recommendation
<which option you'd choose and why>
```

---

## 6. History: two painful lessons from 2026-04-21/22

Read these. They're the reasons several rules above exist.

### Lesson 1: "Merged ≠ deployed ≠ working"

On 2026-04-21, the operator believed 429 retry fixes were live for ~10 hours. They were not. The code was uncommitted on a local branch while PR #10 (a different feature — Pokémon expansion) shipped the same day. Advisor (claude.ai) accepted "I fixed it" at face value. Only post-hoc log review caught the gap: 10:32 UTC ingestion ran on old code and broke the same pool in the same way.

**Result**: `git status` / `git log main..HEAD` / Railway Deployments tab are now the three sources of truth. No verbal "it's done" is accepted without at least one of these. That's why §3's "Verified-not-assumed" rule is enforced.

### Lesson 2: Invisible dependencies are the dangerous ones

eBay scheduler was registered with APScheduler for weeks but **never executed**. Reason: `cron='0 3 * * *'` + multiple daily deploys = startup always recomputed `next_run` to tomorrow's 03:00, which the next deploy missed. Fix was simple (switch to interval trigger). But the failure mode was invisible because the registration log line was loud while the execution absence was silent.

**Result**: All scheduled jobs must write `scheduler_run_log` entries. The heartbeat now checks for >25h absences and alerts Discord. When you add a new scheduled job, it must include both (execution log + absence detection) from day one. **But note**: `scheduler_run_log` only catches variants 1 (never ran) and 2 (silently misconfigured). It does not catch variant 4 (ran successfully but downstream-filtered) — see Lesson 4 for that.

### Lesson 3 (subtler): Dead config misleads

`rate_limit_per_second = 5.0` was declared on `PokemonClient` but never read. The operator and advisor both assumed it was enforcing rate limiting. It wasn't. Day 2 activation closed this gap — but the pattern recurred in `EBAY_INGEST_CRON` env var (still referenced after migration to interval trigger). Both deleted.

**Result**: See §3 "Dead config" rule.

### Lesson 4: "Designed, ran, written, but downstream-filtered silently"

This is the fourth variant of the "designed but never X" failure class. Earlier variants are each detectable at a distinct layer: Lesson 1 catches deployment gaps (code not on the running instance); Lesson 2 catches scheduler gaps (job never executing, visible through missing or zero-records `scheduler_run_log` entries); Lesson 3 catches config gaps (attribute declared, never read). The fourth variant passes all three layers — `scheduler_run_log` shows 100% success — but is invisible at the product layer.

YGO ingestion was registered, scheduled, executing, and writing to `price_history` — `scheduler_run_log` showed 100% success for two weeks. But every YGO row was being silently dropped at the signal computation layer because `market_segment` was NULL and PR B's signal filter required `market_segment = 'raw'`. The data was reaching the database; the database just wasn't reaching the product.

**Result**: end-to-end verification cannot stop at "data hits the DB." It must trace through to product output. For new data sources, the verification SQL must include: (a) row count grew in `price_history`, (b) row count grew in `asset_signals` for that game/source, (c) Card Detail page renders for sample assets from that source. If any of these three fail despite (a) succeeding, the source is in the "fourth variant" state. The full chain is:

1. Ingest writes
2. Schema invariants hold (segment populated, FKs valid, etc.)
3. Filter layer includes the data
4. Compute layer produces signals
5. Display layer renders to product
6. Regression check: existing data sources unaffected

A new data source is not "live" until all six layers show evidence.

### Lesson 5: Surface-level bugs surface deeper bugs

Activating YGO and opening YGO Card Detail pages exposed two bugs that also existed for Pokemon: Signal History showed identical "50 changes" on every card (placeholder rows from pre-migration data leaking through), and the TCGPlayer column was hardcoded to `pokemon_tcg_api` source. Both bugs had been present since their respective code paths were written, but the conditions that triggered them — assets with no real signal transitions, assets whose primary price source isn't TCGPlayer — were rare for Pokemon's active flow.

**Result**: each new game / data source exposure is implicitly an audit of empty-state and non-default code paths. Treat the "secondary bugs surfaced during activation" not as scope creep but as the activation's main deliverable for code quality — specifically bugs that block accurate activation verification or expose source/game assumptions baked into the code. Defer unrelated polish to follow-up issues. Budget for this category when planning new game launches. **Follow-on example (2026-04-27)**: the §7 production refresh — a routine docs calibration task — surfaced the `ebay_sold` future-dated rows pollution that was 9 days from entering the signal baseline window. The surface task was as mundane as possible; the latent bug was not. The more ordinary the audit, the more likely it reaches non-critical-path code that nobody is actively watching.

### Lesson 6: Catalog source ≠ price source — never couple them

`fetch_set_entries` was designed to simultaneously serve as catalog source (which cards exist) and price source (what they sell for). For sets released 2020–2022 (POTE, TOCH) this worked — YGOPRODeck has price data for those sets. For all 11 sets released 2023 onward, YGOPRODeck returns `set_price = "0"` for every entry. The ingest filter `if price <= 0: continue` was correct in isolation — empty prices shouldn't write `price_history` rows. But because the same loop also created the asset row, **price filtering silently dropped the catalog**.

Production state confirmed 2026-04-29 via `/admin/diag/ygo-13set-coverage` (binary distribution, no partial coverage):

| | Year range | sets_in_code | sets_with_assets |
|---|---|---|---|
| Pre-2023 (POTE, TOCH) | 2020–2022 | 2 | 2 |
| 2023+ (AGOV, BLTR, CYAC, DUNE, INFO, LEDE, MZMI, PHNI, RA01, RA02, WISU) | 2023–2025 | 11 | **0** |

The `scheduler_run_log` shows `status=success, sets_failed=[]` for all 50+ runs — the ingest is "working" in every observable sense while systematically omitting 11 of 13 configured sets.

**Detection test**: when a single source serves dual roles (catalog + price), ask: *if the price source returned empty for a real card, would the asset still exist in the database?* If no, the source is fatally coupled.

**Resolution pattern**: split into two ingest passes. Pass 1 writes the catalog (asset rows, no price filtering). Pass 2 writes prices, and is allowed to write zero rows without affecting the asset's existence. This applies to all current and future game integrations.

**Result**: any price-source coupling in a catalog-building function creates a silent data gap invisible to all existing monitoring. The planned Phase B fix: replace `fetch_set_entries` (which filters price=0) with a catalog-only `fetch_set_cards` that builds all assets first, then let eBay be the price source. Because the gap is binary (not partial), Phase B-1 migration is pure addition — no merge logic, no conflict resolution. Running the diagnostic first (`/admin/diag/ygo-13set-coverage`) converted this from inference into fact before writing the migration, which simplified the PR scope considerably.

### Lesson 7: External upstream outage ≠ our system broken — distinguish them before diagnosing

2026-04-26 to ~2026-04-30: eBay experienced a multi-day outage (suspected DDoS by hacktivist group "313 Team"). eBay's official status page showed all-green throughout. Impact on Flashcard Planet:

1. `ebay-ingestion` ran 3+ hours instead of normal <30 min — per-call latency degraded from ~3s to ~18s (timeout edge). `scheduler_run_log` showed the job was running; nothing in our code was broken.
2. YGO eBay spike blocked with HTTP 500 + errorId `10001` on every call. `10001` normally means "quota exceeded" but during the outage eBay returned it as a generic failure code for any request. Our quota detection code (`if "10001" in resp.text`) was correct for normal operation — it became misleading only because eBay was reusing the error code.
3. `calls_today` counter (based on `metadata->>'ebay_sold_last_ingested_at'`) only counts successful writes, not attempted API calls. During the outage, many calls were attempted but failed before write — counter underreported actual usage.

**Key diagnostic signals that distinguish "upstream broken" from "our system broken":**
- HTTP 500 from eBay across ALL queries (not just specific cards) → upstream
- HTTP 429 with normal latency → our quota
- Generic eBay error codes (e.g. `10001`) become unreliable during outages — cross-check with Down Detector
- Down Detector + StatusGator are more trustworthy than vendor status pages during incidents
- Job duration anomaly without error status (3h run that logged `success`) → upstream latency, not logic bug

**Pre-spike gating (replaces "wait for quota reset" heuristic):** Before running any eBay-dependent diagnostic, all three must pass:
1. eBay Down Detector shows operational > 1 hour
2. Production `ebay-ingestion` last cycle `finished_at - started_at < 15 min`
3. `/admin/diag/ebay-budget` shows healthy `calls_today` accumulation pattern

**What didn't break:** multi-source architecture held — Pokemon ingest (pokemon_tcg_api), YGO catalog (ygoprodeck_api), signal sweep, Discord heartbeats all continued normally. A single upstream outage degrades but does not halt the platform.

**Result**: when a scheduler job shows anomalous duration or a diagnostic tool returns unexpected errors, check external dependency health (Down Detector, StatusGator) before diagnosing internal code. The job behaving correctly under degraded upstream is a success mode, not a failure mode — don't send a PR to "fix" it.

### Lesson 8: External dependency failures are free fault-injection tests — ask "is our system still correct?"

The April 2026 eBay outage forced the signal system to operate on TCG API data only. This made Bug 1 (liquidity_service counting TCG polls as "sales") visible: without eBay data, every card had `liquidity_score=95-98` and `alert_confidence=83-86` driven entirely by hourly TCGPlayer polling. The leaderboard filled with "0 sales, BREAKOUT" entries that were pure TCGPlayer listing price movements.

If the outage hadn't happened, Bug 1 might have persisted for months: eBay data would have been sparse but present, partially suppressing the worst false positives, and the core logic error would have stayed invisible.

**Pattern to apply**: whenever an external dependency goes down or degrades, before restoring it, ask: *"Is our system producing correct output right now, or is the dependency's absence exposing a logic error in how we use it?"* If the output looks wrong with the dependency absent, the dependency was probably masking a bug — fix the bug before restoring the dependency.

**Specific signal to watch**: if `scheduler_run_log` shows `status=success, records_written=0` for a job that calls an external API, and this persists for multiple consecutive runs — don't assume the API is healthy just because our code is running. The zero-output pattern requires its own alert category (see `get_zero_output_jobs` in `scheduler.py`). A job that burns API quota and writes nothing is in the "ran usefully" vs "ran uselessly" gap that `status=success` cannot distinguish.

### Lesson 9: `status=success` ≠ useful output — monitor the gap separately

`scheduler_run_log.status` only answers "did the job run to completion without exceptions." It says nothing about whether the job produced any value. The gap between "ran" and "ran usefully" is invisible to the existing 25h-absence alert.

Canonical example: eBay ingest with `api_calls_used=201, records_written=0, status=success` for 14 consecutive runs over 2+ days. Monitoring was silent throughout.

**Detection pattern**: for every job that calls an external API and writes to the DB, define a "useful output" metric (`records_written > 0` for ingest jobs). Alert separately when ALL completed runs in a sliding window have zero useful output. Implemented as `get_zero_output_jobs()` in `scheduler.py`, called from the heartbeat. Default window: 24h, configurable via `ZERO_OUTPUT_ALERT_WINDOW_HOURS`.

**Addition rule**: whenever a new scheduled job is added that calls an external API, add it to `_monitored_jobs` in `_send_heartbeat`. "Job runs without errors" ≠ "job is working."

### Lesson 10: Symptom timeline alignment across ≥3 independent sources is causal evidence

During the eBay investigation, three independent anchors aligned:
1. eBay outage reported externally: 2026-04-26 ~22:30 ET
2. Last productive eBay ingest: 2026-04-27 08:37 UTC (47 records)
3. `match_status_counts: {}` pattern began: 2026-04-28 03:22 UTC

This upgraded "strongly consistent with outage" to "confirmed root cause" without needing direct HTTP response logs from eBay's API.

**Rule**: when ≥3 independent anchors align coherently (outage starts → last success just before → first failure just after), accept this as causal evidence. Two-point alignment (only external report + our failure) requires more investigation before declaring root cause.

### Lesson 11: Audit artifacts and fix PRs are separate — never mix them

This audit ran: investigation → SQL evidence → Codex methodology review → reconciliation → findings report → separate fix PRs (P0, P1, P2, DC-2). Each step produced a durable artifact in `audits/2026-05-01/`. The pre-fix evidence (`p0-pre-fix-evidence.md`) is permanent; each fix is reversible and traceable back to the audit report.

Mixing audit evidence with fix code makes the audit unverifiable. For future bugs: (1) document SQL evidence separately before touching code, (2) confirm root cause with runtime evidence, (3) open the fix in a dedicated PR referencing the evidence. Do not write fix code before step (2) completes.

### Lesson 12: Adjacent spec decisions can produce silent contradictions

TASK-301d (2026-05-03) decided watchlist runs client-side. TASK-301e (written later the same day) spec'd "Section 2: watchlist movers" assuming server-side watchlist data existed. Both decisions were individually correct; together they were inconsistent — invisible to anyone reading only one spec.

**Pattern**: when a task spec references another system, table, service, or capability, verify that the referenced thing exists *and behaves as the spec assumes* before writing any implementation. "It should exist" is not verification. Use grep / SQL / code-read to confirm current state. If a contradiction surfaces, stop, name both conflicting decisions, and wait for operator resolution — do not pick a side silently.

**Trigger**: any spec that references another task's output, another service's API, a schema column introduced by a different PR, or a behaviour owned by a different task. These are cross-boundary assumptions that can diverge without either side knowing.

### Lesson 13: A new enum value silently coerced to default is a silent tier downgrade

PR #43 (2026-05-04) added `Tier.PLUS` on the backend. `UserContext.tsx` on the frontend had two ternary coercion sites that pattern-matched on `'pro'` only — anything else fell through to `'free'`. Every `plus` subscriber saw free-tier UI. The backend change was correct; the bug was entirely in the frontend coercion layer, and no test covered the `plus` value because it hadn't existed when the tests were written.

The gap: enum values added on one side of the stack are invisible to other sides unless explicitly grepped. The backend `Tier` class, the DB CHECK constraint, the TypeScript union type, and every conditional or ternary that switches on tier are four separate surfaces that must all be updated atomically. Missing even one is a silent regression.

**Result**: see "Enum extension verification" in §3 Code patterns. Every PR that introduces a new enum value must enumerate all handling sites in its description and verify each was updated. Codex Cloud caught this as P1 in review — the pattern is predictable enough that Codex can be relied on to flag it, but the checklist should be run before opening the PR, not after.

---

## 7. Current state anchors

Things that are true as of 2026-04-29 and unlikely to change soon:

- **Assets**: ~4,304 Pokemon + 67 YGO = ~4,371 total (338 without price history). Pokemon expanded via eBay ingestion since 2026-04-22 creating new asset records; local DB snapshot (~2,898) is stale. YGO: **production has 67 assets across 2 sets only — POTE (40) + TOCH (27)**. `YGO_PHASE2_SETS` in code = 13 sets (5 original + 8 added in PR #28), but 11 of those 13 produce 0 assets because YGOPRODeck returns `set_price = "0"` for all their entries. Root cause: `fetch_set_entries` uses YGOPRODeck as both catalog source AND price source; the 11 empty sets are AGOV, BLTR, CYAC, DUNE, INFO, LEDE, MZMI, PHNI, RA01, RA02, WISU — all 2023+. Distribution is binary (no partial coverage cases). Verified 2026-04-29 via `/admin/diag/ygo-13set-coverage`. **Do not write "13 sets seeded" anywhere** — code config ≠ production reality.
- **Price history**: ~797k rows total (production, 2026-04-27). `pokemon_tcg_api` dominant (bulk-refresh writes ~94k rows/day for all curated sets + scheduled-ingestion ~17k/day). `ebay_sold` 1,380 rows, 426 distinct assets, captured 2026-04-21 to 2026-04-27 only (verified 2026-05-14 against production endpoints + backup-14; the earlier ~5.5k figure was a carried-forward estimate, never a verified SQL count). `ygoprodeck_api` ~1k (67 assets × ~16 ingest cycles since activation). All production rows have `market_segment` populated as of 2026-04-27 — alembic 0025 migration (PR #26) backfilled original 134 YGO rows; `/trigger/backfill-ygo-segment` one-shot cleared the 2,814 post-migration NULLs that accumulated while ingest fix was not yet deployed. `null_audit` confirmed zero NULLs. Note: `max(captured_at)` shows `2026-05-06` — likely naive datetime storage artifact; does not affect signal windows (computed relative to `NOW()`).
- **Signal state** (4,033 assets with signals, 338 without): BREAKOUT 110, MOVE 190, WATCH 127, IDLE 487, INSUFFICIENT_DATA 3,119 (77.3%). INSUFFICIENT breakdown not available from existing admin endpoints — local snapshot had `bulk_baseline_price` ~1,125 / `no_current_data` ~547 / `no_baseline_data` ~100 but local asset count is ~1,400 lower so ratios don't transfer. YGO contributes 67 to INSUFFICIENT (all 67 assets; expected — only 4 days of data as of 2026-04-27, baseline window requires ~7-14 days). Non-INSUFFICIENT YGO signals expected to appear around 2026-05-07.
- **Known open problems** (see session handoff for the latest — may be stale by the time you read this):
  - Orphaned `running` rows in `scheduler_run_log` are now cleaned up at startup via `cleanup_stale_runs` (120-min threshold). New orphans from container crash are auto-closed on next deploy.
  - `pokemon_tcg_api` price data "3 days stale" on 2026-04-22 was a false alarm. SQL confirmed data flowing continuously 8–37k rows/day every day. Root cause: `scheduler_run_log` visibility gap (no run_log rows for `scheduled-ingestion` before its instrumentation was confirmed working). Resolved by PR #13.
  - All 6 scheduler jobs now write `scheduler_run_log` (resolved 2026-04-23).
  - **Backup system live.** GitHub Actions `daily-backup.yml` runs at 04:00 UTC daily → `backup.sql.gz` asset on `ivancjz/flashcard-planet-backups` GitHub Releases. 30-day rolling retention. Discord alert on failure. APScheduler watchdog (`backup-freshness-check`, interval/4h, first run startup+15000s) verifies a fresh backup appeared and alerts if not. 4h cadence caps detection latency regardless of deploy time. Quarterly local download via `backend/scripts/backup_to_local.sh`. Restore: `docs/runbooks/restore-from-backup.md`. **First restore drill: 2026-05-13** — backup-14 (449 MB), 53.9s download + 11.3s gunzip + 49.3s restore = ~115s RTO. Row counts matched within expected 28h drift. See `docs/runbooks/restore-from-backup.md` drill log.
  - `start_run` outside `try` block for all scheduler jobs — if `start_run` itself raises (DB pool exhaustion, transient network issue), the job crashes without leaving a `scheduler_run_log` row AND without triggering a Discord alert. Accepted tradeoff on 2026-04-23; 25h heartbeat alert provides eventual detection. See PR #13 Codex Review Finding #3 for full rationale. Proper fix: wrap `start_run` in its own try/except with separate alerting path; treat as hardening work, not urgent. **Re-evaluate if**: (a) scheduler_run_log shows unexplained gaps >2h for any job, (b) production Postgres moves off Railway-internal (latency/reliability profile changes), or (c) a second scheduler job is added that cannot tolerate silent failure.
  - 2026-05-04 throughput collapse from 429 storm in `_run_bulk_set_price_refresh` (PR #12 fix coverage gap): bulk-refresh path called `PokemonTCGImporter._sleep_for_retry` with no Retry-After cap. PR #12's 60s cap only covered `pokemon_tcg.py`. Resolution: `cap_and_backoff` applied to bulk-refresh path (commits 636da83–e453e8b, audit record: GitHub issue #46). **Mark resolved** once 48h post-deploy SQL shows bulk-refresh failure count < 2/day.
  - **Issue E — RESOLVED (by design, calibration deferred)** (diagnosed 2026-05-07): Three hypotheses tested and refuted via SQL: (1) `MIN_CURRENT_N_FOR_SIGNAL` too high — REFUTED (current_n=10 for all affected assets); (2) baseline coverage gap — REFUTED (baseline_n=5-6, all assets >14d old); (3) data freshness lag — REFUTED (no new assets, no ingest gap). Actual root cause: 2,353 of 2,390 INSUFFICIENT_DATA assets are downgraded for `bulk_baseline_price` — intentional filter suppressing spurious +1000% BREAKOUT signals from $0.01–$0.10 bulk commons. NOT a bug. Open product question (deferred, NOT a code fix): is 58% bulk-commons rate the right tradeoff? Could floor be tier-based? **Do not adjust `_apply_signal_downgrade` without explicit calibration design and operator approval.**
  - **Issue D (P0) — `asset_signal_history` disk growth** (discovered 2026-05-07): `_append_history` in `signal_service.py` (lines 622, 641, 660, 709) writes one row per asset per sweep unconditionally — not only on label transitions. DB is 3.3 GB total; `asset_signal_history` alone is 2.6 GB (79%), 5.8 M rows. Growth rate ~174 MB/day (~387k rows/day at 96 sweeps/day × 4,033 assets). Headroom to full: TBD — confirm Railway Postgres volume limit in Railway dashboard → Postgres → Storage tab. **Audit findings (2026-05-07):** All 4 callsites are transition-safe — all write INSUFFICIENT_DATA or a classified label for every asset every sweep; a transition guard is semantically correct for all four. All 5 product queries (`/cards?sort=recent`, watchlist export, batch cards sort=recent, card detail signal history, `/alerts`) already filter `WHERE previous_label IS NOT NULL AND label IS DISTINCT FROM previous_label` — none depend on every-sweep rows. `get_daily_snapshot_signals` (signal_service.py:753) is confirmed dead code: its only caller (`site.py:signals_page`) was removed in the SPA migration commit 2b84b10; no production path calls it. Dead-code confirmation clears the one audit blocker. **Phase 1 (transition guard) deployed 2026-05-06 in commit `78bd30b`** — guard placed inside `_append_history` itself (returns early when `previous_label == signal.label.value`); single function-level site covers all 4 callsites, no per-callsite logic. **Phase 2 (retention prune) tracked as TASK-105 in `BACKLOG.md`**, blocked on 48h verification gates (see below). The original fix-path constraint still holds: do NOT prune before verification confirms inflow reduced — only buys ~10 days otherwise and the problem recurs. **48h verification gates (all must hold after deploy):** rows_written/day drops from ~387k toward transition rate; ratio rows_written:transitions approaches 1:1 via `/admin/diag/signal-history-stats`; DB total size growth rate drops from ~174 MB/day to <10 MB/day. `observation_match_logs` (127 MB, no purge) is a secondary concern — growth currently paused while eBay ingest is dark, but needs a purge policy before Browse API is wired.

---

## 8. What "project boundary" means

You operate within:
- `C:\Flashcard-planet\` directory tree
- The corresponding Railway services (Postgres + app)
- The `ivancjz/Flashcard-planet` GitHub repo
- `codex exec` as an external tool callable for review

You do NOT touch:
- Other repos, other Railway projects, or any other Railway accounts
- Operating system configuration
- The operator's personal machine settings outside the repo directory
- Secrets in any form that leaks them to logs, commits, or external calls

If a task seems to require crossing these boundaries, **stop and report to the operator**. Do not attempt workarounds.

---

## 9. Operator preferences (learned over 2026-04-21/22)

- **Direct feedback is welcomed.** The operator will say "you're wrong" when they disagree and expects the same from you. Don't soften bad news.
- **Operator reads SQL fluently**, and has deep domain knowledge of Pokémon TCG market. When the operator says "this doesn't match what I see on eBay," that's a strong signal — listen.
- **The operator moves fast.** They would rather ship a small imperfect thing now and iterate than wait for a perfect plan. But they will also respect "stop — this needs more thought" if you have a concrete concern.
- **The operator does not want excessive caveats or hedging.** State your position, explain the reasoning briefly, and let them decide. Long "on the other hand..." passages get skimmed.
- **The operator prefers shorter, specific questions over open-ended ones.** Use `ask_user_input` equivalents with 2-4 options when you have uncertainty.
- **Language**: Mix of English and Chinese is fine, as in the advisory conversations. Keep technical terms in English (commit messages, code, error messages). Narrative can switch.

---

## 10. Getting started when you pick up this project

1. Read `.claude/session-handoff-<latest>.md` for the most recent state.
2. Read `BACKLOG.md` for the active task queue and how to pick a task without operator input.
3. Run `git status && git log --oneline -20 && git branch -a` to see recent activity.
4. Run `git log -1 --stat` to see the last commit's scope.
5. If the session-handoff lists pending tasks, proceed with the highest priority one. If unclear, ask the operator.
6. **Do not assume** that anything described in a session-handoff is still true 24 hours later. Verify the current state before acting.

---

## 11. Archived: Signal Hysteresis Bands

Investigated 2026-04-26. Top 20 high-flip cards showed:
- WATCH→IDLE oscillations were `prediction=None` bugs (fixed in PR #18), not threshold boundary thrashing
- MOVE→BREAKOUT and BREAKOUT→IDLE: zero oscillations in 30-day data

No data supports adding hysteresis bands. Re-evaluate if:
- Single-card transition count exceeds 50/30days with consistent delta in narrow band
- Standard deviation of trigger deltas <1% (indicates threshold-grazing not real volatility)

---

## 12. Backlog: Deferred restores from testing phase

### Restore Pro gate on AI Analysis panel (PR #34)

Currently temporarily open for testing phase. To restore the Pro tier gate:
1. Search for `-- TEMP` in `backend/app/api/routes/web.py` containing "Restore when commercial tier is finalized" — the `s.explanation AS ai_analysis` SELECT line
2. Remove that line from the unconditional SELECT
3. Add `access_tier` param to `web_card_detail` (match existing auth pattern in the codebase)
4. Gate the field: `s.explanation AS ai_analysis` only when `can(access_tier, Feature.SIGNAL_EXPLANATION)`
5. Update the 3 TEMP test cases in `tests/test_web_routes.py::WebCardDetailTests` to assert tier-gated behaviour

All supporting infrastructure (`Feature.SIGNAL_EXPLANATION`, `can()`, the pattern in `signals_feed_service.py:63`) is already in place.

### Backlog: find and fix the source of the "3 days no data" label

The "3 days no Pokémon data" wording for the 2026-05-04 incident came from conversation/session handoff — source not confirmed to be an automated alert. Two places to check: (1) `_send_heartbeat` in `backend/app/backstage/scheduler.py` around the zero-output and 25h-absence checks; (2) session-handoff-*.md files in `.claude/`. `last_priced_at` does **not** exist in the codebase — any alert watching it is hypothetical until confirmed. Do NOT conflate this audit with the 429 fix (separate PR).

### Backlog: move PokemonTCGImporter out of scripts/

`PokemonTCGImporter` lives in `scripts/import_pokemon_cards.py` but is called directly by the production scheduler (`_run_bulk_set_price_refresh` in `scheduler.py`). `scripts/` is the conventional location for one-off CLI tools; placing production scheduler dependencies there breaks the expectation that everything under `backend/app/` is the production package boundary. Move to `backend/app/ingestion/` when convenient (no urgency — separate PR).

### Backlog: revisit main-direct policy for retry/backoff/rate-limiting changes

Current policy ("Operator trusts you to push to main directly") is correct for velocity and fits the solo-dev Railway auto-deploy setup. But there is a category of change where main-direct is higher risk: **production retry/backoff/rate-limiting logic**. This category has a history of "designed but never ran" / "fixed but not on all paths" failure modes — eBay ingest, signal sweep, PR #12 coverage gap (bulk-refresh), and the 2026-05-04 incident. The gap between push and first visible alert can be minutes to hours.

Consider requiring feature-branch + Codex-review-before-merge specifically for changes to: retry budgets, backoff delays, rate-limit guards, and circuit-breaker logic. Not blocking velocity for other change types.

This backlog item is a "someday / Sunday decision" — do not implement without explicit operator decision. It is recorded here so the next session has the context.

---

## 13. Active experiments

### YGO Phase 2 unblock — final criteria (2026-05-14)

Source resolved: CardMarket public price guide (see §2 CardMarket data source). No further reframes expected.

**1. CardMarket JSON ingest job**
- Fetch `https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_3.json` daily ~04:00 AEST (after CET ~02:43 daily refresh)
- Store `avg1`, `avg7`, `avg30`, `trend` as four separate sources: `cardmarket_avg1`, `cardmarket_avg7`, `cardmarket_avg30`, `cardmarket_trend`
- Do NOT blend. Each source independently tracked.
- Budget: single ~16 MB download, negligible cost.

**2. Signal engine source-awareness**
- Per-source thresholds (`cardmarket_avg7` will be primary, `cardmarket_avg30` baseline)
- Volume-proxy quality flag: high dispersion between `avg1`/`avg7`/`avg30` → `insufficient_data`
- Documented in code, not just CLAUDE.md

**3. YGO seed cards**
- 50–100 cards drawn from CardMarket high-coverage modern sets
- Avoid vintage tier where EU/US gap > 30%
- Avoid cards with <10 entries in `avg30` (proxy for liquidity)

**4. 7-day CardMarket data accumulation before signal sweep enabled**

**5. Discord alert format**
- Source-agnostic alerts: "YGO breakout detected on Card X"
- No CardMarket price figures displayed
- Link to Flashcard Planet card page for detail

Estimated 3–5 days solo dev work. No external dependencies blocking. Triggerable whenever Pokémon baseline is stable (depends on Issue B resolution).

---

## 14. Operational tooling gaps

### scheduler_run_log per-row queries unavailable in production

Existing `/admin/diag` endpoints expose aggregates only (`/diag/scheduler-history` groups by `(job_name, day)`). Forensic investigations requiring per-row inter-run spacing — e.g. the May 11 2026 anomaly where `ebay-ingestion` logged 30 runs vs 6–8 for other jobs — cannot be completed without either:

- **(a)** Railway Postgres TCP proxy + `railway run` access to `psql` or a Python DB connection (currently blocked: `postgres.railway.internal` is not resolvable from local; no public TCP proxy configured), or
- **(b)** A generic `/admin/diag/scheduler-runs?job_name=<name>&date=<YYYY-MM-DD>` endpoint returning per-row `started_at`, `finished_at`, `status`, `records_written`, `meta_json`.

**Deferred.** Do not implement (b) until the next forensic investigation also stalls on this same gap. At that point, the accumulated cost justifies the endpoint.

### CLAUDE.md statistical claims not systematically dated

Carryover-from-old-revision risk verified 2026-05-14 (ebay_sold count was stale by ~4x). Future statistical claims should be tagged with verification date inline. Backlog item: audit existing claims, no time pressure.

### User-facing source attribution policy (pending)

When external sources contribute to a signal but data is not displayed directly to users, the about page should list contributing sources for transparency (Pokemon TCG API, CardMarket public price guide, etc.) without quoting prices. Pending UX/legal hygiene item, deferred until YGO Phase 2 ships.

### metadata_json as cross-source asset identifier store

`metadata_json` is the current catch-all for cross-source asset identifiers: `set_id` for Pokémon (set by YGOPRODeck ingest), `cm_product_ids` for CardMarket (added by Phase 2 CardMarket ingest), future sources will continue to add keys. Pattern accepted at 2-source scale. Trigger to extract to a dedicated `asset_external_ids` table: when adding a 3rd source, OR when any source needs multi-id per asset (currently all are 1:1 between source and list of IDs).

### Latent-trap audit pattern for source deprecations

When deprecating a data source, code-level exclusion + weight removal must accompany documentation. Documentation alone leaves the door open for accidental re-introduction. Future source deprecations must: (1) add explicit `source != X` to all analytical query WHERE clauses, (2) remove source weight from `signal_delta_source_weights`, (3) update relevant tests to assert the new exclusion behavior, (4) update this doc. Verified necessary 2026-05-14 when `ebay_sold` audit found 1,380 rows reachable by baseline computation for 426 assets despite months of doc-stated deprecation.

### CardMarket EUR/USD hardcoded conversion rate

`CARDMARKET_EUR_TO_USD = Decimal("1.09")` in `signal_service.py` (set 2026-05-14) converts CardMarket EUR prices to USD-equivalent before comparing against `signal_breakout_min_price_usd`, `signal_move_min_price_usd`, and `SIGNAL_BULK_FLOOR_PRICE`. These thresholds are USD-denominated; CardMarket reports in EUR.

Threshold misclassification risk if rate drifts beyond ±10%. Trigger to update: (a) EUR/USD observed outside 0.98–1.20 range, OR (b) adding a third currency-denominated source. Long-term fix: per-source currency configuration + live exchange rate (e.g. ECB daily reference rates).

### CardMarket source weights are provisional

`cardmarket_avg7=1.0, cardmarket_avg30=0.5, cardmarket_avg1=0.0, cardmarket_trend=0.0` in `signal_delta_source_weights` default (set 2026-05-15). Weights are provisional pending production data. avg1 and trend carry 0.0 weight: avg1 is only used in the dispersion gate; trend uses an opaque CardMarket algorithm not suitable for direct signal weighting. Revisit alongside dispersion threshold calibration (Task 8) at 2026-06-14. Note: CM sources are excluded from `_compute_delta_batch()` WHERE clauses (EUR-denominated); current weights only apply if routing logic changes.

### Sample tiering by sold-count over-indexes on query-fuzzy matches

Verified 2026-05-14 during eBay Q1 analysis: "Pokemon Pikachu Base" matched Shadowless, 1st Edition, Unlimited, and Yellow Cheeks Pikachu variants as one card because `_build_search_query` does not include card number. Sold-count-based tier assignment treats multi-variant query matches as one card — the high sold count reflects query fuzziness, not single-card liquidity. Future eBay or market analyses should tier by realized-price tier and collectibility category (e.g. vintage holo / modern rare / modern common), not raw sold-row count.

---

*This file is living documentation. When you learn something about the project that another Claude instance would benefit from, propose an update to this file in a dedicated commit.*

## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool. When in doubt, invoke the skill.

Key routing rules:
- Product ideas/brainstorming → invoke /office-hours
- Strategy/scope → invoke /plan-ceo-review
- Architecture → invoke /plan-eng-review
- Design system/plan review → invoke /design-consultation or /plan-design-review
- Full review pipeline → invoke /autoplan
- Bugs/errors → invoke /investigate
- QA/testing site behavior → invoke /qa or /qa-only
- Code review/diff check → invoke /review
- Visual polish → invoke /design-review
- Ship/deploy/PR → invoke /ship or /land-and-deploy
- Save progress → invoke /context-save
- Resume context → invoke /context-restore
