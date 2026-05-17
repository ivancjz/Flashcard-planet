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

**eBay Finding API is permanently dead.** `svcs.ebay.com/services/search/FindingService/v1` returns HTTP 500 + errorId=10001 on every call including the first of a fresh session. Not quota exhaustion — permanent endpoint rejection confirmed 2026-05-14 via forensic probe (details in git history commit `9a6e9e6`).

**eBay Browse API** (`api.ebay.com/buy/browse/v1`) returns active listings, not sold prices. Must NOT be written to `price_history`. Ask prices → `listing_snapshot` table only (not yet built).

**`_parse_insights_items` in `ebay_sold.py` is dead code** — never called. Do not wire up.

**Historical `ebay_sold` data (1,380 rows, 2026-04-21 to 2026-04-27):** grade-mix contaminated, junk prices confirmed. Do NOT use for signal threshold calibration. Excluded at code level in `signal_service._compute_delta_batch` and `liquidity_service`.

**`ebay_web_sold` (YGO only, 2026-05-17 activated):** GitHub Actions scraper (`scripts/github_ebay_scrape.py`, runs 17:00 UTC daily via `.github/workflows/ebay-scrape.yml`). Scoped to YGO assets, EN ungraded singles, 1st Edition only, writes one median-price row per asset per run. Railway IP blocked by Akamai — GitHub Actions IP works (confirmed 2026-05-18). See `docs/adr/ADR-001-ebay-web-sold-scoped-signal-source.md`.

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
- **Feature flag default conventions**: pick the default based on resource consumption profile, not abstract "safe vs unsafe" reasoning. Name the category in the PR description AND in the config comment — the choice must not be a silent decision.
  - **Category α — `Field(default=True)` (auto-activate)**: ALL must hold: read-only or read-safe (no external quota burn); idempotent or audit-trail-recoverable on failure; production value depends on early data accumulation (calibration, baseline); has built-in safety nets at downstream (rate limiting, contamination exclusion). *Example: CardMarket ingest — S3 download ETag-gated, price_history recoverable, source isolation prevents signal corruption.*
  - **Category β — `Field(default=False)` (opt-in via env var)**: ANY one: consumes external paid API quota; mutates external state (Discord alerts to users, emails, purchases); could produce user-visible bad output if misconfigured; calibration values uncertain or fail-open sentinel still in effect. *Example: eBay scheduled ingest (paid quota), signal sweep with unverified thresholds.*
  - **Category γ — bare `bool = False` (no Field — explicit code change required to enable)**: one-time experimental features; unbounded resource consumption potential; requires explicit operator decision in any environment, even staging. *Example: bulk re-ingest jobs, force-overwrite operations.* Use bare `bool = False` not `Field(default=False)` — `Field` metadata signals that env var override is acceptable, which it isn't for γ.

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

## 6. History: production lessons

Full narratives in `.claude/LESSONS.md`. Quick reference:

| # | Lesson | Rule |
|---|---|---|
| 1 | Merged ≠ deployed ≠ working | `git status`/`git log main..HEAD`/Railway Deployments are the three truth sources. No verbal "done". |
| 2 | Invisible dependencies | All scheduled jobs must write `scheduler_run_log`. Heartbeat checks >25h gaps. |
| 3 | Dead config misleads | Any declared-but-unread setting is debt. Activate it or delete it. |
| 4 | Downstream-filtered silently | Verify all 6 layers: ingest → schema → filter → compute → display → regression. |
| 5 | Surface bugs surface deeper bugs | New game/source activation audits empty-state and non-default code paths. Budget for it. |
| 6 | Catalog source ≠ price source | Never couple catalog creation with price filtering. Two-pass: catalog first, prices second. |
| 7 | External outage ≠ our system broken | Check Down Detector / StatusGator before diagnosing internal code. |
| 8 | Failures are free fault-injection tests | When a dependency degrades, ask: "Is our output still correct without it?" |
| 9 | `status=success` ≠ useful output | Monitor `records_written=0` separately. Add new API jobs to `_monitored_jobs`. |
| 10 | ≥3 anchors = causal evidence | Three independent timeline anchors aligned coherently is sufficient to declare root cause. |
| 11 | Audit artifacts and fix PRs are separate | Document SQL evidence first. Confirm root cause second. Fix in dedicated PR third. |
| 12 | Adjacent specs can silently contradict | When a spec references another system, verify it exists and behaves as assumed before coding. |
| 13 | New enum value → silent tier downgrade | Grep all handling sites (TypeScript unions, ternaries, DB constraints, UI) before merging. |

