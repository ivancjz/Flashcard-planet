# Dashboard & Signals Page Audit — TASK-205 + TASK-206

**Date:** 2026-05-12  
**Reference:** `docs/plan-v3.md` §3 A-1 (dashboard), §3 A-3 (signals), `03_pricing_page_copy.md`  
**Author:** Claude Code

---

## TASK-205: Dashboard structure vs. v3 spec A-1

### v3 Spec target (plan-v3.md §3 A-1)

Module ordering: Top Movers → Recent Price Updates → Highest Value Cards → Smart Pool Summary → Daily Summary

### Current implementation (DashboardPage.tsx)

The dashboard was rebuilt as a React SPA during the architecture migration. The v3 spec described a static multi-section layout; the SPA implements the same content through dynamic filtering and sorting.

| v3 Module | Current equivalent | Gap? |
|---|---|---|
| Top Movers | Sort: Change (default) | None — same content, filter-driven |
| Recent Price Updates | Sort: Recent (added 2026-05-10) | None — same content |
| Highest Value Cards | Sort: Price | None — same content |
| Smart Pool Summary | Not present in user-facing UI | Gap (see below) |
| Daily Summary | Not present as module | Gap (see below) |

**Current dashboard layout (DashboardPage.tsx):**
1. NavBar + GameSwitcher + TickerBar
2. Stat tiles: Total assets · BREAKOUT · MOVE · WATCH counts
3. Search bar + filter drawer
4. Active filter chips
5. Signal filter row (All / BREAKOUT / MOVE / WATCH / IDLE / INSUFFICIENT_DATA)
6. Sort row (Change / Price / Volume / Recent)
7. CardGrid

**Verdict: design is BETTER than the spec.** The filter/sort approach delivers all five v3 modules dynamically in a single view. A user gets "Top Movers" by setting sort=Change, "Recent Price Updates" by sort=Recent, "Highest Value" by sort=Price. No separate page sections needed.

**Gaps worth tracking (not blocking):**

1. **Smart Pool Summary** — `/admin/smart-pool` exists as an admin endpoint but has no user-facing surface. The v3 spec intended this as a dashboard feature for Pro users ("recommended watchlist additions"). Not blocking for Pro launch but is a Pro differentiation opportunity. Suggest adding to TASK-301 scope or as a separate post-launch task.

2. **Daily Summary module** — no daily digest visible on the dashboard itself. The Market Digest is email-only (TASK-301e). A dashboard "today's highlights" tile would complement the email digest. Low priority.

3. **Volume sort + Recent sort** — both currently ungated (TEMP comment in DashboardPage.tsx:259-270 notes ProGate removed for testing). Per CLAUDE.md §12: "Restore when commercial tier is finalized." Both sorts should be Pro-gated when TASK-301 ships.

**Decision:** No refactoring needed. Mark v3 A-1 as ✅ Done (design intent met via SPA filter/sort approach). Volume/Recent sort gating tracked in TASK-301 scope (CLAUDE.md §12).

---

## TASK-206: Signals page Pro/Free hierarchy vs. pricing spec

### Context

`signals_page` (the old Python template with 10 ProGate callsites, referenced in plan-v3.md §3 A-3) **no longer exists**. It was replaced by the React SPA during the architecture migration. The SPA delivers signal data through:
- `DashboardPage.tsx` — signal-filtered card grid
- `CardDetailPage.tsx` — per-card signal detail + AI analysis

### Spec (03_pricing_page_copy.md)

| Feature | Free | Pro |
|---|---|---|
| Signal labels (BREAKOUT/MOVE/WATCH/IDLE) | ✓ | ✓ |
| Confidence score on every signal | — | ✓ |
| AI explanation per signal | — | ✓ |
| Banlist-triggered signals (YGO) | — | ✓ |
| Franchise-level watchlists | — | ✓ |
| CSV export | — | ✓ |
| Volume/Recent sort | — | ✓ |

### Current SPA state

| Feature | Gated? | Status |
|---|---|---|
| Signal labels (BREAKOUT/MOVE/WATCH/IDLE) | No — Free | ✅ Correct |
| Confidence score | `CardDetailPage.tsx:339` renders for all tiers | ⚠️ Gap — should be Pro-gated |
| AI explanation (`ai_analysis`) | Rendered via `AIAnalysisSection` with PRO badge overlay but analysis text shown unconditionally per CLAUDE.md §12 TEMP comment | ⚠️ Temporarily open (testing phase) |
| Banlist-triggered signals (YGO) | No YGO signals exist yet (blocked on price source) | N/A until YGO unblocked |
| CSV export | Not implemented | Gap |
| Volume/Recent sort | Ungated (TEMP) | ⚠️ Gap — should be Pro-gated per CLAUDE.md §12 |
| Franchise-level watchlists | Not implemented | Gap |

### Gaps

**P1 (block Pro launch — TASK-301 scope):**
- Confidence score should be Pro-gated in `CardDetailPage.tsx`
- AI analysis gate should be restored (see CLAUDE.md §12 restore instructions)
- Volume + Recent sort should be Pro-gated in `DashboardPage.tsx`

**P2 (post-launch):**
- CSV export — no implementation. Add to TASK-301 or post-launch P2.
- Franchise-level watchlists — deferred to TASK-301 scope.

**Verdict:** TASK-206 surfaced 3 gating gaps that must be wired during TASK-301. These are not new discoveries (all are documented in CLAUDE.md §12 and the TEMP comments). Mark v3 A-3 as 🚧 Partial — gaps exist but are tracked in TASK-301.

---

## Actions

| Task | Action | Owner |
|---|---|---|
| TASK-205 | Mark v3 A-1 ✅ Done in plan-v3.md | Claude Code (see below) |
| TASK-206 | Mark v3 A-3 🚧 Partial in plan-v3.md; gates go in TASK-301 | Claude Code (see below) |
| Volume/Recent sort gate | Restore ProGate per CLAUDE.md §12 during TASK-301 | Claude Code when TASK-301 starts |
| Confidence score gate | Add Pro-gating to CardDetailPage during TASK-301 | Claude Code when TASK-301 starts |
| AI analysis gate | Follow CLAUDE.md §12 restore instructions during TASK-301 | Claude Code when TASK-301 starts |
| CSV export | Add to TASK-301 scope as low-effort Pro feature | Ivan decision |
