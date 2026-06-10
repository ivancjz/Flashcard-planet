# BACKLOG.md — Flashcard Planet 任务流

> **Companion docs:** `CLAUDE.md` (agent operating rules), `docs/plan-v3.md` (current-state plan), `.claude/session-handoff-<latest>.md` (24h state snapshot).
>
> **This file is for Claude Code to consume autonomously.** When picking up a session and there is no specific operator instruction, read this file and start the highest-priority task you have evidence to safely execute. See §0 below.

**Last updated:** 2026-06-10 (v15 — reconcile: PR #79/TASK-301 merged, TASK-305 + BL-1 shipped; statuses synced to git reality)
**Maintained by:** Ivan (operator) with proposed updates from Claude Code via PR

---

## Decision log

### Decision (2026-05-13): PR #14 split into PR #14a / #14b / #14c

**Authority:** Ivan + claude.ai (strategy session 2026-05-13).

The spec's single PR #14 bundled six items: backups, PgBouncer, rate limiting, audit log, Sentry+PostHog, structlog. Split into three PRs:

- **PR #14a** (this PR): Reconcile docs with live GitHub Actions backup system + execute first restore drill. R2 path retired (Cloudflare card binding unavailable). See PR #14a description for full scope.
- **PR #14b** (future): Rate limiting (slowapi) + audit log + Sentry + PostHog + structlog
- **PR #14c** (future): PgBouncer connection pooling — after prepared-statement audit

**Rationale:**
1. Backups (14a) are the only true P0 and carry a 7-day verification window ("7 consecutive days of backup logs" per acceptance criteria). That window should not gate the observability cluster.
2. PgBouncer (14c) carries prepared-statement compatibility risk requiring a codebase audit before any code lands — different release profile from the rest.
3. The observability cluster (14b: rate limiting, audit log, Sentry, PostHog, structlog) is internally cohesive and ships independently of both backups and PgBouncer.

**Scope mapping** (spec PR #14 items → split PRs):
- Scope item 1 (backups) → PR #14a
- Scope items 3, 4, 5, 6 (rate limiting, audit log, Sentry+PostHog, structlog) → PR #14b
- Scope item 2 (PgBouncer) → PR #14c

**The spec section "PR #14"** remains the merged source of truth for scope requirements. This split is a sequencing decision, not a scope reduction.

---

## 0. How Claude Code uses this file

When you start a session without a specific instruction from the operator:

1. **Read in order:** `.claude/session-handoff-<latest>.md` → this file → `git log --oneline -20`.
2. **Pick a task** following these rules:
   - Take the **highest-priority** task in §2 marked `Status: ready`.
   - If multiple tasks are at the same priority, prefer the one that **unblocks others**.
   - Skip any task whose `Preconditions` are not met. If you think a precondition is met but unsure, check the relevant SQL/files first.
3. **Before coding:**
   - Confirm preconditions with concrete evidence (SQL, file existence, env state).
   - Update the task status from `ready` → `in_progress` in this file via a one-line commit (`chore(backlog): start TASK-X`).
4. **Execute** following the standard PR workflow in `CLAUDE.md` §3-4 (TDD, codex review, diagnostic endpoint if needed).
5. **On completion:**
   - Move the task to §3 (Completed) with the PR number and merge date.
   - If you discovered new tasks during execution, propose them at the bottom of §2 with `Status: needs_triage`.

**Hard rules:**

- **Never start a task marked `Status: blocked` or `Status: needs_decision`.** These require operator input first.
- **Never modify §1 (P0 invariants) without explicit operator approval** — those are non-negotiable invariants, not items to "do".
- **One task in `in_progress` at a time** unless the operator explicitly parallelises.
- **If you are about to take a task but the production state contradicts the precondition** (e.g., the file you'd modify has been refactored, the SQL evidence the task depends on shows different numbers), **stop and report** instead of forcing the task through.

---

## 1. P0 invariants (do not "complete" — these are always true)

These are not tasks. They are properties of the system that must hold at all times. If a task threatens any of these, stop.

- [ ] **Pokemon ingestion runs daily without manual intervention.** `scheduler_run_log` shows `ingestion` job with `status='success'` within the last 25 hours.
- [ ] **All 6 scheduler jobs write `scheduler_run_log`.** No silent failures.
- [ ] **Discord alerts fire within their 25h window.** If silent, investigate before any other work. Note: alerts are sent by backend via REST API in `alert_service.py`, not by a bot process. There is no Gateway connection to maintain.
- [ ] **No PR merges without Codex review** (auto-posted by Codex Cloud, or manually pasted as fallback — see `CLAUDE.md` §4).
- [ ] **`market_segment` is populated on every new `price_history` row.** `null_audit` returns zero NULLs.
- [ ] **Existing Pokemon Card Detail pages render correctly.** Any change touching `site.py`, `signal_service.py`, or `permissions.py` requires regression check on at least 3 sample assets across different sets.

---

## 2. Active backlog

Format:

```
### TASK-NNN — short title
**Priority:** P0 / P1 / P2
**Status:** ready / in_progress / blocked / needs_decision / needs_triage
**Owner:** Claude Code / Ivan / Claude Code + operator review
**Preconditions:** what must be true before starting
**Definition of Done:** what evidence proves completion
**Estimated effort:** XS / S / M / L / XL  (XS = 1 PR <100 LOC, XL = multi-PR week)
**Reference:** related docs/PRs/conversations
**Notes:** any caveats
```

---

### P0 — must do next

#### TASK-101 — YGO signal graduation verification

**Priority:** P0
**Status:** COMPLETE — 2026-05-17
**Owner:** Claude Code
**Preconditions:** all met

**Definition of Done — verified 2026-05-17:**
- ✅ Criterion 1 — non-INSUFFICIENT_DATA: 20/67 assets = 29.85% (borderline but `D_pass=true` per `/admin/diag/ygo-verify-26`). Source: CardMarket avg7/avg30 (3 days data).
- ✅ Criterion 2 — MOVE/WATCH signals: **4 MOVE + 3 WATCH** on YGO. Top movers: Stardust Dragon TOCH-EN050 +40%, Toon Bookmark TOCH-EN003 +23%, Destiny HERO - Destroyer Phoenix Enforcer POTE-EN100 +18%.
- ✅ Criterion 3 — Card Detail page: renders cleanly for POTE and TOCH assets.

**Evidence:** `/admin/diag/ygo-signal-context` — 2026-05-17T17:xx:00Z — `D_pass: true`, `top_20_by_delta` shows MOVE/WATCH entries.

**Known caveats (not blocking):**
- `baseline_n=2, current_n=1` on all signals — data is 3 days old, thin but real.
- Multi-product CardMarket name matching causes: (a) TOCH-EN050 Stardust Dragon showing twice (two asset rows for same card_number, both matching same CM product); (b) extreme negative IDLE deltas on cheap cards (different CM product editions pooling avg30 vs avg7). Both are accepted Phase 1 limitations per `cardmarket.py:90` comment. Disambiguation deferred to Phase 3.
- TASK-801 criterion 2 (≥1 YGO MOVE/WATCH) now met → TASK-801 precondition 2 is satisfied.

---

#### TASK-105 — `asset_signal_history` retention prune (Issue D Phase 2)

**Priority:** P0
**Status:** COMPLETE — deployed, Phase 1 + Phase 2 both verified 2026-05-17
**Blocked by:** ~~Phase 1 48h verification~~ — verified ✅
**Owner:** Claude Code (Phase 2 implementation) + Ivan (verification)

**Background:** `asset_signal_history` was growing ~387k rows/day before transition guard fix — DB at 3.3 GB total, history table 2.6 GB (79%), 5.8 M rows, ~174 MB/day growth (CLAUDE.md §7 Issue D). **Phase 1 (transition guard) deployed in commit `78bd30b` on 2026-05-06 19:58 +1000.** Phase 2 = retention DELETE for the pre-fix accumulation plus ongoing daily trim.

**Preconditions:**
- Phase 1 in production: `78bd30b` reachable from `origin/main` — ✅ confirmed.
- 48h post-deploy verification window closed (deploy ≈ 2026-05-06 09:58 UTC; window closed ≈ 2026-05-08 10:00 UTC).
- Operator runs `GET /admin/diag/signal-history-stats?days=7` and confirms **all three** gates from CLAUDE.md §7:
  1. `rows_written/day` dropped from ~387k toward transition rate (estimate: 4–20k/day)
  2. `repeat_pct` < 5% on the most recent days (transitions ≈ rows_written)
  3. DB total size growth rate dropped from ~174 MB/day to <10 MB/day (Railway → Postgres → Storage tab)

**Definition of Done:**
- New scheduler job `signal-history-prune` registered: interval trigger 24h, `_STARTUP_DELAY` entry, `next_run_time=None` (per CLAUDE.md §2 scheduler conventions).
- Job DELETEs `WHERE computed_at < NOW() - (RETENTION_DAYS || ' days')::INTERVAL`.
- `RETENTION_DAYS` env-configurable via `SIGNAL_HISTORY_RETENTION_DAYS`; default decided in packet (lean 90; tighter possible given pre-fix accumulation is mostly repeat-row garbage).
- Job writes `scheduler_run_log` on every run with `meta_json={rows_deleted, retention_days_applied, oldest_remaining_at}`.
- Job added to heartbeat `_monitored_jobs` list (CLAUDE.md §6 Lesson 9).
- 48h post-deploy: DB total size trends down toward steady-state (`RETENTION_DAYS × post-fix-daily-rate` rows). Confirm via `/admin/diag/signal-history-stats` and Railway storage tab.
- `/admin/diag/signal-history-stats` sentinel re-evaluated — remove if "48h verification of Issue D" purpose is satisfied.

**Estimated effort:** S (~2h, single PR, 2 commits — scheduler job + test).

**Reference:**
- CLAUDE.md §7 Issue D entry (still describes both phases as pending — needs sync once Phase 2 lands).
- Commit `78bd30b` (Phase 1).
- Diagnostic endpoint at `backend/app/backstage/routes.py:2302`.

**Verification 2026-05-17 — all Phase 1 gates pass:**
- Gate 1: `rows_written/day` = 1,034–1,586 (down from 387k) ✅
- Gate 2: `repeat_pct = 0%` on all days since Phase 1 deploy ✅
- Gate 3: DB growth rate effectively zero at current write rate ✅ (pending Railway storage tab confirmation by operator)
- Phase 2 `signal-history-prune` job: **already deployed and running** — `success=4` runs in last 2 days, `writes=0` (no rows older than 90-day retention yet; old garbage will be pruned by 2026-08-04 under default `SIGNAL_HISTORY_RETENTION_DAYS=90`).

**Remaining:** Operator to confirm Railway storage tab shows flat or declining disk usage. If pre-fix garbage needs faster cleanup, set `SIGNAL_HISTORY_RETENTION_DAYS=30` in Railway env vars.

**Notes:**
- `observation_match_logs` (127 MB, no purge) is a separate secondary concern — not part of TASK-105. Becomes urgent if eBay Browse API ingest is wired.

---

### P1 — should do this month

#### TASK-GATE4 — Enable RESOLVE_PREDICTIONS_ENABLED in Railway (Ivan action required)

**Priority:** P1
**Status:** blocked — Ivan action
**Owner:** Ivan
**Preconditions:** Gate 2 pass (B2 test predictions injected — ✅ done commit 96091bb)

**Action:** Set `RESOLVE_PREDICTIONS_ENABLED=true` in Railway backend env vars. This starts the Gate 4 observation window (7 days of resolve-predictions job running cleanly before Gate 5 check).

**Definition of Done:**
- `RESOLVE_PREDICTIONS_ENABLED=true` set in Railway
- `/admin/diag/pred-accuracy` returns non-empty resolved predictions after next sweep
- 7 days of `scheduler_run_log` `job_name='resolve-predictions'` showing `status='success'`

**Gate 5 check date:** ~2026-06-05 via `/admin/diag/gate5-chaos-rising`

**Notes:** Do NOT set this without explicit Ivan instruction — it changes production behavior (prediction resolution starts running, affecting calibration metrics).

---

#### TASK-GATE7 — Approve signal sort as default (Ivan review)

**Priority:** P1
**Status:** COMPLETE — deployed 2026-06-04 (commit 3b8dc10)
**Owner:** Ivan (decision) → Claude Code (1-line change)

**Gate 5 evidence (2026-06-04):** sv6 Twilight Masquerade: 9 MOVE + 24 WATCH. Top: Greninja ex +112%, Hearthflame Mask Ogerpon ex +30%.

**Change:** `DashboardPage.tsx:31` — `useState<SortKey>('change')` → `useState<SortKey>('signal')`

---

#### TASK-GATE9 — Public Calls soft launch (Ivan action required)

**Priority:** P1
**Status:** blocked — Ivan action after Gates 4–8 pass
**Owner:** Ivan
**Preconditions:**
- Gates 1–8 all pass (Gate 4 requires RESOLVE_PREDICTIONS_ENABLED; Gate 5 requires Chaos Rising data; Gates 6/7/8 per plan)
- Ivan has 4–6 public predictions ready to inject

**Actions:**
1. Set `PUBLIC_PREDICTIONS_ENABLED=true` in Railway
2. Use `POST /admin/trigger/inject-paper-prediction` to create 4–6 public predictions anchored to Destined Rivals (sv10, released 2026-05-30)
3. Announce soft launch

**Notes:**
- Destined Rivals (sv10) is the best available launch anchor — releases 2026-05-30. 21-day contamination window means first sv10 predictions should close ~2026-06-20.
- Do NOT set `PUBLIC_PREDICTIONS_ENABLED=true` without explicit Ivan instruction.

---

#### TASK-201 — YGO Tier 1 expansion to ~30 sets

**Priority:** P1
**Status:** blocked
**Owner:** Claude Code
**Preconditions:**
- TASK-101 completed (YGO signal graduation proven) — **BLOCKED**: TASK-101 is blocked on YGO price source
- YGO real-time sold-price source resolved (YGOPRODeck is static; expanding sets before this is solved only increases DB/scheduler load with no signal value)
- Stable production state with no scheduler red flags

**Definition of Done:**
- `YGO_PHASE2_SETS` expanded from 13 → ~30 sets, including at minimum:
  - All Quarter Century / 25th anniversary sets (Konami flagship for 2026)
  - Phantom Revenge (key rebound product mentioned in market research)
  - High-staple legacy sets relevant for tournament play
- ≥300 YGO assets in production
- Banlist trigger framework implemented (even if no banlist update during dev window) per `01_architecture_audit_tasks.md` TASK-010 Part 2
- 6-layer verification pass on new sets

**Estimated effort:** M
**Reference:** `backend/app/ingestion/ygo.py` `YGO_PHASE2_SETS`, doc `01_architecture_audit_tasks.md` TASK-010
**Notes:**
- **BLOCKED 2026-05-07 pending discovery test.** POTE/TOCH returned byte-identical prices across 14 days — but this may be set-specific (older low-velocity sets) or source-specific (YGOPRODeck doesn't refresh old sets). TASK-201 is NOT a known unlock — it might confirm the problem rather than solve it.
- **Required before TASK-201:** 7-day discovery test — poll 10 high-velocity 2024–2025 sets (LEDE, PHNI, AGOV, DUNE, INFO candidates) via `/admin/diag/price-variance`. Decision rule: ≥30% of assets show ≥2 distinct prices → proceed; otherwise → YGO is blocked on alternative price source.
- Use the existing PR #11 import guard pattern — bulk import only sets that exist in DB; never auto-import on schedule.

---

#### TASK-801 — YGO CardMarket seed expansion (Phase 2b)

**Priority:** P1
**Status:** COMPLETE — verified 2026-06-04
**Owner:** Claude Code + Ivan
**Preconditions:** all met ✅

**Definition of Done — verified 2026-06-04:**
- ✅ CardMarket product IDs resolved (catalog quote-escape bug fixed; all 8 confirmed matching)
- ✅ All 8 assets seeded via `/admin/trigger/seed-ygo-cardmarket-cards` — `created=8`
- ✅ 75 total YGO assets now in production (was 67)
- ✅ 7+ days `cardmarket_avg7` rows — data since 2026-05-14, 11,304+ rows
- ✅ Non-INSUFFICIENT_DATA signals on 3/8 cards: PHNI-EN057 MOVE +86%, RA01-EN000 MOVE +49%, LEDE-EN003 WATCH

**Seeded cards (actual names as stored):**

| card_number | name | rarity | avg7 at seed |
|---|---|---|---|
| PHNI-EN043 | Promethean Princess, Bestower of Flames | Ultra Rare | €4.32 |
| PHNI-EN057 | "Infernoble Arms - Durendal" | Secret Rare | €4.09 |
| LEDE-EN003 | Snake-Eye Ash | Super Rare | €1.75 |
| LEDE-EN034 | Snake-Eyes Flamberge Dragon | Secret Rare | €1.85 |
| AGOV-EN026 | Unchained Abomination | Secret Rare | €2.33 |
| AGOV-EN038 | Chaos Ruler, the Chaotic Magical Dragon | Super Rare | €3.08 |
| RA01-EN000 | Blue-Eyes White Dragon | QC Secret Rare | €9.06 |
| RA01-EN001 | Dark Magician | QC Secret Rare | €45.68 |

**Note:** "Infernoble Arms - Durendal" has literal quotes in the YGO card name. CM catalog was storing it double-escaped (`""name""`); fixed in cardmarket_catalog.py.

**Estimated effort:** S
**Reference:** Phase 2 plan `docs/superpowers/plans/2026-05-14-ygo-phase2-cardmarket.md` Task 7 (Step 7.1); CLAUDE.md §13

---

#### TASK-802 — YGO edition-aware asset model (ebay_web_sold Phase 2)

**Priority:** P2
**Status:** not_started
**Owner:** Claude Code + Ivan
**Preconditions:**
- `EBAY_WEB_SOLD_ENABLED=true` live for ≥7 days (signals validated)
- Pro launch complete

**Definition of Done:**
Per-edition asset rows for YGO — 1st Edition and Unlimited as separate `Asset` records. Required work:
- `assets.metadata` schema update: add `edition` field (`"1st"` | `"unlimited"` | `null`)
- Backfill existing YGO rows: `edition=null` (signals intent to resolve later)
- `ebay_web_sold` scraper: scrape 1st Ed and Unlimited separately into respective `asset_id` rows, remove the 1st-Edition query workaround (see ADR-001 §Update 2026-05-17)
- Signal engine: confirm independent delta computation per edition asset (no cross-edition blending)
- CardMarket alignment: investigate whether CM `avg7/30/1` data distinguishes editions; document conclusion
- Frontend card detail: edition indicator or tabs if both editions exist for same card+set
- i18n strings: `edition.first` / `edition.unlimited`

**Estimated effort:** L (schema + 3 ingest paths + UI)
**Origin:** ADR-001 §Update 2026-05-17. Workaround (`"1st Edition"` baked into query) must stay in place until this task ships.

---

#### TASK-202 — One Piece TCG integration research spike

**Priority:** P1
**Status:** complete
**Owner:** Claude Code (research) + Ivan (decision)
**Preconditions:**
- TASK-201 not blocked

**Definition of Done:**
- A design doc at `docs/strategy/05_onepiece_integration.md` covering:
  - Data source options: official Bandai (probably unavailable), TCGPlayer scraping rules, eBay-only path, community datasets like OPTCG.gg / limitlesstcg
  - Recommended source with cost/risk tradeoff
  - Mapping rules sketch (Manga Rare, Alternate Art, Set Code OP-13 etc.)
  - First 5 sets to seed (suggest OP01 Romance Dawn for vintage status, OP05 Awakening for liquidity, OP13/OP14 for chase appeal)
  - Estimated cost (eBay budget, any scraping infrastructure)
- Operator decides go/no-go before any code is written

**Estimated effort:** S (research only)
**Reference:** Strategy doc; market research notes that One Piece outsold Yu-Gi-Oh in Q4 2025 monthly volume
**Notes:** Do NOT start client code until operator approves the design doc. One Piece has no clean public API equivalent to YGOPRODeck, so source selection is more consequential.

---


---

#### TASK-204 — Image backfill retry audit

**Priority:** P1
**Status:** complete
**Owner:** Claude Code
**Preconditions:** None

**Definition of Done:**
- Answer recorded in `docs/plan-v3.md` B-3 section: does image backfill currently retry, where, and how often are cards left imageless?
- If answer is "no retry": a follow-up task created with scope estimate
- If answer is "retry exists": where it lives is documented

**Estimated effort:** S
**Reference:** `docs/plan-v3.md` §3 B-3 ("Image coverage & retry — needs audit")
**Notes:** Pure audit task, no code change. Output is documentation. Kept at P1 because imageless cards directly affect Card Detail page quality, which is a user-facing surface.

---

#### TASK-401 — Add OpenAI as third LLM provider for AI analysis

**Priority:** P1
**Status:** complete
**Owner:** Claude Code

**Background:** The codebase already runs Anthropic + Groq as dual LLM providers for signal explanation, mapping disambiguation, etc. Operator already purchased OpenAI API credits expecting to use them for PR review automation, but TASK-103b adopted Codex Cloud (Path C) instead — making the API key available for higher-value use.

This task adds OpenAI as a third provider to the existing LLM analysis pool. The three providers serve different roles based on their strengths:

- **Anthropic (Claude)**: long context, reasoning, natural-language explanations — signal explanation (user-facing copy)
- **Groq**: fast, cheap, high-throughput — mapping disambiguation (frequent, structured, low creativity needed)
- **OpenAI (gpt-4o-mini)**: strict JSON schema enforcement, function calling — structured tagging tasks (foundation for Phase 3 Cross-TCG Franchise Move detector)

**Preconditions:**
- OpenAI API key purchased (already done)
- TASK-103b in progress or done (so Codex Cloud is the review path; this task doesn't fight for the same key)

**Definition of Done:**
1. `backend/app/services/llm/` adds `OpenAIClient` matching the existing `AnthropicClient` / `GroqClient` interface
2. Provider router updated with explicit routing rules:
   - `signal_explanation` → Anthropic
   - `mapping_disambiguation` → Groq
   - `structured_tagging` (new task type) → OpenAI
   - Fallback chain: each task type has a primary + 1 fallback. Default fallback ordering documented.
3. `OPENAI_API_KEY` added to Railway env vars (backend service only)
4. **Operator action**: OpenAI dashboard sets monthly budget cap at $20 (hard limit, alert at $15)
5. **Small-scale IP tagging validation experiment**:
   - Sample 100 assets across Pokemon (60) + YGO (40) for diversity
   - Run through OpenAI with IP tagging prompt + JSON schema (FRANCHISE / CHARACTER / THEME / ARTIST)
   - Manually verify ~30 random outputs to estimate accuracy
   - Save results to `docs/audits/2026-XX-openai-ip-tagging-validation.md`
   - Target: >85% accuracy. If lower, document failure modes. Do NOT proceed to full batch.
6. TDD: provider failover test suite. Verify fallback is invoked when primary fails.
7. **Do not modify** existing signal_explanation / mapping paths. Pure additive change.
8. CLAUDE.md §2 updated: "Anthropic + Groq + OpenAI triple provider, with task-type routing"

**Estimated effort:** M
**Reference:** CLAUDE.md memory (Anthropic + Groq dual provider). `02_cross_tcg_signal_design.md` (IP tagging foundation for Phase 3)
**Notes:**
- The 100-sample experiment is a deliberate scope limit. Full 10K batch tagging is a Phase 3 task (~Q4 2026), not this one.
- Use OpenAI Batch API for the 100-sample run (50% cheaper than sync API, latency irrelevant for validation).
- If validation accuracy is <85%, file follow-up task TASK-402 ("iterate IP tagging prompt"), do NOT proceed to Phase 3 dependence on it.

---

### P1 — should do this month (continued)

#### TASK-606 — bulk-set-price-refresh failure logging gap

**Priority:** P1
**Status:** complete
**Owner:** Claude Code
**Preconditions:** None

**Symptom:** `bulk-set-price-refresh` runs at 16% error rate (4/25 runs in 24h as of 2026-05-04) with `status='error', errors=1, meta_json=null`. Root cause is unobservable because `meta_json` is never passed to `finish_run` — the field is entirely absent from the call in `_run_bulk_set_price_refresh()` (scheduler.py ~line 554), unlike every other scheduler job which passes `meta_json` on both success and failure paths.

**Definition of Done:**
1. Audit `_run_bulk_set_price_refresh()` — confirm `finish_run` call at line ~554 lacks `meta_json` on both success and failure paths
2. On success path: pass `meta_json` with `sets_processed`, `cards_processed`, `prices_recorded`
3. On exception path: pass `meta_json` with `error_type`, `error_message` (first 500 chars), `sets_completed_before_failure` counter
4. Unit test: simulate exception mid-loop → verify `finish_run` called with non-null `meta_json` containing `error_type`
5. Verify in production: next error run has non-null `meta_json` visible in `/admin/stats`
6. Codex review

**Estimated effort:** S (~2 hours)
**Reference:** `/admin/stats` PR #45 diagnosis 2026-05-04. Violates CLAUDE.md §3 invariant #2 (all scheduler jobs write run_log with status + meta_json).
**Notes:** Does not block Pro launch. Ship within 1 week — Pro launch user load will make silent bulk-refresh failures a data freshness risk.

---

### P2 — important but not urgent

#### TASK-205 — Dashboard structure audit vs. v3 spec

**Priority:** P2
**Status:** complete
**Owner:** Claude Code
**Preconditions:** None

**Definition of Done:**
- A short report (markdown, posted as a PR comment or saved to `docs/audits/`) comparing current dashboard module ordering against §3 A-1 of original v3 plan
- Specific gaps enumerated
- Operator decides whether to schedule fixes

**Estimated effort:** S
**Reference:** `docs/plan-v3.md` §3 A-1
**Notes:** Demoted from P1 to P2. Dashboard module ordering is unlikely to be the bottleneck on Pro conversion vs. Pro tier not existing at all. Revisit after Pro launches.

---

#### TASK-206 — Signals page Pro/Free hierarchy audit

**Priority:** P2
**Status:** complete
**Owner:** Claude Code
**Preconditions:** None

**Definition of Done:**
- An audit comparing current `signals_page` ProGate placements against `03_pricing_page_copy.md` Free vs Pro spec
- Either: (a) audit shows full match, mark v3 A-3 → Done in `plan-v3.md`, or (b) audit shows gaps, list them with size estimates

**Estimated effort:** S
**Reference:** `docs/plan-v3.md` §3 A-3
**Notes:** Demoted from P1 to P2. Will become relevant when TASK-203 (payment design) reaches CTA wiring step.

---

#### TASK-301 — Pro tier launch implementation

**Priority:** P1 — both blockers resolved, promoting now
**Status:** in_progress — PR #79 (checkout routing, webhook tier detection, 90-day grace cleanup job, sort gate) merged 2026-06-10 (29818d6 + 0d369ef). Remaining DoD: first real payment end-to-end, refund flow test, ≥10 paying Pro users — gated on GATE4/GATE9 (Ivan env flips) + LemonSqueezy live.
**Blocked by:** ~~TASK-102~~ (done) ~~TASK-203~~ (done)
**Owner:** Claude Code + Ivan
**Preconditions:**
- Database backups in place (TASK-102 done) ← last remaining blocker
- ~~Payment provider chosen and design doc approved~~ — done (LemonSqueezy, see ADR)
- ~~Pricing decided~~ — done (USD $12/mo standard, USD $9/mo Founders lifetime lock-in, first 100)

**Definition of Done:**
- `/pricing` page live with full feature comparison table from `03_pricing_page_copy.md`
- 5 CTA placements wired
- Stripe (or chosen provider) webhook handling implemented and tested
- 7-day free trial enforced
- First real payment processed end-to-end (operator's own card or trusted beta tester)
- Refund flow documented and tested
- At least 10 real paying Pro users within 30 days of launch

**Estimated effort:** XL
**Reference:** TASK-203 output; existing `permissions.py` framework
**Notes:** This is the single largest unlock in the 12-month roadmap. Do not rush.

---

#### TASK-303 — `start_run` outside try block hardening

**Priority:** P2
**Status:** complete (already implemented — audit confirmed 2026-05-12)
**Owner:** Claude Code
**Preconditions:** Re-evaluate condition triggered, per CLAUDE.md §7:
- (a) `scheduler_run_log` shows unexplained gaps >2h for any job, OR
- (b) production Postgres moves off Railway-internal, OR
- (c) a second scheduler job is added that cannot tolerate silent failure

**Definition of Done:**
- `start_run` wrapped in its own try/except with separate alerting path
- TDD: a unit test simulating `start_run` failure verifies that an alert is sent and the job either retries or surfaces clearly

**Estimated effort:** S
**Reference:** CLAUDE.md §7, PR #13 Codex Review Finding #3
**Notes:** Accepted tradeoff — only do this when the conditions above trigger.

---

#### TASK-304 — Pokemon coverage to full historical (~20,000 cards)

**Priority:** P2
**Status:** needs_decision
**Owner:** Ivan (decision) → Claude Code (execution)
**Preconditions:** Operator decides this is a priority over multi-TCG breadth

**Definition of Done:**
- Pokemon set list expanded to all major historical sets (~150 sets, ~20,000 cards)
- All cards have basic price coverage from `pokemon_tcg_api`
- eBay ingest scope updated accordingly
- Storage / cost impact assessed and acceptable

**Estimated effort:** L
**Notes:** "Nice to have" until there's user demand evidence (Pro users asking for vintage sets we don't cover).

---

#### TASK-305 — `/pricing` page i18n + Chinese localization

**Priority:** P2
**Status:** complete — 2026-06-10 (commit 086d756)
**Owner:** Claude Code
**Preconditions:** TASK-301 has at least produced the English `/pricing` page

**Definition of Done:**
- Chinese translation of `/pricing` page using existing i18n framework
- Translations match `03_pricing_page_copy.md` Chinese version
- Currency display switches to ¥ when locale is `zh`
- One end-to-end manual test in zh locale

**Estimated effort:** S
**Reference:** `03_pricing_page_copy.md` Chinese section, `plan-v3.md` I18N-1b
**Completion note (2026-06-10):** Shipped via inline `LOCALES` constant + `useState` toggle in `PricingPage.tsx`, **not** the existing i18n framework (single-page scope didn't justify wiring it in). zh prices use RMB (¥88/mo Plus, ¥218/mo Pro) per `03_pricing_page_copy.md`. dist rebuilt in same commit (§13). Deviation from DoD wording accepted — revisit if a second page needs zh.

---

#### TASK-306 — Evaluate replacing Discord alerts with Sentry / Healthchecks / email

**Priority:** P2
**Status:** complete
**Owner:** Claude Code
**Preconditions:** TASK-104 completed (Discord bot archived — done 2026-05-02).

**Definition of Done:**
- Evaluation written: should `alert_service.py`'s Discord REST API path be replaced by Sentry (errors) + Healthchecks.io (job heartbeat) + email (digest)?
- Comparison covers: cost, signal-to-noise, operator-on-mobile experience, vendor lock-in
- If replace: design doc + implementation as separate follow-up task
- If keep as is: formal "keep" decision recorded in `docs/decisions/2026-XX-discord-alerts.md`

**Estimated effort:** S (decision) or M (if implemented)
**Notes:** Discord REST API alerts work. Evaluate after Pro launch when alert volume might increase.

---

#### TASK-501 — Domain setup + codebase URL migration

**Priority:** P1
**Status:** needs_decision — operator must complete Cloudflare/Railway steps first
**Owner:** operator (steps 1–9) → Claude Code (step 10 code PR)

**Operator action items (no code):**
1. Register `flashcardplanet.com` on Cloudflare (~$10/yr). If taken, decide on alternative (.io / .app / .co).
2. Cloudflare Email Routing: `hello@flashcardplanet.com` → `ivancheng236@gmail.com`
3. Railway → Custom Domains → add `flashcardplanet.com` → apply DNS records in Cloudflare
4. Wait SSL propagation (~5–10 min). Verify: `curl -I https://flashcardplanet.com` returns 200.
5. Railway env var: set `APP_URL=https://flashcardplanet.com`
6. Google Cloud Console: add `https://flashcardplanet.com/auth/google/callback` as authorized redirect URI; remove old Railway URL.
7. Resend: verify `flashcardplanet.com` domain to unlock `hello@flashcardplanet.com` as sender.

**Claude Code action (step 10 — after operator confirms domain is live):**

Code PR (≤2 files, ~10 lines):
- `backend/app/services/market_digest.py:269` — default APP_URL fallback: `flashcard-planet.up.railway.app` → `flashcardplanet.com`
- `backend/app/email/resend_client.py:15` — FROM_ADDRESS: `onboarding@resend.dev` → `hello@flashcardplanet.com` (after Resend verification)

**Audit results (2026-05-04):** Everything else is env-var driven (`settings.app_url`). No CORS changes needed (frontend uses same-origin relative URLs). Auth flows, magic links, and email templates all use `{{ app_url }}` dynamically.

**Precondition for Claude Code PR:** operator says "domain is live + APP_URL set".

**Estimated effort:** XS (code PR after operator completes infra)
**Reference:** Conversation 2026-05-04 domain audit.

---

#### TASK-502 — Sealed product data model + ingest job

**Priority:** P1
**Status:** needs_decision (waiting on data source inventory + EBAY_APP_ID confirmation)
**Owner:** Claude Code + Ivan
**Preconditions:**
- Ivan runs `railway variables` to confirm `EBAY_APP_ID` and `EBAY_CERT_ID` are non-empty
- Ivan completes data source inventory (due 2026-05-17) confirming eBay Browse API as viable source
**Definition of Done:**
- `listing_snapshot` table created (migration)
- `AssetClass.SEALED` added to `enums.py` + all handling sites audited per CLAUDE.md §3 Lesson 13
- `product_type` nullable column on `Asset`
- `sealed_products.json` contains 20 manually curated products (name, ebay_search_query, product_type)
- `sealed_browse_client.py` fetches from-price for each product (NO reuse of `_is_single_card()` or `noise_filter.py`)
- New scheduler job writes to `listing_snapshot` + `scheduler_run_log` + `_monitored_jobs`
**Estimated effort:** S
**Reference:** CEO plan 2026-05-12, design doc sealed-pivot-design-20260510

---

#### TASK-503 — /sealed page (SealedPage.tsx)

**Priority:** P1
**Status:** blocked
**Blocked by:** TASK-502 (data model + ingest must exist first)
**Owner:** Claude Code
**Definition of Done:**
- New `/sealed` route in `main.tsx`
- `SealedPage.tsx` shows table: product name, from-price, 7-day change %, last-updated timestamp
- Reads from new `GET /api/v1/sealed/products` endpoint
- No signal badge in v1 (signal thresholds calibrated after 14 days of real data in TASK-504)
**Estimated effort:** S
**Reference:** CEO plan 2026-05-12, D11 decision

---

#### TASK-504 — sealed signal computation + threshold calibration

**Priority:** P2
**Status:** blocked
**Blocked by:** TASK-502 must be running for ≥14 days to collect from-price baseline
**Owner:** Claude Code
**Definition of Done:**
- `signal_service_sealed.py` computes from-price trend signal (BREAKOUT/MOVE/WATCH/IDLE/INSUFFICIENT_DATA)
- Thresholds calibrated against real from-price variance on 20 products
- `sweep_signals()` modified to filter `WHERE asset_class != 'SEALED'` (prevents overwrite)
- Sealed signals visible in `asset_signals` table
**Estimated effort:** S
**Reference:** CEO plan 2026-05-12, D13 decision (defer thresholds until real data)

**Data source decision (2026-05-13): Approach C scrapped.** All external sold-price sources evaluated (eBay Marketplace Insights — business gate; TCGPlayer — closed; 130point — no API; PriceCharting — paid, no historic sales). Approach B (eBay Browse API from-price trend) is the ceiling. No sold-price reference will be added. TASK-504 scope revised accordingly.

---

#### TASK-505 — Extend trial duration to 14 days

**Priority:** P1
**Status:** complete — verified 2026-05-17
**Owner:** Claude Code
**Definition of Done — verified 2026-05-17:**
- ✅ `trial.py:12` → `TRIAL_DURATION_DAYS = 14`
- ✅ `resend_client.py` subject → "Your 14-day Pro trial has started"
- ✅ `trial_started.html` → "Your 14-day Pro trial has started."
- ✅ `PricingPage.tsx` → 3 user-facing strings updated
- ✅ No "day-6" references in scheduler.py
- ✅ 9/9 tests pass (`tests/test_trial_14day.py`)
**Reference:** CEO plan 2026-05-12, D3 decision

---

#### TASK-506 — Disable trial auto-start until LemonSqueezy is wired

**Priority:** P1
**Status:** complete — verified 2026-05-17
**Owner:** Claude Code
**Definition of Done — verified 2026-05-17:**
- ✅ `config.py:110` → `trial_auto_start: bool = False`
- ✅ `google_oauth.py:69` gated: `if settings.trial_auto_start`
- ✅ `magic_link.py:55` gated: `if settings.trial_auto_start`
- ✅ 9/9 tests pass (shared test file with TASK-505)
- Set `TRIAL_AUTO_START=1` in Railway when LemonSqueezy is wired
**Reference:** CEO plan 2026-05-12, D1 decision

---

#### TASK-507 — Sealed ingest scheduler observability

**Priority:** P1
**Status:** complete — verified 2026-05-17
**Owner:** Claude Code
**Definition of Done — verified 2026-05-17:**
- ✅ `scheduler_run_log` confirmed: `run_count_24h=10, status=success, records_written=20` per run, `meta_json={products_total:20, products_failed:0, snapshots_written:20}`
- ✅ `JOB_SEALED_INGEST` added to `_tracked_jobs` in admin/stats (commit 6c3a9b2 — visible in admin/stats scheduler.jobs section)
- ✅ `JOB_SEALED_INGEST` in heartbeat `_monitored_jobs` — silence alert fires if >25h gap
- ✅ `JOB_SEALED_INGEST` in `_zero_output_monitored` — zero-output alert if all runs write 0

---

#### TASK-508 — Sealed listings count display

**Priority:** P2
**Status:** needs_decision
**Owner:** Claude Code (implementation) + Ivan (product call)
**Preconditions:** TASK-502 merged; first sealed ingest run completed
**Context:** Current implementation shows "50" in the listings column for products that saturate eBay Browse API's 50-result cap. 19/20 products are expected to hit this cap, making the column uniformly uninformative and misleading (implies exactly 50 listings when the true count is ≥50).
**Options:**
- (a) Raise Browse API `limit` to 200 — more data, minor cost in API latency per product
- (b) Show "50+" for capped products (`listing_count >= 50`) — one-line UI change, honest about saturation
- (c) Remove the column — cleanest, loses any liquidity signal
- (d) Replace with tiered liquidity indicator: "Deep" (≥50), "Moderate" (10–49), "Shallow" (<10)
**Recommendation:** Option (b) as immediate one-line fix while gathering real data, revisit with option (d) after 30 days of ingest data.
**Definition of Done (option b):** `SealedPage.tsx` renders "50+" when `listing_count >= 50`, plain number otherwise.
**Estimated effort:** XS
**Reference:** PR #13 review (scoped out — sealed-feature decision, not Phase 1 rebuild scope)
**Notes:** Not in scope for PR #13. Decision depends on product direction for liquidity display.

---

### needs_triage (proposed by Claude Code or operator, not yet prioritized)

#### BL-1 — Extend `_get_json` retry schedule (resilience, key-independent)
**Proposed:** 2026-06-05 (TASK-80Y root cause audit)
**Status:** complete — 2026-06-10 (commit f4b56d0; MAX_FETCH_ATTEMPTS extended to 5-attempt schedule in pokemon_tcg.py)
**Why:** A single 429 or transient network blip currently kills the entire bulk-refresh job (`sets_completed_before_failure=0`, job dies at `dur=8-15s`). Three retries with delays `[2.0, 5.0, 15.0]` don't survive a Cloudflare throttle window where `Retry-After` is absent or small. This fragility is independent of the throttling root cause (now resolved by API key) — even on the authenticated tier, a transient failure should not be fatal.
**What:** In `import_pokemon_cards.py` `_get_json`, extend `cap_and_backoff` fallback delays from `[2.0, 5.0, 15.0]` (3 attempts) to `[2.0, 5.0, 15.0, 30.0, 60.0]` (5 attempts). Note: `MAX_FETCH_ATTEMPTS` is imported from `pokemon_tcg.py` — update the constant there, not in the script.
**Do NOT add inter-set pacing** — pacing was for the per-IP throttling problem, which the API key solved. Pacing is no longer needed and would slow down a job that now runs comfortably under the 250/min per-key limit.
**Effort:** XS (2 lines + test)

#### BL-2 — Monitor shared-key quota headroom (long-horizon)
**Proposed:** 2026-06-05 (TASK-80Y root cause audit)
**Status:** needs_triage
**Why:** `scheduled-ingestion` and `bulk-set-price-refresh` now share the same `POKEMON_TCG_API_KEY` → they share the 250/min per-key budget. Fine now (~30-35 req bulk + ~1 req/hr per-card ingestion ≪ 250/min), but as set count grows the ceiling could be approached.
**Trigger condition (no action before this):** combined per-minute request count nears 200 (80% of 250). Observable via Railway logs or a per-job request counter.
**No code change now.** Action when triggered: register a second API key or stagger the two jobs' startup offsets so they don't burst simultaneously.

#### TASK-509 — Mobile hamburger nav drawer (PR #15 scope)

**Priority:** P1 within PR #15
**Status:** deferred — implement in PR #15, not before
**Proposed:** 2026-05-13 (PR #13 diagnostic finding)
**Context:** At viewports ≤640px the NavBar overflows its visible area. PR #13 chose Option C — allow horizontal scroll within the nav-links container (`overflow-x: auto`, hidden scrollbar) while keeping the page body non-scrolling. This is functional but suboptimal UX: mobile users must discover horizontal swipe to reach Watchlist and Alerts. A hamburger drawer is the correct pattern.
**Trigger for PR #15:** The shadcn `Sheet` or `Dialog` primitive (required for a proper drawer) lands in PR #15's shadcn/ui adoption. Implement this task immediately after that primitive is available.
**Scope:** Below a ~640px breakpoint, replace the scrollable nav-links strip with a hamburger icon button. Tap opens a shadcn Sheet anchored left/right containing all nav items (Market, Sealed, Watchlist, Alerts + auth). Hamburger replaces the current `overflow-x: auto` on `.nav-links` at that breakpoint.
**Design note:** Option B (shrink nav items to fit via smaller font/tighter padding) was considered and rejected — it would pollute the design system's type scale and padding tokens before the Tailwind migration in PR #15 establishes them as the source of truth. Option C was chosen as the interim solution.
**Reference:** PR #13 (feat/pr-13-critical-bug-fixes) — commit documenting decision; PR #15 spec §2.1 (shadcn adoption).

---

#### TASK-T01 — YGO image retry path
**Proposed:** 2026-05-02 (TASK-204 audit finding)
`_query_missing_image()` only covers `game='pokemon'`. YGO assets that lack images have no retry path. ~20 LOC fix in `pokemon_tcg.py` + `ygo.py`. Not urgent (67 YGO assets today), but needed before YGO expansion to 300+ assets (TASK-201).

#### TASK-T02 — Add failed_backfill_queue count to diagnostics
**Proposed:** 2026-05-02 (TASK-204 audit finding)
`failed_backfill_queue` permanent failure count is not visible in any admin endpoint. Add to next diagnostic endpoint PR alongside TASK-301 diag work.

#### TASK-T03 — Frontend a11y deferred items (WCAG 2.1 AA)
**Proposed:** 2026-05-08 (frontend WCAG audit; quick wins shipped on `fix/a11y-quick-wins`).
**Quick wins shipped:** `nav-logo-sub` contrast (1.4.3), aria-labels on FilterDrawer/WatchlistPage form controls (3.3.2), keyboard activation for NavBar nav-link spans (2.1.1).

**Deferred items, each warrants its own PR:**

1. **Modal accessibility** — ✅ **COMPLETE 2026-06-10 (PR #80).** On re-verification, 6 of 7 requirements (`role="dialog"`, `aria-modal="true"`, `aria-labelledby`, focus trap, Escape-close, focus restoration via `useFocusTrap`, backdrop click-to-close) were already shipped on all three surfaces — only **scroll lock** was missing. PR #80 added the reference-counted `useScrollLock` hook + wired it into all three + test coverage (5 `useScrollLock` cases, 2 `useFocusTrap` regression cases). WCAG 4.1.2, 2.4.3 met. Note: implemented as two focused hooks (`useFocusTrap` + `useScrollLock`), not a single `useDialog()` wrapper — the wrapper/`<Dialog>` pattern-promotion idea was not needed.

2. **GameSwitcher dropdown items** — ✅ **COMPLETE 2026-06-11 (PR #81).** "Coming soon" `<div>` entries → `<button disabled aria-label="<Game> — coming soon">`; added `aria-haspopup` + `aria-expanded` to the toggle. WCAG 2.1.1, 4.1.2. Test coverage added.

3. **Skip link** — ⏳ **DEFERRED — needs arch decision (own PR).** No shared layout exists (each page self-renders NavBar + content), so a correct `#main-content` landmark requires either a `<Layout>` wrapper refactor across 13 routes or per-page `id="main-content"` additions. The `.sr-only` utility it needs was added to `theme.css` in PR #81. WCAG 2.4.1. **Decision for Ivan:** introduce a shared `<Layout>`, or per-page id?

4. **Live regions** — ✅ **COMPLETE 2026-06-11 (PR #81).** NavBar unread badge → `aria-live="polite"` + descriptive `aria-label`; `DigestPreferencesPage` save state → sr-only `role="status" aria-live="polite"` region. WCAG 4.1.3. Known limitation: NavBar badge only renders when `unreadCount > 0`, so the 0→1 transition's announcement isn't guaranteed across all SRs (a persistent region would fix it — minor, deferred).

5. **Heading hierarchy** — ✅ **COMPLETE 2026-06-11 (PR #81).** `ComparePage` title `<div>` → `<h1>` (`margin:0` preserves layout). WCAG 1.3.1, 2.4.6. Note: no other non-semantic page titles found needing the sweep at this time.

6. **Link/button semantics** — ⏭️ **MOOT (verified 2026-06-11).** Audit cited `PlusUpgradeModal.tsx:35 <a href="/#plus">` as a button-action-as-link; current code is a legitimate `<a href="/pricing">` link to a real route. No defect. WCAG 4.1.2.

**Triage criteria:** All items resolved except item 3 (skip link), which is the only one left and needs an arch decision. Items 1/2/4/5 shipped (PRs #80, #81); item 6 was moot.

**Audit report archived in:** session transcript 2026-05-08; `frontend/src/styles/theme.css` history reflects the design-system fixes that preceded this audit.

#### TASK-301e2 — Market Digest Section 2: Personalised watchlist movers
**Proposed:** 2026-05-03
**Status:** deferred — do not start without operator approval
**Trigger:** User-reported demand for cross-device watchlist sync
**Depends on:** Server-side watchlist persistence decision (see anti-task above)
**Context:** TASK-301e ships digest with global BREAKOUTs only. Section 2
(watchlist movers) requires server-side knowledge of each user's watchlist,
which is currently localStorage-only. This task picks up when a Plus subscriber
explicitly reports needing cross-device watchlist sync.

#### TASK-701 — Deep Analysis (Pro hero, post-launch)
**Proposed:** 2026-05-04
**Status:** deferred — do not start until Pro launch + ≥10 paying Pro users
**ADR reference:** ADR-06v3 §F-23

Differentiation from Plus Card Detail AI Analysis (TASK-301e):

| Dimension | Plus AI Analysis (current) | Pro Deep Analysis (TASK-701) |
|---|---|---|
| Length | 1–2 sentences | 4–6 paragraphs structured |
| Content | Data restatement + simple observation | Drivers / Historical pattern / Operational thesis / Risks |
| External lookup | None | Web search (Reddit / Twitter / official news) |
| Historical matching | None | Similar (liquidity + price movement) combos in DB |
| Actionable guidance | No | "hold" / "wait" / "exit" with explicit reasoning |
| Risk quantification | No | Yes |
| Cost | ~$0.005/call (cached aggressively) | ~$0.30/call |
| Rate limit | N/A | 5 calls/day per Pro user |
| Cache strategy | Shared by (card, signal_label) 24h | Per (asset, date) 24h per user |

**Why the distinction matters for pricing:**
Plus AI Analysis is a convenience feature — it saves the user from pasting data into ChatGPT themselves. Pro Deep Analysis is a capability gap — web search + historical pattern matching is structurally impossible to replicate with ChatGPT alone on public TCG data. This is where the Pro $30/month price point is justified.

**Implementation notes (when ready):**
- New endpoint: `POST /api/v1/predict/deep` (Pro-gated, rate-limited via `llm_request_log` table)
- Provider: Anthropic with `web_search_20250305` tool enabled (TASK-401 router)
- Structured output schema: `{ drivers, historical_pattern, thesis, risks, guidance }`
- `guidance.action` must be one of `hold | wait | exit | accumulate` — no `buy` language
- Daily counter resets UTC 00:00; persisted in `llm_request_log` with `task_type='deep_analysis'`
- Cost monitoring: alert if daily Deep Analysis spend > $15 (50 users × 5 calls × $0.30 = $75/day max; alert at 20%)
- Response time: 15–30s acceptable (stream to frontend)
- Precondition: `llm_request_log` table must exist (TASK-604 or equivalent)

#### TASK-T04 — Create DESIGN.md (design system source of truth)
**Proposed:** 2026-05-12 (plan-design-review finding)
**Status:** needs_triage
**Why:** The gold token system, component class hierarchy (.badge-*, .btn-*, .surface-*), dark-only decision, and the tierBadge pattern are scattered across `theme.css`, plan files, and audit notes. No single document exists for future design decisions to calibrate against. Every design review starts by grepping `theme.css` to reconstruct the system.
**What:** Write `DESIGN.md` covering: colour semantics (signal palette vs severity palette vs gold/plus accent), typography scale, component class hierarchy with when-to-use guidance, dark-only rationale, tierBadge pattern and its planned evolution to CSS classes.
**Effort:** S (1–2h to write). Zero code changes.
**Depends on:** Nothing. Can be written anytime.

#### TASK-T06 — Delete stale /admin/diag/ingestion-history endpoint
**Proposed:** 2026-05-12 (plan-devex-review finding)
**Status:** needs_triage
**Why:** `backend/app/backstage/routes.py` `admin_diag_ingestion_history()` has hardcoded timestamps `BETWEEN '2026-04-23 11:30'::timestamptz AND '2026-04-23 14:30'::timestamptz` from the 2026-04-23 crash loop incident. The incident is resolved; the endpoint silently returns empty/stale results for any current diagnostic query. Per CLAUDE.md §4, diagnostic endpoints must have a removal condition — this one's condition passed months ago.
**What:** Delete the `@router.get("/diag/ingestion-history")` route and its function body from `backend/app/backstage/routes.py`. No other code references it.
**Effort:** XS (delete ~30 lines). Zero risk.
**Depends on:** Nothing.

#### TASK-T07 — Add health_warnings to /admin/stats + /admin/diagnostics/json endpoint
**Proposed:** 2026-05-12 (plan-devex-review finding)
**Status:** needs_triage
**Why:** (1) `/admin/stats` shows `records_written: 0, status: success` for zero-output jobs with no explicit warning. The only signal is Discord webhook — if Discord is down, Ivan has no API-accessible health warning. (2) `/admin/diagnostics` returns HTML only, blocking `railway run curl ... | jq` workflows. Both gaps make production diagnosis slower.
**What:**
- In `admin_stats()`: call `get_zero_output_jobs(db, ...)` (already exists in `scheduler.py`) and append results to a `health_warnings: list[str]` field. Omit the field when empty.
- Add `@router.get("/diagnostics/json")` that calls `build_standardized_diagnostics_summary(db)` and returns it as JSON (same dict, no HTML render).
**Effort:** S (1-2h). No schema migration. Uses existing functions.
**Depends on:** Nothing.

#### TASK-T08 — Add operational quick reference to docs/DEV_NOTES.md
**Proposed:** 2026-05-12 (plan-devex-review finding)
**Status:** needs_triage
**Why:** No documented pattern for "how do I check if production is healthy from the terminal?" CLAUDE.md §2.5 covers Railway CLI generally but doesn't show the specific `railway run bash -c 'curl $APP_URL/admin/stats ...'` pattern that Ivan uses for health checks.
**What:** Add a 10-15 line "Operational health check" section to `docs/DEV_NOTES.md` with: base URL pattern, the `/admin/stats` curl command, and 3-5 key diagnostic jq paths.
**Effort:** XS (<30 min).
**Depends on:** Nothing.

#### TASK-T05 — Migrate tierBadge() to CSS classes (.badge-pro, .badge-plus)
**Proposed:** 2026-05-12 (plan-design-review finding)
**Status:** needs_triage
**Why:** Task 1 of the pattern-promotion plan (`.badge-gold`) deliberately excludes NavBar because the `tierBadge()` helper returns two colour-family variants (gold for PRO, violet for PLUS). Completing the badge-gold migration requires separate CSS classes for each tier so `tierBadge()` can return `className` instead of inline style properties.
**What:** Add `.badge-pro` (gold palette, same as `.badge-gold`) and `.badge-plus` (violet palette: `var(--plus)`, `var(--plus-glow)`, `var(--border-plus-soft)`) to `theme.css`. Update `tierBadge()` to return `{ className: string; label: string }` instead of `TierBadgeStyle`. Update `NavBar.tsx` to use `className={badge.className}`.
**Effort:** S (1h). Unblocked once pattern-promotion Task 1 is merged.
**Depends on:** Pattern-promotion Task 1 (`.badge-gold` class added to `theme.css`).

#### TASK-202b — OP13 data source gap (One Piece)
**Proposed:** 2026-05-04 (TASK-202 spike finding)
**Status:** deferred — do not start without operator approval
**Trigger:** optcgapi.com still has no OP13 coverage 30 days after `ONEPIECE_INGEST_ENABLED=true` **and** Plus/Pro users report missing OP13 cards.
**Options (decide at trigger time, not now):**
- Wait for optcgapi.com to add OP13 (passive)
- Test tcgapi.dev free tier for OP13 coverage
- Accelerate Phase 2: tcgapi.dev Pro ($49.99/mo) — standard Phase 2 trigger is ARR ≥ $5K
**Context:** OP01–OP12 covered by optcgapi.com. OP13 returns `not_found_in_source` per run — expected, not an error. See `docs/strategy/05_onepiece_integration.md` §2 and `docs/superpowers/specs/2026-05-04-onepiece-integration-design.md`.

---

### Observations (not tasks — monitor only)

#### OBS-2026-05-04 — ingestion 24h failure rate elevated

`ingestion` job: `runs_24h=25, fails_24h=12` (~40% failure rate). Historical normal range 10–25%. 40% is yellow-zone top.

**Candidate causes:** Pokemon TCG API 429 rate limit storm; scheduler load from TASK-301e deploy; API upstream change; rate limit config drift.

**Action:** No task opened. Track daily via `/admin/stats` `ingestion.failure_count_24h` for 7 days.
- If stays >35% → escalate to P1 task
- If drops to <25% → transient, close observation

---

## 3. Completed (last 30 days)

When a task ships, move it here with PR number and merge date. Keep this section trimmed to the last 30 days; older items move to `docs/backlog-archive/<year>-<month>.md` quarterly.

| TASK | Title | PR | Merged | Outcome |
|---|---|---|---|---|
| TASK-301 (PR #79) | Pro tier payment-gap fixes | PR #79 (29818d6 + 0d369ef) | 2026-06-10 | Pro checkout routing, webhook tier detection, 90-day grace cleanup job, backend Pro-only sort gate. Subset of TASK-301 DoD — umbrella task stays in_progress (first real payment + ≥10 paying users not yet met). |
| TASK-305 | /pricing zh/en language toggle | commit 086d756 | 2026-06-10 | Inline LOCALES + useState toggle on PricingPage.tsx (no i18n framework). zh RMB pricing (¥88 Plus, ¥218 Pro). dist rebuilt same commit. |
| BL-1 | Pokemon TCG API retry 3→5 attempts | commit f4b56d0 | 2026-06-10 | MAX_FETCH_ATTEMPTS extended to [2.0,5.0,15.0,30.0,60.0] in pokemon_tcg.py. Survives longer Cloudflare throttle windows. No inter-set pacing added (key solved per-IP throttling). |
| TASK-GATE7 | Default sort → signal | commit 3b8dc10 | 2026-06-04 | Gate 5 pass (sv6 9 MOVE + 24 WATCH, Greninja ex +112%). DashboardPage.tsx:31 'change' → 'signal'. |
| TASK-801 | YGO CardMarket seed expansion (Phase 2b) | — | 2026-06-04 | 8/8 seeded cards have signals. PHNI-EN057 MOVE +86%, RA01-EN000 MOVE +49%, LEDE-EN003 WATCH. CardMarket data: 11,304+ rows since 2026-05-14. |
| FE-6 | Card Detail driver attribution + fundamental delta panel | commit 39c148b | 2026-05-29 | Driver type, confidence %, event description, fundamental delta, hype premium shown on card detail when driver != UNKNOWN. |
| FE-5 | INVESTMENT signal filter (BREAKOUT+MOVE shortcut) | commit 6348690 | 2026-05-29 | Frontend filter chip + backend `IN ('BREAKOUT','MOVE')` SQL; `signal` sort CASE WHEN ordering added. |
| FE-2 | Signal sort (BREAKOUT-first ordering) | commit 6348690 | 2026-05-29 | Sort button + CASE WHEN ORDER BY on backend; default remains `change` until Gate 7 approved. |
| FE-1 | Landing page live calibration metrics | commit 05bcba3 | 2026-05-29 | Brier score + honest-n pre-cal warning live on landing; waitlist form removed; pricing CTA added. |
| Gate 3 fix | normalize naive captured_at to UTC in fundamental_signal_service | commit 6834b64 | 2026-05-29 | Added `_to_utc()` helper; fixed naive vs tz-aware comparison bug; fixed vacuous-true gate3_pass. |
| Gate 6 | /methodology page live | commit 1cf152a + 545ec20 + d509f1c | 2026-05-28 | MethodologyPage.tsx at /methodology — signal engine methodology, dual-window algorithm, edge cases. |
| Admin | POST /admin/trigger/inject-paper-prediction endpoint | commit a4c719f | 2026-05-28 | Allows operator to inject paper predictions via admin API for Gate 2/4 seeding. |
| Admin | /diag/gate3-fundamental + /diag/pred-accuracy sanity endpoints | commit beb8def | 2026-05-28 | Gate 3 diagnostic samples 20 assets for fundamental signal computation; pred-accuracy endpoint for gate verification. |
| Admin | /diag/gate5-chaos-rising endpoint | commit 5456e50 | 2026-05-28 | Checks Chaos Rising (sv6) assets for price variance after TIER1 reorder; target ~2026-06-05. |
| Ingest | sv6/sv6pt5/sv7 added to TIER1_BULK_SET_IDS + reordered newest-first | commit 205c388 + 8a567c4 | 2026-05-28 | Chaos Rising, Stellar Crown, Stellar Miracle added; bulk refresh now prioritizes newest sets. |
| Signal display | Dollar + percentage delta across all card surfaces | commit f530947 | 2026-05-28 | `formatDeltaDisplay(deltaAbs, deltaPct)` helper; suppression rule: |delta| < $0.50 → dollar only; `price_delta_abs` added to API response schema. |
| FE-3 | 3-tier pricing page + landing hero grammar | commit 7290106 | 2026-05-28 | Free/$9.99/$24.99 tiers on PricingPage; signal intelligence terminal copy on landing. |
| Scheduler | resolve-predictions writes scheduler_run_log on kill-switch path | commit 8b510f0 | 2026-05-28 | Unconditional start_run + finish_run on kill-switch path in resolve-predictions job. |
| 12-month roadmap | Product roadmap + Public Calls track design | commit 69cf06b + efc711a | 2026-05-28 | 9-gate plan for Public Calls soft launch; 4-phase 12-month roadmap. |
| TASK-507 | Sealed ingest observability | commit 6c3a9b2 | 2026-05-17 | sealed-ingest: run_count_24h=10, status=success, written=20/run. In _tracked_jobs, _monitored_jobs, _zero_output_monitored. |
| TASK-505 | Extend trial to 14 days | tests/test_trial_14day.py | 2026-05-17 | All 5 propagation sites verified (trial.py, resend_client.py, trial_started.html, PricingPage.tsx). 9/9 tests pass. No day-6 refs in scheduler. |
| TASK-506 | Disable trial auto-start until LemonSqueezy | config.py + oauth gates | 2026-05-17 | `trial_auto_start: bool = False` in Settings; both google_oauth.py and magic_link.py gated. 9/9 tests pass. |
| — | Fix digest MOVE ordering noise + display cap on extreme deltas | PR fix/digest-move-ordering | 2026-05-16 | Re-ordered MOVE candidates by signal_score DESC (was ABS(price_delta_pct)); capped triple-digit deltas to ▲+100%+ / ▼-100%+ in email template. 43 tests pass. |
| TASK-T06 | Delete stale /admin/diag/ingestion-history | commit 2176d0f | 2026-05-12 | Deleted 30-line endpoint with hardcoded 2026-04-23 timestamps. |
| TASK-T07 | health_warnings in /admin/stats + /admin/diagnostics/json | commit 2176d0f | 2026-05-12 | Added health_warnings[] to /admin/stats (calls get_zero_output_jobs). Added /admin/diagnostics/json JSON endpoint. |
| TASK-T08 | Operational quick reference in DEV_NOTES.md | commit 2176d0f | 2026-05-12 | Added 6-command "Operational health check" section to docs/DEV_NOTES.md. |
| TASK-303 | start_run try/except hardening | already done | 2026-05-12 | Audit confirmed: all 9 scheduler jobs including signal-history-prune already have start_run wrapped in try/except with send_discord_alert. No change needed. |
| TASK-205 | Dashboard structure audit vs. v3 spec A-1 | docs/audits/2026-05-12-dashboard-signals-audit.md | 2026-05-12 | Design intent met. SPA filter/sort covers all 5 v3 modules. Volume/Recent sort gating deferred to TASK-301. |
| TASK-206 | Signals page Pro/Free hierarchy audit | docs/audits/2026-05-12-dashboard-signals-audit.md | 2026-05-12 | signals_page (Python) replaced by SPA. 3 gates open (testing phase): confidence, AI analysis, volume/recent sort. All tracked in TASK-301 via CLAUDE.md §12. |
| TASK-306 | Discord alerts evaluation | docs/decisions/2026-05-12-discord-alerts-keep.md | 2026-05-12 | Decision: keep Discord REST API. Sentry/Healthchecks/email rejected. health_warnings on /admin/stats reduces alert fatigue without new tooling. |
| TASK-101 | YGO signal graduation verification | BLOCKED — see active backlog | 2026-05-07 | Attempted 2026-05-07. Criteria 1 (IDLE state) and 3 (Card Detail renders) met. Criterion 2 (BREAKOUT/MOVE/WATCH) structurally unreachable: YGOPRODeck returns static prices, delta=0 on all 67 assets across 14 days. TASK-201 also blocked. Root: no real-time YGO sold-price source exists. |
| TASK-606 | bulk-set-price-refresh failure logging gap | commits (scheduler.py + test) | 2026-05-07 | Added meta_json to finish_run on both success path (sets_processed, cards_processed, prices_recorded) and exception path (error_type, error_message[:500], sets_completed_before_failure). 1 new test; 7/7 pass. |
| TASK-606 (PR) | bulk-set-price-refresh failure logging gap | PR #45 (admin stats) | 2026-05-04 | PR #45 exposed: meta_json never passed to finish_run. TASK-606 opened as P1 ready for fix. |
| TASK-202 | One Piece TCG integration research spike | (research only) | 2026-05-04 | Design doc at docs/strategy/05_onepiece_integration.md. Recommended: optcgapi.com (free Phase 1) → tcgapi.dev Pro ($49.99/mo Phase 2). eBay Browse API via existing integration. First 5 sets: OP01, OP05, OP08, OP09, OP13. Operator go/no-go required. |
| TASK-103a | Codex CLI CI feasibility research | (research only) | 2026-05-02 | Codex CLI is headless-capable; ChatGPT OAuth blocks GitHub Secret storage; Path C (Codex Cloud) chosen. Report at `docs/audits/2026-05-02-codex-ci-feasibility.md` |
| TASK-104 | Archive Discord bot, simplify product boundary | commit e09c100 | 2026-05-02 | bot/ archived to archive/discord-bot-2026/. OAuth routes removed. 845 tests pass. |
| TASK-302 | Pro tier waitlist form | commit ef6f7e3 | 2026-05-02 | POST /api/v1/waitlist + admin diag + landing page form. 851 tests pass. Requires migration 0029 on prod. |
| TASK-103b | PR review via Codex Cloud (Path C) | commit 47b3c63 | 2026-05-02 | AGENTS.md written. CLAUDE.md §4 updated. Operator enables Codex Cloud in chatgpt.com settings. |
| TASK-401 | OpenAI as third LLM provider | commit 9dafe11 | 2026-05-02 | OpenAIProvider + task-type router + FallbackLLMProvider + IP tagging experiment. 861 tests pass. |
| TASK-203 | Pro tier payment integration design doc | commit f1ee749 | 2026-05-02 | Design doc + 6-decision ADR. LemonSqueezy MoR, USD $12/$9 Founders, card-free 7d trial. TASK-301 now blocked only on TASK-102 (backups). |
| TASK-204 | Image backfill retry audit | (audit only) | 2026-05-02 | Two-layer retry exists (backfill_pass + retry_pass). ~0% imageless rate for Pokemon. Gap: YGO has no image retry path. See docs/audits/2026-05-02-image-backfill.md |
| TASK-102a | Daily pg_dump backup via GitHub Actions | commit a9c5cfb | 2026-05-02 | Workflow live, 11+ consecutive daily runs. Restore runbook rewritten against GitHub Releases (PR #14a). First restore drill: PR #14a D4. |
| TASK-102b | Quarterly local backup download script | commit c1dc319 | 2026-05-02 | backend/scripts/backup_to_local.sh + quarterly-backup.md. Add quarterly reminder to Google Calendar. |

---

## 4. Decisions log (deferred items needing operator input)

When a task is `needs_decision`, log here:

| Date raised | Question | Status | Resolution date | Resolution |
|---|---|---|---|---|
| 2026-05-02 | Database backup: Railway Pro vs external dump vs hybrid? (TASK-102) | **resolved** | 2026-05-02 | **Free-tier hybrid**: GitHub Actions daily → private Releases (102a) + quarterly manual local download (102b). Re-evaluate at Pro users ≥ 10. |
| 2026-05-02 | Pro tier payment provider, pricing, trial, refund, data retention, launch sequence (TASK-203) | **resolved** | 2026-05-02 | See `docs/decisions/2026-05-02-pro-launch-parameters.md`. LS MoR, USD $12/$9 Founders, card-free 7d trial, 14d self-service refund, 90d grace, waitlist-48h-then-public. |
| 2026-05-02 | Pokemon full historical coverage vs multi-TCG breadth — which gets resources first after Pro launches? (TASK-304) | open | — | — |
| 2026-05-02 | Discord bot 24-hour deployment vs archive? | **resolved** | 2026-05-02 | **Archive.** Zero users on slash commands, web is the product, REST API alerts stay. See TASK-104. |
| 2026-05-02 | Codex CLI in CI: feasible or use alternative? | **resolved** | 2026-05-02 | **Path C: Codex Cloud auto-reviews.** Free with ChatGPT subscription. Path A (API key + custom Action) is an anti-task. See TASK-103b. |
| 2026-05-02 | OpenAI API key: use for PR review automation or LLM analysis pool? | **resolved** | 2026-05-02 | **LLM analysis pool (TASK-401).** PR review goes via Codex Cloud (free with subscription). API key produces direct product value via IP tagging foundation. |

---

## 5. Anti-tasks (things we explicitly do NOT do)

Listed to prevent re-litigation:

- **Self-hosted marketplace** — out of scope (`plan-v3.md` §4)
- **Sports cards** — explicitly off-limits (Card Ladder's territory; multi-TCG pitch §4 hinges on this distinction)
- **Funko / comic books** — out of scope (would dilute into Collectr territory)
- **Real-time websocket pricing** — overengineering for the use case; daily/hourly is sufficient
- **Mobile app (native iOS/Android)** — web/PWA is enough for now; resources go to the data layer
- **Crypto/NFT integration** — explicit no, despite market research mentioning blockchain trends
- **Full repo rewrite** — incremental only (`plan-v3.md` §4)
- **Hysteresis bands on signal thresholds** — investigated 2026-04-26, no data supports it (CLAUDE.md §11)
- **Discord bot as product surface** — decided 2026-05-02 (TASK-104). The product is web-first. Discord is an outbound alert channel via REST API only. **No inbound bot, no slash commands, no Discord OAuth login.** If TCG influencers / community partners want Discord integration in the future, the right pattern is webhook-outbound (we deliver content into their existing servers), not asking users to join ours.
- **Native mobile push notifications** — web push (PWA) is sufficient if we ever need real-time delivery. Native apps are off the table per the mobile app entry above; native push falls under that decision.
- **Custom GitHub Action for PR review** — decided 2026-05-02 (TASK-103b). Codex Cloud is included in our existing ChatGPT subscription with zero ongoing maintenance. Building a custom Action duplicates effort for no gain. **Only revisit if Codex Cloud is removed from Plus tier or fundamentally changes behavior.**
- **Routing all LLM tasks to a single provider** — decided 2026-05-02 (TASK-401). Anthropic, Groq, and OpenAI each have task types they're best at. Single-provider routing saves no money and loses heterogeneity benefits.
- **Server-side watchlist persistence before user demand** — decided 2026-05-03 (TASK-301d). Watchlist is currently localStorage. Adding server-side storage implies cross-device sync, conflict resolution, and versioning — product decisions that should be user-driven (user reports losing watchlist on device switch), not pre-built on engineering convenience. F-4 watchlist limit is a conversion nudge, not a true paywall; client-side enforcement is sufficient. **Only revisit if:** (a) a Plus subscriber explicitly reports device-switch data loss, OR (b) a product decision to enable cross-device sync as a Plus feature is made.
- **Server-side watchlist before Section 2 of Market Digest** — decided
  2026-05-03 (TASK-301e). TASK-301d chose client-side localStorage watchlist.
  TASK-301e Section 2 (watchlist movers in digest) is therefore deferred to
  TASK-301e2. Bridging them by adding server-side watchlist here would revisit
  TASK-301d; that decision should be driven by user demand (cross-device sync
  request), not by digest personalisation convenience.

If a task being proposed falls into one of the above, **reject without operator escalation**.

---

## 6. Maintenance

- **Weekly:** Operator reviews §2 priorities, moves things between P0/P1/P2 as state changes.
- **Per task completion:** Claude Code moves the task to §3 in the same PR that completes it.
- **Quarterly:** Archive §3 entries older than 30 days to `docs/backlog-archive/`.
- **When CLAUDE.md updates:** check whether any §1 invariants need to be added/removed.

*This file is living documentation. Propose updates via PR with title `chore(backlog): <change>`.*
