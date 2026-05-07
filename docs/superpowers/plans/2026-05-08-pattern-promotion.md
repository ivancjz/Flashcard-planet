# Frontend Pattern Promotion Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Promote three repeatedly-inlined visual patterns in `frontend/src/` (gold-tinted emphasis surfaces, modals, drawer) into reusable CSS classes in `theme.css`, so future a11y/design work happens at one site instead of N sites.

**Why now:** The 2026-05-08 design-system audit (items 1, 2, 4 done) added the underlying tokens. The 2026-05-08 a11y audit's largest deferred item (modal focus traps, TASK-T03 §1) wants `<Dialog>`-style wrapper anyway. Promoting `.modal` first lets that a11y fix touch one file instead of three.

**Architecture:** Three independent extractions, smallest first. Each is its own PR, each ships before the next starts. No new components, no behavior changes — just class extraction. Existing inline styles stay on any site where the class doesn't fit cleanly (per "surgical changes" rule); we don't force consistency.

**Tech Stack:** Plain CSS in `theme.css`; React `className=` swaps in `.tsx` files. No new dependencies.

---

## Self-review findings (already addressed inline)

- The original audit said "~4 sites" for Pattern A. The actual inventory found 12 sites split across **three sub-patterns** (badge pill, gold button, emphasis card). Splitting these is the difference between a clean refactor and a bad over-abstraction.
- Pattern B (modal) has 2 sites with diverging z-index (100 vs 1000) and centering strategy (manual vs flex). Parameterise via two `--modal-z-*` variables, not by adding props.
- Pattern C (drawer) is single-use today. Extracting it is debt prevention, not DRY.
- Token additions for this work are already in theme.css (`--border-gold-soft: 0.30`, `--border-gold-strong: 0.40`, `--scrim-light/medium/strong`). Use them.

---

## Task 1: Extract `.badge-gold` (smallest blast radius)

**Files:**
- Modify: `frontend/src/styles/theme.css` (add class)
- Modify: `frontend/src/components/AIAnalysisSection.tsx:5-14` — `PRO_BADGE` const
- Modify: `frontend/src/components/NavBar.tsx:49-56` — PRO/PLUS badge
- Modify: `frontend/src/components/GameSwitcher.tsx:26-27` — active pill
- Modify: `frontend/src/pages/LandingPage.tsx:171` — "COMING SOON" badge
- Modify: `frontend/src/pages/DashboardPage.tsx:309-315` — filter chips

**Class API:**

```css
/* Pill-shaped gold-tinted accent. Use for tier labels, status pills, "coming soon", filter chips. */
.badge-gold {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 20px;
  background: var(--gold-glow);
  color: var(--gold);
  border: 1px solid var(--border-gold-soft);
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  font-weight: 700;
  letter-spacing: 0.04em;
  white-space: nowrap;
}
```

- [ ] **Step 1: Add `.badge-gold` to theme.css**

Insert after `.badge-nodata` block (theme.css:167).

- [ ] **Step 2: Migrate `AIAnalysisSection.tsx` PRO_BADGE**

Replace the 9-prop inline style object with `className="badge-gold"`. Since `PRO_BADGE` is exported as a JSX element, change it from a styled `<span>` to `<span className="badge-gold">PRO</span>`.

- [ ] **Step 3: Migrate `NavBar.tsx` tier badge**

Replace inline style block at line 50-55 with `className="badge-gold"`. Keep the `fontSize: 9` override inline for now (smaller than the default `var(--text-xs)` 11px) — token doesn't have a smaller size and one-off override is fine.

- [ ] **Step 4: Migrate remaining 3 sites**

GameSwitcher active pill, LandingPage "COMING SOON", DashboardPage filter chips. Each should have `className="badge-gold"` plus only the props that legitimately differ (e.g. font-size on the dashboard chip is 12, not 11).

- [ ] **Step 5: Build + visual diff**

```bash
npm run build
```

