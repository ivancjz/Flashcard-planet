# CLAUDE.md — Flashcard Planet Project Context

This file is the project context for any Claude instance working on this codebase (primarily Claude Code operating in `C:\Flashcard-planet`). Read this first. Then read `.claude/session-handoff-<latest date>.md` for the most recent operational state.

---

## 1. What this project is

**Flashcard Planet** is a TCG (Trading Card Game) investment signals SaaS, targeting retail TCG investors who want price movement alerts and AI-powered analysis. Pokémon TCG is the first game live; Yu-Gi-Oh is scaffolded; MTG / One Piece are roadmap.

- **Operator**: Ivan (solo dev, Melbourne, AEST). GitHub: `ivancjz`.
- **Stack**: Python 3.13 + FastAPI + SQLAlchemy 2 + Alembic + APScheduler + httpx + Postgres 18. Discord for alerts.
- **Hosting**: Railway. Hobby plan. ~AUD 300/month. **No automatic backups** (Pro plan required — not on Pro).
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
- `backend/app/ingestion/` — `pokemon_tcg.py` (Pokemon TCG API), `ebay_sold.py` (eBay sold listings), `ygo.py` (Yu-Gi-Oh scaffold).
- `backend/app/services/signal_service.py` — Signal computation. Dual-window algorithm (baseline ≥7d + current ≤24h). See `SWEEP_BATCH_SIZE` at file top.
- `backend/app/models/` — SQLAlchemy models.
- `scripts/import_pokemon_cards.py` — CLI for manual Pokemon set imports.

### Models you'll touch most
- `Asset` — card identity. Columns: `asset_class, game, name, set_name, card_number, year, language, variant, grade_company, grade_score`. UniqueConstraint on all 10.
- `PriceHistory` — price observations. Columns: `id, asset_id (FK), source, currency, price (Numeric 12,2), captured_at`. Indices on `captured_at` and `asset_id`. **No index on `source`.**
  - `source` values: `'pokemon_tcg_api'` or `'ebay_sold'` (lowercase, underscore). **Don't write `'ebay'` or `'pokemon'`.**
- `SchedulerRunLog` — job audit log. Columns: `id, job_name, started_at, finished_at, status, records_written, errors, error_message, meta_json`. Status values: `'running'` (default), `'success'`, `'partial'`, `'warning'`, `'error'`, `'failed'`.
- `AssetSignal` / `AssetSignalHistory` — signal outputs. Label values: `BREAKOUT, MOVE, WATCH, IDLE, INSUFFICIENT_DATA`.

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

## 3. Critical conventions (do not violate without explicit operator approval)

### Git workflow
- Branches always `feat/<description>` or `fix/<description>`.
- **One commit = one concern.** Day 1 merged a "bulk-refresh guard + 429 fixes" tangle and it cost us 10 hours of confusion. Keep PRs focused.
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

---

## 4. Codex review gate (mandatory)

The operator installed Codex CLI specifically to have an independent second opinion on code changes. Codex CLI is pre-authenticated and available via `codex exec "..."`.

### When to trigger codex review

**Every PR before merge to main.** Not optional. Even small changes.

The only exception: changes that touch **zero production code paths** — e.g., README edits, `.gitignore` tweaks, adding a test for existing (unchanged) behavior. If in doubt, review anyway.

### How to trigger

Before opening or merging a PR, run:

```bash
codex exec "Please review the following diff for [brief context: what this change does and why]. Focus on: correctness, security, silent failures, production risks. The project is a TCG signals SaaS; production DB has 200k+ price_history rows. Diff: $(git diff main)"
```

Claude Code must run this itself — **do not delegate to the operator**. Capture codex's output in the PR description under a `## Codex Review` heading.

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

**Result**: All scheduled jobs must write `scheduler_run_log` entries. The heartbeat now checks for >25h absences and alerts Discord. When you add a new scheduled job, it must include both (execution log + absence detection) from day one.

### Lesson 3 (subtler): Dead config misleads

`rate_limit_per_second = 5.0` was declared on `PokemonClient` but never read. The operator and advisor both assumed it was enforcing rate limiting. It wasn't. Day 2 activation closed this gap — but the pattern recurred in `EBAY_INGEST_CRON` env var (still referenced after migration to interval trigger). Both deleted.

**Result**: See §3 "Dead config" rule.

---

## 7. Current state anchors

Things that are true as of 2026-04-22 and unlikely to change soon:

- **Assets**: ~2,897 Pokémon assets tracked. Volume growing via scheduled-ingestion + eBay ingestion.
- **Price history**: ~217k rows. `pokemon_tcg_api` dominant (~212k). `ebay_sold` small (~5k, first real run 2026-04-22).
- **Signal state**: `insufficient_data=90.8%` (3832/4219) as of Day 2 sweep. Expected to improve over 2-3 weeks as eBay accumulates baseline history. Root cause: 97.7% of insufficient cases are `has_baseline_no_current` — need 24h-fresh data and eBay is the source that provides it.
- **Known open problems** (see session handoff for the latest — may be stale by the time you read this):
  - Orphaned `running` rows in `scheduler_run_log` are now cleaned up at startup via `cleanup_stale_runs` (120-min threshold). New orphans from container crash are auto-closed on next deploy.
  - `pokemon_tcg_api` price data "3 days stale" on 2026-04-22 was a false alarm. SQL confirmed data flowing continuously 8–37k rows/day every day. Root cause: `scheduler_run_log` visibility gap (no run_log rows for `scheduled-ingestion` before its instrumentation was confirmed working). Resolved by PR #13.
  - All 6 scheduler jobs now write `scheduler_run_log` (resolved 2026-04-23).
  - No backup infrastructure (Hobby plan). Operator accepted this risk explicitly; P0 remains on backlog.
  - `start_run` outside `try` block for all scheduler jobs — if `start_run` itself raises (DB pool exhaustion, transient network issue), the job crashes without leaving a `scheduler_run_log` row AND without triggering a Discord alert. Accepted tradeoff on 2026-04-23; 25h heartbeat alert provides eventual detection. See PR #13 Codex Review Finding #3 for full rationale. Proper fix: wrap `start_run` in its own try/except with separate alerting path; treat as hardening work, not urgent. **Re-evaluate if**: (a) scheduler_run_log shows unexplained gaps >2h for any job, (b) production Postgres moves off Railway-internal (latency/reliability profile changes), or (c) a second scheduler job is added that cannot tolerate silent failure.

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
2. Run `git status && git log --oneline -20 && git branch -a` to see recent activity.
3. Run `git log -1 --stat` to see the last commit's scope.
4. If the session-handoff lists pending tasks, proceed with the highest priority one. If unclear, ask the operator.
5. **Do not assume** that anything described in a session-handoff is still true 24 hours later. Verify the current state before acting.

---

*This file is living documentation. When you learn something about the project that another Claude instance would benefit from, propose an update to this file in a dedicated commit.*
