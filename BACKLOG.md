# BACKLOG.md — Flashcard Planet 任务流

> **Companion docs:** `CLAUDE.md` (agent operating rules), `docs/plan-v3.md` (current-state plan), `.claude/session-handoff-<latest>.md` (24h state snapshot).
>
> **This file is for Claude Code to consume autonomously.** When picking up a session and there is no specific operator instruction, read this file and start the highest-priority task you have evidence to safely execute. See §0 below.

**Last updated:** 2026-05-02 (v3 — operator review revisions)
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
- [ ] **No PR merges to main without `## Codex Review` section.** This is a procedural invariant, enforced by Claude Code self-discipline (until automated by TASK-103b).
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
- After verification passes, **propose** a CLAUDE.md §6 entry as "Lesson 6: First non-Pokemon signal validated end-to-end" — but this is documentation maintenance, not a verification gate. Doing it well is encouraged; not doing it does not block task completion.

---

#### TASK-102 — Database backup infrastructure

**Priority:** P0
**Status:** needs_decision
**Owner:** Ivan (decision) → Claude Code (execution)
**Preconditions:**
- Operator decides between: (a) Railway Pro plan upgrade, (b) external `pg_dump` → S3/Backblaze daily, (c) hybrid

**Definition of Done:**
- Daily backup running and visible in some monitorable location (Railway dashboard / S3 bucket / wherever)
- One end-to-end restore drill performed against a non-prod DB; RTO documented as <4 hours
- `docs/runbooks/disaster-recovery.md` written with exact commands to restore from backup

**Estimated effort:** M
**Reference:** CLAUDE.md §7 ("No backup infrastructure (Hobby plan). Operator accepted this risk explicitly; P0 remains on backlog.")
**Notes:** **Must complete before TASK-301 (Pro tier launch).** Once real money is involved, the cost of a single point of failure goes up by orders of magnitude.

---

#### TASK-103a — Codex CLI CI feasibility research

**Priority:** P0
**Status:** ready
**Owner:** Claude Code (research only — no code changes)
**Preconditions:** Codex CLI is installed and authenticated locally (already true).

**Definition of Done:**
A short report at `docs/audits/2026-XX-codex-ci-feasibility.md` answering:

1. **What auth mechanism does Codex CLI v0.118.0 use?** (OpenAI API key / ChatGPT session token / OAuth / other) — find this by inspecting where Codex stores credentials locally and what env vars / config files it reads.
2. **Is that auth form storable in GitHub Actions Secrets?**
   - API keys: yes, trivially.
   - Session tokens: no — they expire and are not designed for headless CI.
   - OAuth refresh flows: depends on whether Codex supports non-interactive refresh.
3. **If auth works in CI, does Codex CLI run headless?** Try `codex exec` from a non-TTY shell locally to simulate CI. Some CLIs require a TTY and fail silently in CI.
4. **If Codex doesn't fit CI, list 2-3 alternatives** with one-line tradeoffs:
   - GitHub Copilot CLI as reviewer
   - Claude Code itself running with a "play independent reviewer" prompt (loses true independence but preserves the review gate)
   - Other open-source LLM review tools (e.g., aider, sweep) — note any that exist in 2026
5. **Recommendation:** which path to take in TASK-103b.

**Estimated effort:** XS (research; one afternoon)
**Reference:** CLAUDE.md §4 ("Claude Code must run this itself — do not delegate to the operator")
**Notes:**
- Pure research task. Do NOT modify any CI config or secrets in this task.
- Output is a markdown file the operator can read in 5 minutes and decide direction.

---

#### TASK-103b — Implement automated PR review (path TBD by 103a)

**Priority:** P0
**Status:** blocked
**Blocked by:** TASK-103a
**Owner:** Claude Code
**Preconditions:**
- TASK-103a complete with operator-approved recommendation

**Definition of Done:**
- An automated review runs on every PR and posts findings as a PR comment under a `## Codex Review` (or equivalent) heading
- The automation runs without operator intervention
- Existing manual `codex exec` workflow remains as a fallback documented in CLAUDE.md
- At least 1 PR has gone through the full automated cycle, with the comment visible on the PR

**Estimated effort:** M
**Reference:** TASK-103a output
**Notes:**
- This is one of the three changes that converts Claude Code from "reactive 9-5 helper" to "24-hour async builder" (the others being TASK-102 backups and TASK-104 product surface cleanup).
- The exact implementation depends entirely on 103a findings. If Codex CLI doesn't fit CI, this task may end up implementing a Claude Code self-review fallback — that's acceptable and preserves the review gate, even if not fully independent.

