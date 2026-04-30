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
- **NULL census before filter rollouts**: any new `WHERE` clause that excludes data based on a column value (e.g., `WHERE market_segment = 'raw'`) requires a pre-rollout NULL census across the entire affected table, grouped by source: `SELECT source, COUNT(*) FROM <table> WHERE <column> IS NULL GROUP BY source`. The rollout is safe only when this returns zero rows or only sources that the filter intentionally excludes. Verifying "the target rows look right" is not enough — silent-exclusion filters are about what gets dropped, and the dropped set must be enumerated explicitly. PR #26 exposed this: PR B's `market_segment = 'raw'` filter silently dropped all YGO rows because they had `market_segment = NULL`, and PR B's pre-merge SQL had only verified `pokemon_tcg_api` was correct.
- **Local DB absolute counts are not authoritative**: when a local audit surfaces an unexpected number (e.g., "22,654 NULL rows"), do not act on the number — first run the same query on production. Local DBs can be arbitrarily stale relative to production migrations and backfills. Trends, shapes, and source lists from local DB are usable; absolute counts are not. The default response to an alarming local count is "production audit before deciding scope," not "expand the PR scope to fix the local number."
- **Trigger functions: `clock_timestamp()` not `CURRENT_TIMESTAMP`**: in PL/pgSQL trigger functions that compare against "now", always use `clock_timestamp()` (wall-clock, advances during the transaction). `CURRENT_TIMESTAMP` / `NOW()` are pinned to transaction start — a 10-minute ingest transaction using `CURRENT_TIMESTAMP` would false-reject valid rows captured mid-transaction, producing silent data loss that looks identical to "eBay API missed some listings."
- **Cross-PR assumption tracking**: when a PR's correctness depends on an assumption established by a previous PR (e.g., "PR A guaranteed `market_segment` is set on all rows"), the new PR's verification step must re-run the SQL that established that assumption — not assume it still holds. PRs are merged at different times against different data; assumptions drift. List the inherited assumptions in the PR description's "Assumptions" section, with the SQL used to verify each.

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

---

## 7. Current state anchors

Things that are true as of 2026-04-29 and unlikely to change soon:

- **Assets**: ~4,304 Pokemon + 67 YGO = ~4,371 total (338 without price history). Pokemon expanded via eBay ingestion since 2026-04-22 creating new asset records; local DB snapshot (~2,898) is stale. YGO: **production has 67 assets across 2 sets only — POTE (40) + TOCH (27)**. `YGO_PHASE2_SETS` in code = 13 sets (5 original + 8 added in PR #28), but 11 of those 13 produce 0 assets because YGOPRODeck returns `set_price = "0"` for all their entries. Root cause: `fetch_set_entries` uses YGOPRODeck as both catalog source AND price source; the 11 empty sets are AGOV, BLTR, CYAC, DUNE, INFO, LEDE, MZMI, PHNI, RA01, RA02, WISU — all 2023+. Distribution is binary (no partial coverage cases). Verified 2026-04-29 via `/admin/diag/ygo-13set-coverage`. **Do not write "13 sets seeded" anywhere** — code config ≠ production reality.
- **Price history**: ~797k rows total (production, 2026-04-27). `pokemon_tcg_api` dominant (bulk-refresh writes ~94k rows/day for all curated sets + scheduled-ingestion ~17k/day). `ebay_sold` ~5.5k. `ygoprodeck_api` ~1k (67 assets × ~16 ingest cycles since activation). All production rows have `market_segment` populated as of 2026-04-27 — alembic 0025 migration (PR #26) backfilled original 134 YGO rows; `/trigger/backfill-ygo-segment` one-shot cleared the 2,814 post-migration NULLs that accumulated while ingest fix was not yet deployed. `null_audit` confirmed zero NULLs. Note: `max(captured_at)` shows `2026-05-06` — likely naive datetime storage artifact; does not affect signal windows (computed relative to `NOW()`).
- **Signal state** (4,033 assets with signals, 338 without): BREAKOUT 110, MOVE 190, WATCH 127, IDLE 487, INSUFFICIENT_DATA 3,119 (77.3%). INSUFFICIENT breakdown not available from existing admin endpoints — local snapshot had `bulk_baseline_price` ~1,125 / `no_current_data` ~547 / `no_baseline_data` ~100 but local asset count is ~1,400 lower so ratios don't transfer. YGO contributes 67 to INSUFFICIENT (all 67 assets; expected — only 4 days of data as of 2026-04-27, baseline window requires ~7-14 days). Non-INSUFFICIENT YGO signals expected to appear around 2026-05-07.
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

---

*This file is living documentation. When you learn something about the project that another Claude instance would benefit from, propose an update to this file in a dedicated commit.*
