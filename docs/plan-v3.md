# Flashcard Planet — Working Plan (v3)

**Last updated:** 2026-04-18
**Status:** Productization phase, post-C-4, post-B-2, post-v3.1 Phase C
**Companion doc:** `CLAUDE.md` (agent operating rules)

---

## How to use this document

This is a **current-state plan**, not a copy of the original v3 proposal.
It reflects what is actually in the codebase as of the date above, not
what was planned 12 weeks ago. If something here conflicts with older
planning docs (the `Flashcard_Planet_计划书_详细的v3.docx` in particular),
**this file wins**.

The plan is organised in three layers:

1. **What's already built** — features and capabilities that exist today
2. **v3.1 architecture migration** — status of the DataService/boundary
   refactor, with explicit decisions on what to finish and what to defer
3. **Roadmap** — remaining work, ordered

When Claude Code is given a new task, it should cross-check against
the "already built" section first to avoid re-implementing something
that already exists. Many items in the original v3 doc are already done.

---

## 1. What's already built

The original v3 plan organised work into four workstreams (A Product
Experience, B Data Coverage, C Monetization, D Ops). That mental model
still helps for navigation, so the completed list preserves it.

### Workflow A — Product Experience

- **A-2 Card Detail (credibility indicators)** — ✅ Done
  - `sample_size_label`, `data_age_label`, and source breakdown all
    render on the card detail page
  - Rendering is inline in `site.py:792-793` via
    `build_credibility_indicators()` + `render_credibility_html()`
  - Label definitions in `backend/app/services/card_credibility_service.py:42-43`
  - Caveat: wired directly, not through `DataService` — see §2 ST-1

- **A-3 Signals page Free/Pro layering** — 🚧 Partial
  - `signals_page` exists with 10 `ProGate` macro callsites
  - Whether the full Free/Pro visual hierarchy matches the v3 spec is
    not confirmed — treat as partially done until audited

### Workflow B — Data Coverage & Quality

- **B-2 Mapping rule optimization** — ✅ Done
  - `rule_engine` extracts language and variant, computes confidence
    score, falls back to AI when confidence < 0.75
  - Complete structure per the v3 spec

- **B-4 Trust indicators (UI surface)** — ✅ Done (feature-wise)
  - All three indicators render on Card Detail: sample size, data age,
    source breakdown
  - Architecturally still routes directly; ST-1 would move this through
    `DataService`

### Workflow C — Monetization

- **C-1 Pro capability boundary** — ✅ Done
  - `backend/app/services/permissions.py` defines `AccessTier` and
    `Feature` enums (15 gated features) plus `can()`,
    `get_capabilities()`, `get_pro_gate_config()` helpers

- **C-3 Upgrade flow (mock/manual)** — ✅ Done
  - `upgrade_service.py` + `upgrade_requests` table (migration 0010) +
    backstage approval routes all in place

- **C-4 Permission gating consolidation** — ✅ Done
  - Everything routes through `permissions.py`
  - Defensive test: `TestFeatureEnum.test_all_expected_features_exist`
    in `tests/test_permissions.py` will fail if you add a `Feature`
    without updating the expected set
  - **For new code:** never compare `access_tier == "pro"` directly —
    always go through the helper

### Workflow D — Ops Maturity

- **D-1 Unified Diagnostics page** — ✅ Done
  - `GET /admin/diagnostics` renders a full KPI panel covering
    ingestion, signals, review queue, scheduler, and backfill

- **D-2 KPI panel with threshold alerts** — ✅ Done
  - `kpi_thresholds.py` + `kpi_status()` used throughout
    `diagnostics_summary_service`
  - Badge colours reflect threshold state

- **D-3 Backfill failure retry queue** — ✅ Done
  - `backfill_retry_service.py` + `FailedBackfillQueue` model +
    scheduler integration + diagnostics surface all live

### Infrastructure / cross-cutting

- **Auth v2** — ✅ Shipped (separate PR, independent of v3.1)
- **v3.1 Phase C Layer 1** (Bot UTM-tagged links) — ✅ Done
  - `bot/link_builder.py` + `extract_utm_params` in `site.py:2736`
- **v3.1 Phase C Layer 3** (Discord landing pages) — ✅ Done
  - `/welcome-from-discord`, `/upgrade-from-discord`,
    `/signals/explained` all live in `site.py`

---

## 2. v3.1 architecture migration — status and decisions

The v3.1 migration added a `DataService` abstraction layer and a
Discord→Web funnel. Most of it is done or explicitly deferred. Full
spec: `docs/superpowers/specs/2026-04-17-v31-architecture-migration-design.md`.

### What's already built from v3.1

