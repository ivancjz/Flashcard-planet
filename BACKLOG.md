# BACKLOG.md — Flashcard Planet 任务流

> **Companion docs:** `CLAUDE.md` (agent operating rules), `docs/plan-v3.md` (current-state plan), `.claude/session-handoff-<latest>.md` (24h state snapshot).
>
> **This file is for Claude Code to consume autonomously.** When picking up a session and there is no specific operator instruction, read this file and start the highest-priority task you have evidence to safely execute. See §0 below.

**Last updated:** 2026-05-02 (v5 — Pro launch parameters decided, TASK-203 complete)
**Maintained by:** Ivan (operator) with proposed updates from Claude Code via PR

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
**Status:** ready
**Owner:** Claude Code
**Preconditions:**
- Today is 2026-05-07 or later (YGO needs 7-14 days baseline window after 2026-04-23 activation; PR #15 seeded 5 sets, PR #28 expanded to 13)
- Production has YGO `price_history` rows continuously written for at least 7 days
- `/admin/diag/ygo-verify-26` endpoint is still deployed (it has a sentinel for removal but should still be live)

**Definition of Done:**
- SQL evidence: ≥30% of YGO assets have a non-`INSUFFICIENT_DATA` signal label
- At least one YGO BREAKOUT/MOVE/WATCH visible in #flashcard-alerts channel
- Card Detail page renders cleanly for 3 sample YGO assets (one from each rarity tier: Secret, Ultra, Common)

**Estimated effort:** S
**Reference:** CLAUDE.md §7 ("Non-INSUFFICIENT YGO signals expected to appear around 2026-05-07"), `/admin/diag/ygo-verify-26` endpoint
**Notes:**
- This is a verification task, not a code change. If <30% threshold not met by 2026-05-14, escalate to operator — likely indicates either data freshness or threshold calibration issue.
- After verification passes, **propose** a CLAUDE.md §6 entry as "Lesson 6: First non-Pokemon signal validated end-to-end" — but this is documentation maintenance, not a verification gate.

---


---

#### TASK-103b — PR review automation via Codex Cloud (Path C)

**Priority:** P0
**Status:** ready
**Owner:** Ivan (5 min config) + Claude Code (AGENTS.md + CLAUDE.md updates)

**Background:** TASK-103a confirmed Codex CLI is headless-capable in CI but blocked on auth (ChatGPT OAuth session can't be stored as GitHub Secret). Three paths surfaced:
- Path A: OpenAI API key + custom GitHub Action
- Path B: Claude Code self-review (loses independence)
- **Path C (chosen): Codex Cloud automated review** — included in current ChatGPT subscription, no API key needed, OpenAI-managed infrastructure

**Why Path C:** Zero additional cost (already paid via ChatGPT subscription). Zero ongoing maintenance (OpenAI hosts it). Preserves full reviewer independence. Configures in 5 minutes vs hours for Path A. Path A's strength was "works without ChatGPT" — irrelevant when we have ChatGPT. The OpenAI API credit purchased earlier gets redirected to TASK-401 (LLM analysis pool) where it produces direct product value instead.

**Preconditions:** None.

**Definition of Done:**
1. **Operator action (done)**: Log into chatgpt.com → Codex settings → enable Code review for `ivancjz/Flashcard-planet` repo. Toggle on "Automatic reviews".
2. **Operator action (done)**: Verify the bot account is granted access to the repo via GitHub OAuth flow Codex initiates.
3. `AGENTS.md` at repo root with review guidelines — **done** (committed 2026-05-02).
4. CLAUDE.md §4 updated — **done** (committed 2026-05-02): Codex Cloud is primary; manual `codex exec review` is fallback.
5. CLAUDE.md §1 invariant reworded: "No PR merges without Codex review (auto-posted by Codex Cloud, or manually pasted as fallback)" — **done**.
6. **Validation**: Open one test PR. Confirm Codex Cloud posts a `## Codex Review` comment within 10 minutes.

**Estimated effort:** XS (config) + S (AGENTS.md authoring)
**Reference:** TASK-103a research output. Conversation 2026-05-02.
**Notes:**
- Plus subscribers get ~400–1000 code reviews per 5-hour window. At Ivan's PR cadence (~30 PR/month), this is ~100x headroom.
- AGENTS.md is read by Codex Cloud automatically. It does not duplicate CLAUDE.md — it extracts the review-relevant subset.
- If Codex Cloud is later removed from Plus tier, fall back to Path A. The OpenAI API key from TASK-401 is sufficient — only need to add a GitHub Action workflow at that point.

---

### P1 — should do this month

#### TASK-201 — YGO Tier 1 expansion to ~30 sets

**Priority:** P1
**Status:** ready
**Owner:** Claude Code
**Preconditions:**
- TASK-101 completed (YGO signal graduation proven)
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
**Notes:** Use the existing PR #11 import guard pattern — bulk import only sets that exist in DB; never auto-import on schedule.

---

#### TASK-202 — One Piece TCG integration research spike

**Priority:** P1
**Status:** ready
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

### P2 — important but not urgent

#### TASK-205 — Dashboard structure audit vs. v3 spec

**Priority:** P2
**Status:** ready
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
**Status:** ready
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
**Status:** ready
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
**Status:** ready (re-evaluation conditions matter)
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
**Status:** ready
**Owner:** Claude Code
**Preconditions:** TASK-301 has at least produced the English `/pricing` page

**Definition of Done:**
- Chinese translation of `/pricing` page using existing i18n framework
- Translations match `03_pricing_page_copy.md` Chinese version
- Currency display switches to ¥ when locale is `zh`
- One end-to-end manual test in zh locale

**Estimated effort:** S
**Reference:** `03_pricing_page_copy.md` Chinese section, `plan-v3.md` I18N-1b

---

#### TASK-306 — Evaluate replacing Discord alerts with Sentry / Healthchecks / email

**Priority:** P2
**Status:** ready
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

### needs_triage (proposed by Claude Code or operator, not yet prioritized)

#### TASK-T01 — YGO image retry path
**Proposed:** 2026-05-02 (TASK-204 audit finding)
`_query_missing_image()` only covers `game='pokemon'`. YGO assets that lack images have no retry path. ~20 LOC fix in `pokemon_tcg.py` + `ygo.py`. Not urgent (67 YGO assets today), but needed before YGO expansion to 300+ assets (TASK-201).

#### TASK-T02 — Add failed_backfill_queue count to diagnostics
**Proposed:** 2026-05-02 (TASK-204 audit finding)
`failed_backfill_queue` permanent failure count is not visible in any admin endpoint. Add to next diagnostic endpoint PR alongside TASK-301 diag work.

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

---

## 3. Completed (last 30 days)

When a task ships, move it here with PR number and merge date. Keep this section trimmed to the last 30 days; older items move to `docs/backlog-archive/<year>-<month>.md` quarterly.

| TASK | Title | PR | Merged | Outcome |
|---|---|---|---|---|
| TASK-103a | Codex CLI CI feasibility research | (research only) | 2026-05-02 | Codex CLI is headless-capable; ChatGPT OAuth blocks GitHub Secret storage; Path C (Codex Cloud) chosen. Report at `docs/audits/2026-05-02-codex-ci-feasibility.md` |
| TASK-104 | Archive Discord bot, simplify product boundary | commit e09c100 | 2026-05-02 | bot/ archived to archive/discord-bot-2026/. OAuth routes removed. 845 tests pass. |
| TASK-302 | Pro tier waitlist form | commit ef6f7e3 | 2026-05-02 | POST /api/v1/waitlist + admin diag + landing page form. 851 tests pass. Requires migration 0029 on prod. |
| TASK-103b | PR review via Codex Cloud (Path C) | commit 47b3c63 | 2026-05-02 | AGENTS.md written. CLAUDE.md §4 updated. Operator enables Codex Cloud in chatgpt.com settings. |
| TASK-401 | OpenAI as third LLM provider | commit 9dafe11 | 2026-05-02 | OpenAIProvider + task-type router + FallbackLLMProvider + IP tagging experiment. 861 tests pass. |
| TASK-203 | Pro tier payment integration design doc | commit f1ee749 | 2026-05-02 | Design doc + 6-decision ADR. LemonSqueezy MoR, USD $12/$9 Founders, card-free 7d trial. TASK-301 now blocked only on TASK-102 (backups). |
| TASK-204 | Image backfill retry audit | (audit only) | 2026-05-02 | Two-layer retry exists (backfill_pass + retry_pass). ~0% imageless rate for Pokemon. Gap: YGO has no image retry path. See docs/audits/2026-05-02-image-backfill.md |
| TASK-102a | Daily pg_dump backup via GitHub Actions | commit a9c5cfb | 2026-05-02 | Workflow + disaster-recovery runbook. Operator must: create backup repo, add 3 secrets, run workflow_dispatch, perform restore drill. |
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

If a task being proposed falls into one of the above, **reject without operator escalation**.

---

## 6. Maintenance

- **Weekly:** Operator reviews §2 priorities, moves things between P0/P1/P2 as state changes.
- **Per task completion:** Claude Code moves the task to §3 in the same PR that completes it.
- **Quarterly:** Archive §3 entries older than 30 days to `docs/backlog-archive/`.
- **When CLAUDE.md updates:** check whether any §1 invariants need to be added/removed.

*This file is living documentation. Propose updates via PR with title `chore(backlog): <change>`.*