---

### P1 — should do this month

#### TASK-104 — Archive Discord bot, simplify product boundary

**Priority:** P1
**Status:** ready
**Owner:** Claude Code

**Background:** `bot/main.py` has 9 fully-implemented slash commands (`/price`, `/predict`, `/history`, `/watch`, `/watchlist`, `/unwatch`, `/alerts`, `/topmovers`, `/topvalue`, `/alerthistory`) but has never been deployed. Zero users have used them. This is the largest "designed but never ran" surface in the codebase (CLAUDE.md Lesson 2 pattern).

The product is web-first: FastAPI + Card Detail + Signals + Watchlist + Pro tier permissions + pricing page are all on web. Competitors (Card Ladder, MTGStocks, Collectr, Pokelytics) are all web-first. Discord-as-product-surface is a 2024 MVP decision that the product has outgrown.

**What stays:** `backend/app/services/alert_service.py` — sends alerts via Discord REST API, not Gateway connection. Zero deployment cost, already works, you're used to it. Keep this as alert delivery channel only.

**What goes:** `bot/main.py` slash command process, Discord OAuth-as-login binding (redundant with magic link + Google OAuth which already exist).

**Preconditions:** None.

**Definition of Done:**
1. `bot/` directory moved to `archive/discord-bot-2026/` (preserve history; do not `git rm` outright in case future rollback needed)
2. `archive/discord-bot-2026/ARCHIVED.md` written with:
   - Date archived and reason
   - Re-evaluation conditions (see Notes below)
   - Pointer to `alert_service.py` for "where Discord alerts come from now"
3. `requirements.txt`: if `discord.py` is ONLY referenced from `bot/`, remove it. If referenced elsewhere, keep with comment.
4. `bot/api_client.py` and `bot/link_builder.py` move with the rest of `bot/`.
5. Audit Discord OAuth binding routes in `backend/app/api/routes/auth.py`:
   - `/account/link-discord` and `/account/link-discord/callback` — keep or remove based on whether anyone has actually linked. If no users have linked, remove. Keep magic link + Google OAuth untouched.
6. `CLAUDE.md` §1 product description updated: "Web-first TCG market intelligence platform. Discord is an alert delivery channel via REST API, not a product surface."
7. `CLAUDE.md` §2 architecture quick reference: remove any references to `bot/` as an active component. Note `alert_service.py` as the Discord integration point.
8. `README.md` "What is included" section: remove "Discord bot with slash commands" line. Replace with "Discord alert delivery (one-way, via REST API)".
9. Existing `tests/test_discord_binding.py` kept (it tests the Discord OAuth binding routes that may stay) OR removed if step 5 removes those routes.
10. Run full test suite, confirm no regressions.
11. Codex review.

**Estimated effort:** S
**Reference:** Conversation 2026-05-02 strategic discussion about Discord product role.
**Notes:**
- **Re-evaluation conditions (write into ARCHIVED.md):**
  - Pro users ≥ 30 AND at least 5 unprompted user requests for Discord integration
  - OR: at least 1 competitor (Card Ladder, MTGStocks, Pokelytics, Collectr) demonstrates Discord bot as a measurable acquisition channel with public data
  - In neither case has been met — do not redeploy
- **Future Discord integration, if it ever happens, should be webhook-outbound** (Discord server admins install our webhook in their channels), NOT inbound bot. This is the correct 2026 Discord integration pattern: meet users in their existing communities, not pull them into ours.
- Slash command code preservation: keep in archive intact so future redeployment is a `git mv` away, not a rewrite.

---

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

#### TASK-203 — Pro tier payment integration design doc

**Priority:** P1
**Status:** ready
**Owner:** Claude Code (research) + Ivan (decision)
**Preconditions:** None

**Definition of Done:**
- A design doc at `docs/strategy/06_pro_tier_launch.md` covering:
  - Payment provider comparison: Stripe vs LemonSqueezy vs Paddle (focus on Australian solo developer + cross-border buyer + tax handling)
  - Required schema changes to `users` (subscription_status, subscription_provider_id, current_period_end, etc.)
  - Webhook handling (subscription.created / .updated / .deleted, payment_intent.failed)
  - Free trial enforcement strategy (7 days)
  - `/pricing` page implementation plan (frontend file location, i18n keys, CTA wiring)
  - 5 CTA placement points per `03_pricing_page_copy.md` (Card Detail / Signals page / Watchlist / Cross-TCG teaser / Alert limit)
  - Refund / cancellation flow
  - "What if I stop paying?" data retention policy