- `backend/app/core/data_service.py` — fully implemented
  - `get_card_detail()`, `get_signals()`, `resolve_asset_id()`,
    `get_access_tier_for_discord_user()`
- `backend/app/core/response_types.py` — exists
- `backend/app/core/boundary_check.py` — exists as a comment/stub only
- Phase C Layer 1 (bot UTM links) — shipped
- Phase C Layer 3 (Discord landing pages) — shipped

### Remaining sub-tasks and decisions

Based on cost/benefit analysis, three sub-tasks remain. Decisions below.

#### ST-2: Wire credibility data into alert embeds — ✅ Done (2026-04-18)

**What it means.** Price alerts fired from `services/alert_service.py`
now include credibility data (sample size, match confidence) and a
pro-gate upgrade nudge for free-tier users in the Discord embed.

**Implementation notes.** Pre-implementation research found that
`ResponseTemplates.price_alert()` in `bot/main.py` is not
plug-compatible with `alert_service`: it returns a wrapped
`{"embed": {...}}` dict and expects a `card_data.change` attribute
that has no equivalent in `CardDetailResponse`. The actual
implementation instead enriches `build_alert_notification_embed()`
directly, following the existing `signal_snapshot` field pattern
(lines 553–559). Credibility data is fetched via
`build_credibility_indicators()` under a `# boundary-ok` exception
citing this document — symmetric with `site.py`'s call pattern, so
ST-1 cleanup will cover both sites uniformly. `ResponseTemplates` is
left unchanged.

**Files changed.**
- `backend/app/services/alert_service.py` — added `_credibility_fields()`
  helper, enriched `build_alert_notification_embed()`, added credibility
  fetch with per-asset cache in `evaluate_active_alerts()`
- `tests/test_alert_service.py` — 9 new tests in `AlertEmbedCredibilityTests`

#### ST-1: Wire card_detail_page through DataService — **DEFER**

**Why defer.** The current code path (`site.py` → `build_card_detail()`
+ `build_credibility_indicators()`) and `DataService.get_card_detail()`
produce identical data today because they call the same underlying
services. The divergence risk is real but future-tense. Medium refactor
in `site.py` for no user-visible benefit.

**When to revisit.** Both `site.py:card_detail_page` and `alert_service.py`
now call `build_credibility_indicators()` directly with `# boundary-ok`
exceptions. ST-1 becomes worth doing when (a) a third consumer appears
and we want to stop accumulating boundary exceptions, or (b) a new
credibility field needs to propagate to both web and alerts, making the
duplicate call sites a real maintenance cost. Until one of these
triggers, the current arrangement is the right economic choice.

#### ST-3: Make boundary_check.py runnable — **DEFER**

**Why defer.** Only two current consumers of the boundary (the cards
API and the bot). Human review can manage this. CI enforcement is
overhead for a problem that isn't biting.

**When to revisit.** When a third consumer appears, or when a boundary
violation slips through review.

### Loose end

- `templates/macros/progate.html` — orphan macro. Its function is
  already served by `banner._progate_html_from_config()`. Safe to
  delete; does not block anything. Not scheduled.

---

## 3. Roadmap — remaining work in order

Ordered per the decision: architecture finish → frontend polish →
data expansion. The architecture finish is smaller than it first
appeared (ST-2 only).

### Phase 1 — Finish the one migration piece that matters ✅ Complete

**Scope.** ST-2 (above).

**Definition of done — all met as of 2026-04-18.**
- ✅ A free-tier Discord user receiving a triggered alert sees credibility
  data in the embed (sample size, match confidence)
- ✅ A free-tier user sees a pro-gate upgrade nudge in the alert body
- ✅ Tests in `test_alert_service.py` cover both free and pro paths
  (9 new tests in `AlertEmbedCredibilityTests`)
- ✅ All existing tests still pass — suite is 531 tests (up from 522;
  +9 from ST-2)

### I18N infrastructure — status and decisions

**Discovery note.** Original A-4 gap 1 was assumed to require writing
translations. Research revealed the `site.js` toggle mechanism already
existed and worked for all 234 `_lang_pair()` call sites; only 3 pages
with inline JS remained disconnected. The work scope shrunk from "design
a translation system" to "wrap ~57 JS strings with `t()`". I18N-1b
completed the most user-facing 28 of those.

#### I18N-1a — Expose `t()` globally ✅ Done (2026-04-18)

Added `window.t = t` inside the `site.js` IIFE, right after the `t()`
definition. Allows inline `<script>` blocks in any page to call `t()`
without a separate import. No behavior change for existing
`_lang_pair()` content. Commit `c09539e`.