---

## 7. Current state anchors

See `BACKLOG.md` for current task queue, asset counts, signal state, and open issues. The data in this section was accurate 2026-04-29; BACKLOG.md is the authoritative live state.

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

## 9. Approach & patterns

### 9.1 Operator preferences (learned over 2026-04-21/22)

- **Direct feedback is welcomed.** The operator will say "you're wrong" when they disagree and expects the same from you. Don't soften bad news.
- **Operator reads SQL fluently**, and has deep domain knowledge of Pokémon TCG market. When the operator says "this doesn't match what I see on eBay," that's a strong signal — listen.
- **The operator moves fast.** They would rather ship a small imperfect thing now and iterate than wait for a perfect plan. But they will also respect "stop — this needs more thought" if you have a concrete concern.
- **The operator does not want excessive caveats or hedging.** State your position, explain the reasoning briefly, and let them decide. Long "on the other hand..." passages get skimmed.
- **The operator prefers shorter, specific questions over open-ended ones.** Use `ask_user_input` equivalents with 2-4 options when you have uncertainty.
- **Language**: Mix of English and Chinese is fine, as in the advisory conversations. Keep technical terms in English (commit messages, code, error messages). Narrative can switch.

### 9.2 Evaluation & implementation discipline

**Pattern: Multi-stage prompt with mandatory pauses**

For non-trivial work spanning reference extraction, generation, verification, and integration, structure the prompt as explicit stages with operator-decision gates between them. Each stage produces an artifact (cheat sheet, generated output, grep results, diff) that the operator reviews before authorizing the next stage. Do not let the LLM auto-chain stages — chaining defeats the evidence-gate purpose.

Stages typically follow: pre-flight checks → reference extraction (PAUSE) → generation → visual/structural inspection (PAUSE) → structural grep / diff → final verdict.


---

**Pattern: 5-category post-implementation audit**

After any subagent or LLM-driven implementation phase reports "no flags" or "complete", run a structured self-audit on five known edge-case categories before accepting the result. "No flags" ≠ "no decisions made" — silent decisions are the common failure mode.

Categories:
1. No-match / missing-data paths (what if input is empty?)
2. Multi-match / ambiguity handling (what if input is duplicated?)
3. Null / zero / negative / boundary inputs (what if input is degenerate?)
4. Locale / currency / unit assumptions (what unit is the input in?)
5. Audit-log and monitoring coverage for new code paths (what does ops see?)

For each, ask the implementer to answer one of:
- "handled this way: `<description>`, code at file:line"
- "plan implicitly assumes `<X>`, code matches assumption"
- "not handled, would surface as `<symptom>`, deferred backlog item"


---

**Pattern: Fail-open over fake-precision for under-calibrated thresholds**

When a numerical parameter (threshold, weight, ratio, timeout) is derived from insufficient sample size or wrong-cohort data, do NOT ship a fake-precise value with "revisit later" intent. Ship a fail-open sentinel (e.g. `Decimal("999")` for thresholds, `0.0` for weights) that effectively disables the parameter's filtering effect, with a code comment stating:
- Why the value is fail-open
- What data would be needed to calibrate it properly
- Concrete revisit target date
- Pointer to backlog item that owns the calibration

This applies the "merge ≠ deploy ≠ verified" principle to numerical parameters: a parameter is not verified until production data has calibrated it. Fake-precision gives false confidence that the parameter is doing useful work.


---

**Pattern: Three-layer enforcement for data source deprecation**

When deprecating a data source, documentation alone leaves the door open for accidental re-introduction. Source deprecation requires three coordinated layers:

1. **Documentation** in CLAUDE.md / source comments explaining the deprecation date, reason, and remediation if re-introduction is needed
2. **Code-level exclusion** in computation paths (WHERE clauses, filter functions, aggregation queries) — explicit source IN/NOT IN guards, not date-based filters that happen to work today
3. **Configuration removal** of weights, credentials, feature flags, and any other config surface that would activate the source if data accidentally re-appeared