**Estimated effort:** S (research only)
**Reference:** `docs/strategy/03_pricing_page_copy.md`, `backend/app/core/permissions.py`
**Notes:** Operator's decision required before any code is written. This task produces the **plan**; TASK-301 will be the implementation once the plan is approved.

---

#### TASK-204 — Image backfill retry audit

**Priority:** P1
**Status:** ready
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

#### TASK-302 — Pro tier waitlist form (promoted from P2)

**Priority:** P1
**Status:** ready
**Owner:** Claude Code
**Preconditions:** None

**Why P1:** This is one of the few tasks that produces real product-state change without depending on Pro work. Concrete benefits even if Pro launch slips by 3 months:
1. **Real conversion funnel data** — visitor → email capture rate is the first marketing metric the product has ever generated
2. **Pre-built launch list** — when Pro goes live, day-1 has demand instead of zero
3. **Early-believer identification** — useful for launch promo pricing decisions ($9 vs $12 first 100)
4. **Operator habit shift** — switches the daily metric reflex from technical (`scheduler_run_log` success rate) to commercial (waitlist growth rate). This habit needs to exist BEFORE Pro launch, not after.

**Definition of Done:**
- A "Join the Pro waitlist" form on the homepage and `/pricing` placeholder
- Email capture with confirmation email (use existing magic link infrastructure for sending — same SMTP path)
- Stored in a `pro_waitlist` table: `email, signed_up_at, source_page, locale, ip_country (optional)`
- Admin endpoint `/admin/diag/waitlist` returns count + recent N + simple growth rate (today vs 7d avg)
- Double opt-in NOT required for v1 — single opt-in is fine for solo-operator scale; revisit if list crosses 1000
- One end-to-end manual test: submit email, receive confirmation, verify row in DB

**Estimated effort:** XS-S
**Reference:** Marketing principle: build the list before the product so launch day has demand
**Notes:**
- **Do not** add complex marketing automation (drip campaigns, segmentation). Just capture the email. Pro launch is the action moment.
- A simple "thanks, we'll email you when Pro launches" page is enough — don't over-design.
- This is the **earliest** task that gives the operator any signal about market demand. Don't underweight that.

---

### P2 — important but not urgent

#### TASK-205 — Dashboard structure audit vs. v3 spec (demoted from P1)

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
**Notes:**
- Demoted from P1 to P2 in v3 of this backlog. Reasoning: this is an audit producing knowledge, not product change. Dashboard module ordering is unlikely to be the bottleneck on Pro conversion vs. Pro tier not existing at all (TASK-301), or vs. there being no waitlist to convert into Pro (TASK-302).
- Revisit after Pro launches if conversion data suggests dashboard is a friction point.

---

#### TASK-206 — Signals page Pro/Free hierarchy audit (demoted from P1)

**Priority:** P2
**Status:** ready
**Owner:** Claude Code
**Preconditions:** None

**Definition of Done:**
- An audit comparing current `signals_page` ProGate placements against `03_pricing_page_copy.md` Free vs Pro spec
- Either: (a) audit shows full match, mark v3 A-3 → Done in `plan-v3.md`, or (b) audit shows gaps, list them with size estimates

**Estimated effort:** S
**Reference:** `docs/plan-v3.md` §3 A-3
**Notes:**
- Demoted from P1 to P2 in v3 of this backlog. Same reasoning as TASK-205: audit produces knowledge, not change.
- Will become more relevant when TASK-203 (payment design) reaches the CTA wiring step — that's when the Free/Pro visual hierarchy matters concretely.

---

#### TASK-301 — Pro tier launch implementation

**Priority:** P2 (currently — promotes to P1 when TASK-102 + TASK-203 are both done)
**Status:** blocked
**Blocked by:** TASK-102 (backups), TASK-203 (payment design)
**Owner:** Claude Code + Ivan
**Preconditions:**
- Database backups in place (TASK-102 done)
- Payment provider chosen and design doc approved (TASK-203 done)
- Pricing decided ($12/mo recommended; launch promo $9/mo for first 100 users to be confirmed)

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
**Notes:** Accepted tradeoff — only do this when the conditions above trigger. Listed here so it doesn't get forgotten.

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
**Reference:** Operator confirmed wanting this in the strategic conversation, but explicitly deferred. Worth revisiting once multi-TCG breadth is established.
**Notes:** This is a "nice to have" until there's user demand evidence (Pro users asking for vintage sets we don't cover).