#### I18N-1b — `alerts_page()` inline JS ✅ Done (2026-04-18)

All 28 Chinese-only string literals in `alerts_page()` wired through
`t()`. Status labels, loading states, error messages, action buttons,
and result counts all respond to the language toggle. Commit `d3e2437`.

#### I18N-1c — `watchlists_page()` inline JS ⬜ Deferred

~14 string sites. Deferred to keep review surface small and allow
focused translation work per page.

#### I18N-1d — `backstage_review_page()` inline JS ⬜ Deferred

~14 string sites. Admin-only page; lower urgency than user-facing pages.
Deferred alongside I18N-1c.

---

### Phase 2 — Frontend polish ← active

Four candidates. Pick one to start; they are independent of each other.

#### A-4 Alerts page — one gap done, two remaining 🚧 Partial

**Completed:**
- **Gap 1 — Status labels** ✅ Done (2026-04-18, shipped as I18N-1b).
  All 28 inline JS strings in `alerts_page()` replaced with `t(zh, en)`
  calls. Translations: `"已停用"` → `"Disabled"`, `"已启用"` → `"Active"`,
  `"等待重置"` → `"Waiting to rearm"`. Validation failure message
  `"出错了。"` promoted to `"Please fill out all fields."` (all other
  `"出错了。"` sites map to `"Something went wrong."`). See commit
  `d3e2437` for full translation notes.

**Remaining:**
- **Gap 2 — Alert type dropdown shows raw enum names.**
  `PRICE_UP_THRESHOLD`, `TARGET_PRICE_HIT`, etc. Needs human-friendly
  display labels.
- **Gap 3 — Lookup field still keyed on `discord_user_id`.** After
  Auth v2 shipped, this should default to the logged-in session user
  rather than requiring manual Discord ID entry.

Rough effort for remaining gaps: S each.

#### A-1 Dashboard — needs deeper audit ❓ Unconfirmed

Dashboard page renders 7 modules via AJAX/skeleton pattern
(`site.py:434-549`). Works end-to-end. Whether it matches the v3
Dashboard restructure target (reordered modules: Top Movers → Recent
Price Updates → Highest Value Cards → Smart Pool Summary → Daily
Summary) is not confirmed.

**Task before scoping.** Have Claude Code compare the current dashboard
structure against §3 A-1 of the original v3 plan and report specific
gaps. Then decide whether to schedule.

#### A-5 Human Review UI ⬜ Not started

Batch actions, keyboard shortcuts (A/O/D), backlog counter, review age
display. `backstage_review_page` exists but shows no signs of these
enhancements.

Rough effort: M.

#### A-3 Signals page — confirmation pass 🚧 Partial

`signals_page` has 10 `ProGate` callsites. Need to audit whether the
Free vs Pro visual hierarchy matches the original v3 spec. If it does,
flip to ✅. If not, scope the gap.

Rough effort: S audit + unknown remediation.

### Phase 3 — Data coverage expansion

#### B-1 Card pool expansion — partial

`set_registry` defines `Jungle`, `Fossil`, and `Team Rocket`, but
`P1_P2_BULK_SET_IDS` only contains Base Set variants (`base1`, `base2`,
`base3`, `base5`). Next expansion tier (Jungle / Fossil / Team Rocket)
not yet moved into the bulk ingestion list.

Rough effort: S (config) + M–L (operational — the real cost is
ingestion runtime, review backlog, and image coverage for new sets).

#### B-3 Image coverage & retry — needs audit

`backfill_retry_service.py` handles price data retries. Whether a
parallel retry mechanism exists for image fetches is not confirmed.
`image_url` is referenced but a dedicated image retry queue was not
located.

**Task before scoping.** Audit: does image backfill currently retry?
If so, where? If not, how often are cards left imageless?

---

## 4. What this plan explicitly does not include

These were in the original v3 doc but are either done, out of scope, or
deliberately deferred:

- **Self-hosted marketplace** — out of scope per original v3 (§8.2).
  Still out of scope.
- **Non-Pokémon expansion** — out of scope per original v3. Still.
- **Real payment integration** — deferred. Manual/mock upgrade flow
  (C-3) is live. Stripe/LemonSqueezy integration is not on this
  roadmap.
- **Full repo refactor** — no. This codebase is production-grade;
  incremental improvement, not rewrites.

---

## 5. Reference

- Agent operating rules: `CLAUDE.md`
- v3.1 architecture migration spec:
  `docs/superpowers/specs/2026-04-17-v31-architecture-migration-design.md`
- Architecture overview: `docs/architecture.md`
- Dev notes: `docs/DEV_NOTES.md`
- Provider evaluation: `docs/current_provider_evaluation.md`