Documentation alone is "polite request not to use this". Layers 2 and 3 are "code-enforced cannot use this even if you try". The full three-layer approach prevents latent traps when future code, migrations, or ad-hoc scripts inadvertently write to the deprecated source.


---

**Pattern: Unit conversion at threshold comparison sites**

Threshold comparisons across mismatched units are categorical errors, not precision errors. When code computes `value_in_unit_A < threshold_in_unit_B`, the result determines a category (BREAKOUT / MOVE / WATCH / IGNORE / etc.) — any drift produces real classification errors on boundary inputs, regardless of how close unit_A happens to be to unit_B at the time of writing.

"Small drift" framing is wrong for categorical gates. Always convert units explicitly at the comparison site, even when the conversion factor happens to be near 1.0.

Implementation form:
- A constant declaring the conversion ratio with provenance + drift-watch range
- A helper function or inline conversion at every threshold comparison
- A regression test that uses a boundary input to prove the conversion is applied (e.g. value just below threshold in source unit becomes just above threshold in target unit, classification changes accordingly)


---

**Lesson: Plan specifications must include calibration fallback hierarchy**

When a task derives a value from a primary data source, the plan must explicitly enumerate fallback data sources in priority order, and a stop-condition when all fallbacks are unavailable. Otherwise the LLM implementing the task will substitute an arbitrary larger dataset under information-poor conditions and produce a confidently wrong calibration.

Standard form for calibration tasks:

> Primary dataset: `<X>`
> Fallback 1 if primary unavailable: `<Y>`, with rationale
> Fallback 2 if both unavailable: `<Z>`, with rationale
> If all fallbacks unavailable: STOP and flag, do not substitute alternative dataset.


---

**Pattern: PR description / changelog as derivative artifact**

PR descriptions, release notes, and ad-hoc summaries written by humans or LLMs at submission time are derivative artifacts — they describe code but are not synced with code. They can be wrong even when code, plan, and tests are all consistent.

When verifying behavior of newly-merged work:
- Read PR description for INTENT, not for FACT
- Verify facts directly against code (grep, config inspection, runtime probes)
- If PR description claims behavior X and code shows behavior Y, trust the code, but ALSO patch the PR description / release notes so future archaeologists don't get misled
- Treat PR description as a hypothesis that needs verification, not a ground-truth source


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


## 12. Active experiments

### YGO Phase 2: CardMarket (live 2026-05-15)

CardMarket public S3 price guide is the active YGO price source (see §2 for configuration details). Initial seed: 8 cards seeded 2026-05-17 via TASK-801. Signals expected ~2026-05-25 after 7-day data accumulation window. Next check: day-7 2026-05-24.

---

## 13. Operational tooling gaps

- **Per-row scheduler queries**: `/diag/scheduler-history` aggregates only. Add `/admin/diag/scheduler-runs?job_name=<name>&date=<YYYY-MM-DD>` when next forensic stalls on this same gap.
- **Health dashboard blindspot**: `/admin/diagnostics/json` health fields return 0 — `PROVIDER_EXTERNAL_ID_PREFIX` prefix mismatch in `data_health_service.py:21`. Do not trust `health.*` fields. Fix is one-line correction; deferred.
- **CardMarket EUR/USD hardcoded**: `CARDMARKET_EUR_TO_USD = Decimal("1.09")` in `signal_service.py`. Update if EUR/USD observed outside 0.98–1.20. Long-term: ECB reference rates.
- **CardMarket source weights provisional**: `cardmarket_avg7=1.0, cardmarket_avg30=0.5`. Revisit with TASK-8 calibration at 2026-06-14.
- **`_parse_source_weights` swallows malformed env var segments**: add `logger.warning` opportunistically.
- **`metadata_json` as cross-source ID store**: accepted at 2-source scale. Extract to `asset_external_ids` table at 3rd source or multi-id-per-asset.
- **Source deprecation pattern**: deprecation requires three layers — doc + code-level exclusion (WHERE clauses) + config removal (weights/flags). Documentation alone is not sufficient.
- **eBay sold-count tiering flaw**: query fuzziness inflates counts for multi-variant cards. Future analyses: tier by price/collectibility, not raw sold-row count.
- **Statistical claims**: tag future claims with inline verification date.

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