---

#### TASK-305 — `/pricing` page i18n + Chinese localization

**Priority:** P2
**Status:** ready
**Owner:** Claude Code
**Preconditions:** TASK-301 has at least produced the English `/pricing` page

**Definition of Done:**
- Chinese translation of `/pricing` page using existing i18n framework (already used in alerts page per `plan-v3.md` I18N-1b)
- Translations match `03_pricing_page_copy.md` Chinese version
- Currency display switches to ¥ when locale is `zh`
- One end-to-end manual test in zh locale

**Estimated effort:** S
**Reference:** `03_pricing_page_copy.md` Chinese section, `plan-v3.md` I18N-1b
**Notes:** Hong Kong / Taiwan / Singapore TCG investing communities are real but not the launch market.

---

#### TASK-306 — Evaluate replacing Discord alerts with Sentry / Healthchecks / email

**Priority:** P2
**Status:** ready
**Owner:** Claude Code
**Preconditions:** TASK-104 completed (Discord bot archived). This task evaluates whether to also replace the REST API alert path.

**Definition of Done:**
- Evaluation written: should `alert_service.py`'s Discord REST API path be replaced by Sentry (errors) + Healthchecks.io (job heartbeat) + email (digest)?
- Comparison covers: cost, signal-to-noise, operator-on-mobile experience, vendor lock-in
- If replace: design doc + implementation as separate follow-up task
- If keep as is: formal "keep" decision recorded in `docs/decisions/2026-XX-discord-alerts.md` so we don't relitigate

**Estimated effort:** S (decision) or M (if implemented)
**Reference:** Conversation 2026-05-02 — discussion of better alert tooling for solo operator
**Notes:** Discord REST API alerts work. This is "nice to have" not "must do". Evaluate after Pro launch when alert volume might increase. **Do NOT start before TASK-104 is merged** — the order matters because TASK-104 is "remove the bot process", and TASK-306 is "evaluate the alert delivery layer". Confusing the two would scope-creep TASK-104.

---

### needs_triage (proposed by Claude Code or operator, not yet prioritized)

(Empty — this is the dump zone. Add new tasks here when discovered, then the next triage pass moves them to P0/P1/P2.)

---

## 3. Completed (last 30 days)

When a task ships, move it here with PR number and merge date. Keep this section trimmed to the last 30 days; older items move to `docs/backlog-archive/<year>-<month>.md` quarterly.

| TASK | Title | PR | Merged | Outcome |
|---|---|---|---|---|
| — | (placeholder — first migrations into this format) | — | — | — |

---

## 4. Decisions log (deferred items needing operator input)

When a task is `needs_decision`, log here:

| Date raised | Question | Status | Resolution date | Resolution |
|---|---|---|---|---|
| 2026-05-02 | Database backup: Railway Pro vs external `pg_dump` vs hybrid? (TASK-102) | open | — | — |
| 2026-05-02 | Pro tier payment provider: Stripe vs LemonSqueezy vs Paddle? (TASK-203) | open | — | — |
| 2026-05-02 | Pokemon full historical coverage vs multi-TCG breadth — which gets resources first after Pro launches? (TASK-304) | open | — | — |
| 2026-05-02 | Discord bot 24-hour deployment vs archive? | **resolved** | 2026-05-02 | **Archive.** Zero users on slash commands, web is the product, REST API alerts stay. See TASK-104. |
| 2026-05-02 | Codex CLI in CI: feasible or use alternative? | open — research scheduled | — | TASK-103a will produce the answer |

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

If a task being proposed falls into one of the above, **reject without operator escalation**.

---

## 6. Maintenance

- **Weekly:** Operator reviews §2 priorities, moves things between P0/P1/P2 as state changes.
- **Per task completion:** Claude Code moves the task to §3 in the same PR that completes it.
- **Quarterly:** Archive §3 entries older than 30 days to `docs/backlog-archive/`.
- **When CLAUDE.md updates:** check whether any §1 invariants need to be added/removed.

*This file is living documentation. Propose updates via PR with title `chore(backlog): <change>`.*