Expected: bundle size shrinks slightly (CSS up by ~250 bytes, JS down by ~600 bytes after minified inline styles drop). Run `preview_start` and visually inspect each site. They should look identical.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/styles/theme.css frontend/src/components/AIAnalysisSection.tsx frontend/src/components/NavBar.tsx frontend/src/components/GameSwitcher.tsx frontend/src/pages/LandingPage.tsx frontend/src/pages/DashboardPage.tsx
git commit -m "refactor(theme): extract .badge-gold class (5 sites)"
```

---

## Task 2: Extract `.btn-gold-soft` (CTA button variant)

**Files:**
- Modify: `frontend/src/styles/theme.css` — add class after `.btn-ghost`
- Modify: `frontend/src/components/PlusUpgradeModal.tsx:35-45` — "View Plus plans"
- Modify: `frontend/src/components/AIAnalysisSection.tsx:50-51` — "Join the waitlist"
- Modify: `frontend/src/pages/LandingPage.tsx:188, 214` — waitlist confirmation + submit

**Class API:**

```css
/* Tertiary button: gold-tinted background, gold text. Less emphasis than .btn-primary, more than .btn-ghost. */
.btn-gold-soft {
  background: var(--gold-glow);
  color: var(--gold);
  border: 1px solid var(--border-gold-strong);
}
.btn-gold-soft:hover {
  background: var(--gold-dim);
}
```

- [ ] **Step 1: Add `.btn-gold-soft` to theme.css** (after `.btn-ghost:hover`)

- [ ] **Step 2: Migrate 4 sites**

Each site already uses `<a>` or `<button>` — just add `className="btn btn-gold-soft"`. Drop the inline style props that the class now covers (background, border, color). Keep one-off props (padding deltas, fontSize) only when they're already different from the default `.btn`.

- [ ] **Step 3: Build + visual diff** (same pattern as Task 1).

- [ ] **Step 4: Commit** as `refactor(theme): extract .btn-gold-soft class (4 sites)`.

---

## Task 3: Extract `.surface-emphasis` (gold-bordered card)

**Files:**
- Modify: `frontend/src/styles/theme.css` — add class after `.surface`
- Modify: `frontend/src/pages/LandingPage.tsx:168` — Pro plan card

**Class API:**

```css
/* Gold-bordered surface variant for upsell/Pro emphasis cards. Pairs with .surface as a sibling, not a modifier. */
.surface-emphasis {
  background: var(--bg-surface);
  border: 1px solid var(--gold);
  border-radius: var(--radius-lg);
  box-shadow: 0 0 32px var(--gold-glow);
}
```

- [ ] **Step 1: Add class to theme.css**
- [ ] **Step 2: Migrate LandingPage Pro card** — `className="surface-emphasis"`.
- [ ] **Step 3: Build + visual diff**.
- [ ] **Step 4: Commit** as `refactor(theme): extract .surface-emphasis class`.

**Note:** Only 1 site today. Some plan reviewers will say YAGNI here — fair. The reason to extract anyway is that the Pro plan card is a high-touch upsell surface that designers will tweak frequently; a class lets that happen at one place. Drop this task if operator disagrees.

---

## Task 4: Extract `.modal` + `.modal-backdrop` (paired with TASK-T03 §1)

**Sequencing:** This task should ship **with** the modal-a11y PR (TASK-T03 §1), not before. The class extraction without the a11y additions is a refactor that risks merge conflicts when the a11y PR lands; doing them together is one PR and one diff.

**Files:**
- Modify: `frontend/src/styles/theme.css` — add `.modal-backdrop`, `.modal`, `.modal-header`, `.modal-body`
- Modify: `frontend/src/components/CardPickerModal.tsx`
- Modify: `frontend/src/components/PlusUpgradeModal.tsx`

**Class API:**

```css
.modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: var(--scrim-medium);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
}

.modal {
  background: var(--bg-elevated);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  box-shadow: 0 24px 64px rgba(0,0,0,0.6);
  max-width: 480px;
  width: 100%;
  max-height: 80vh;
  overflow: auto;
}
```

- [ ] **Step 1: Add classes to theme.css**
- [ ] **Step 2: Convert CardPickerModal to use `.modal-backdrop` + `.modal`** — drop manual top/left/transform centering in favour of flex centering on backdrop. Verify visually that the modal is still in roughly the same vertical position; "15% from top" → "centered" is a small visual change that should be acknowledged in the commit message.
- [ ] **Step 3: Convert PlusUpgradeModal** — already uses flex centering, this is a near-pure className swap.
- [ ] **Step 4: Add a11y props per TASK-T03 §1** — `role="dialog"`, `aria-modal="true"`, Escape handler, focus trap, focus restoration, body scroll lock.
- [ ] **Step 5: Build + manual test** — open both modals, verify Tab cycles inside, Escape closes, focus returns to trigger.
- [ ] **Step 6: Commit** as `refactor(theme): extract .modal classes + add WCAG dialog semantics`.

---

## Task 5: Extract `.drawer-*` (paired with future drawer reuse)

**Status:** **DEFERRED until a second drawer exists.** Single-use extraction is YAGNI. Keep `FilterDrawer.tsx`'s inline `sectionHead` const + inline styles. Re-evaluate when a settings drawer / filter sheet / etc. is proposed.

This task is documented for completeness; the executor should NOT do it.

---

## Order

1. Task 1 (`.badge-gold`) — easiest, biggest win (5 sites → 1 class).
2. Task 2 (`.btn-gold-soft`) — easy, 4 sites.
3. Task 3 (`.surface-emphasis`) — judgment call; ship only if operator agrees with debt-prevention rationale.
4. Task 4 (`.modal-*`) — paired with TASK-T03 §1, do not ship standalone.
5. Task 5 (`.drawer-*`) — DEFERRED.

## Out of scope

- Tokenising the inline `--gold` opacity values that don't fit `--border-gold-soft/-strong` (e.g. `0.35`). Leave those alone unless they become the third variant.
- Refactoring the existing `.badge-*` classes (badge-breakout, badge-move, etc.). They're separate semantics (signal labels) from `.badge-gold` (tier/CTA accent).
- Migrating any inline style that uses CSS variables directly (e.g. `boxShadow: '0 0 32px var(--gold-glow)'`) but doesn't match a pattern at ≥3 sites.

## Verified by

- Pattern inventory: Explore subagent grep across all 25 .tsx files in `frontend/src/`, 2026-05-08.
- Token availability: read of theme.css after items 1+2 ship.
- Tradeoff for Task 3 (single-use extraction): documented in task body.
