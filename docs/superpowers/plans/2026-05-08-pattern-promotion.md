# Frontend Pattern Promotion Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Promote three repeatedly-inlined visual patterns in `frontend/src/` (gold-tinted emphasis surfaces, modals, drawer) into reusable CSS classes in `theme.css`, so future a11y/design work happens at one site instead of N sites.

**Why now:** The 2026-05-08 design-system audit (items 1, 2, 4 done) added the underlying tokens. The 2026-05-08 a11y audit's largest deferred item (modal focus traps, TASK-T03 §1) wants `<Dialog>`-style wrapper anyway. Promoting `.modal` first lets that a11y fix touch one file instead of three.

**Architecture:** Three independent extractions, smallest first. Each is its own PR, each ships before the next starts. No new components, no behavior changes — just class extraction. Existing inline styles stay on any site where the class doesn't fit cleanly (per "surgical changes" rule); we don't force consistency.

**Tech Stack:** Plain CSS in `theme.css`; React `className=` swaps in `.tsx` files. No new dependencies.

---

## Component Hierarchy

The new classes layer onto the existing system. Knowing the full map prevents
confusion when choosing which class to use.

```
Badge system:
  .badge (base) ─┬─ .badge-breakout    signal labels
                 ├─ .badge-move
                 ├─ .badge-watch
                 ├─ .badge-idle
                 ├─ .badge-nodata
                 └─ .badge-gold  ← NEW (tier accent, CTA, status pills)

Button system:
  .btn (base) ──┬─ .btn-primary     solid gold fill, highest emphasis
                ├─ .btn-ghost       transparent, lowest emphasis
                └─ .btn-gold-soft  ← NEW (gold-tinted bg, medium emphasis)

Not a class (stays as JS helper — two colour variants, cannot share a single class):
  tierBadge()  → returns inline styles
                  PRO  tier → gold palette (var(--gold), var(--gold-glow))
                  PLUS tier → violet palette (var(--plus), var(--plus-glow))
```

The `tierBadge()` helper is **intentionally excluded** from `.badge-gold` migration.
Reason: the PLUS badge uses the violet token family, not gold. Merging both into
`.badge-gold` would require a colour-modifier prop or two classes (`.badge-gold`,
`.badge-plus`) — adding complexity that isn't justified yet. The helper stays.

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
/* Pill-shaped gold-tinted accent. Use for tier labels, status pills, "coming soon". */
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

/* Compact chip variant with dismiss button. Same gold palette, slightly smaller radius.
   Use for interactive filter chips with × dismiss buttons (DashboardPage active filters).
   Note: the dismiss button goes inside as a sibling; this class does not control it. */
.badge-gold-chip {
  background: var(--gold-glow);
  color: var(--gold);
  border: 1px solid var(--border-gold-soft);
  border-radius: 12px;           /* vs 20px for .badge-gold pill — both pill-like at this size */
  padding: 2px 8px 2px 10px;     /* asymmetric: extra left space for label, tighter right */
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: var(--text-xs);     /* 11px; current inline uses 12px — minor change acceptable */
  max-width: 220px;
  overflow: hidden;
}
```

**Interaction states:**
- `.badge-gold`: no hover state needed — these are non-interactive display elements (PRO label, COMING SOON, GameSwitcher pill).
- `.badge-gold-chip`: no hover needed on the chip itself; the nested `×` dismiss button inherits `.btn:disabled` focus ring via PR #4's global `:focus-visible` rule.
- `.btn-gold-soft`: hover defined (uses `var(--gold-dim)`, which is `rgba(240,180,41,0.25)` — slightly darker than `var(--gold-glow)` default). Disabled state intentionally inherits from `.btn:disabled` (opacity: 0.4, cursor: not-allowed) — no extra CSS required.

**Site scope correction for Task 1:** DashboardPage active filter chip (`DashboardPage.tsx:309–317`, the `Chip` component) migrates to `.badge-gold-chip`, not `.badge-gold`. The sort control buttons at `DashboardPage.tsx:252–268` are NOT in scope — they are `.btn.btn-ghost.btn-sm` buttons with active states, and must remain as-is.

**A11y fix bundled with Task 1:** While migrating the `Chip` component, fix the dismiss `×` button's touch target:
```tsx
// DashboardPage.tsx:317 — change padding: 0 to padding: '4px'
<button onClick={onRemove} style={{ background: 'none', border: 'none',
  color: 'var(--gold)', cursor: 'pointer', padding: '4px',
  fontSize: 16, lineHeight: 1, flexShrink: 0 }}>×</button>
```
This approximately doubles the tap target from ~16px to ~24px. Not 44px but significantly better. Full 44px touch target would require a larger font-size or min-height on the button — defer as a polish item.

- [ ] **Step 1: Add `.badge-gold` to theme.css**

Insert after `.badge-nodata` block (theme.css:167).

**Scope clarifications (design review 2026-05-12):**
- **AIAnalysisSection.tsx** — migrates to `.badge-gold` with `fontSize: 9` inline override
- **LandingPage.tsx "COMING SOON"** — migrates to `.badge-gold`
- **DashboardPage.tsx `Chip` component** — migrates to `.badge-gold-chip` (NOT `.badge-gold` — see class definitions above)
- **`NavBar.tsx` tier badge** — DEFERRED. PR #4 already extracted inline styles into `tierBadge()` helper. The PRO (gold) and PLUS (violet) paths have different colour families; a full migration requires adding `.badge-plus` class first. No change in this task.
- **`GameSwitcher.tsx` active pill** — EXCLUDED. This is a navigation tab (display font, 13px, cursor: pointer), not a static label. Cannot share `.badge-gold`'s mono/11px typography without a visual regression. Leave as-is; raw `rgba(0.35)` border value deferred to PR #5.

**Revised scope: 3 sites (AIAnalysisSection, LandingPage:171, DashboardPage Chip)**

- [ ] **Step 2: Migrate `AIAnalysisSection.tsx` PRO_BADGE**

Delete the `PRO_BADGE: React.CSSProperties` const. Replace both `<span style={PRO_BADGE}>` usages with:
```tsx
<span className="badge-gold" style={{ fontSize: 9 }}>PRO</span>
```
The `fontSize: 9` override stays inline — no token exists below `--text-xs` (11px), and 9px is the intentional small size for this contextual badge.

- [ ] **Step 3: Migrate `LandingPage.tsx:171` "COMING SOON"**

Replace the 100% inline style span with `className="badge-gold"`. The current `borderRadius: 10` rounds to a pill at this element height — effectively same visual as `border-radius: 20px`.

- [ ] **Step 4: Migrate `DashboardPage.tsx` `Chip` component + fix touch target**

Replace inline styles in the `Chip` component at line 309 with `.badge-gold-chip`. **Also fix the dismiss button touch target** (see a11y note above):
```tsx
// The Chip function (line 307–319) becomes:
function Chip({ label, onRemove }: { label: string; onRemove: () => void }) {
  return (
    <span className="badge-gold-chip">
      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{label}</span>
      <button onClick={onRemove} style={{ background: 'none', border: 'none',
        color: 'var(--gold)', cursor: 'pointer', padding: '4px',
        fontSize: 16, lineHeight: 1, flexShrink: 0 }}>×</button>
    </span>
  )
}
```

- [ ] **Step 5: Build + visual diff**

```bash
npm run build
```

Expected: bundle size shrinks (CSS up by ~350 bytes for two classes, JS down by inline style removal). Run `npm run preview` and visually inspect AIAnalysisSection (badge next to "AI Analysis" header), LandingPage Pro card section (COMING SOON pill), and DashboardPage with active filters (filter chips). They should look visually identical.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/styles/theme.css frontend/src/components/AIAnalysisSection.tsx frontend/src/pages/LandingPage.tsx frontend/src/pages/DashboardPage.tsx
git commit -m "refactor(theme): extract .badge-gold + .badge-gold-chip classes (3 sites)"
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

- [ ] **Step 2.5: Fix raw rgba border values in LandingPage.tsx**

While already touching `LandingPage.tsx`, replace the two raw rgba border values with the token:
- `LandingPage.tsx:204`: `border: '1px solid rgba(240,180,41,0.4)'` → `border: '1px solid var(--border-gold-strong)'`
- `LandingPage.tsx:214`: same substitution

Zero visual change (values are identical), eliminates the last raw gold-border literals in the file.

- [ ] **Step 3: Build + visual diff** (same pattern as Task 1).

- [ ] **Step 4: Commit** as `refactor(theme): extract .btn-gold-soft class + fix raw gold-border tokens (4 sites)`.

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

## Order (updated 2026-05-12)

1. Task 1 (`.badge-gold` + `.badge-gold-chip`) — 3 sites (AIAnalysisSection, LandingPage:171, DashboardPage Chip). Includes a11y dismiss-button fix.
2. Task 2 (`.btn-gold-soft`) — 4 sites. Includes raw rgba token fixup in LandingPage.
3. Task 3 (`.surface-emphasis`) — judgment call; ship only if operator agrees with debt-prevention rationale.
4. Task 4 (`.modal-*`) — **DONE** in PR #3/4. Skip.
5. Task 5 (`.drawer-*`) — DEFERRED.

---

## NOT in scope (design review decisions, 2026-05-12)

| Excluded item | Reason |
|---|---|
| `NavBar.tsx` tier badge | `tierBadge()` helper abstracts it; PLUS needs a separate `.badge-plus` class (TASK-T05). Deferred. |
| `GameSwitcher.tsx` active pill | It's a navigation tab, not a static badge. Different font-family (display vs mono), size (13px vs 11px), weight (600 vs 700), and cursor (pointer). `rgba(0.35)` border deferred to PR #5. |
| Sort control buttons `DashboardPage.tsx:252–268` | `.btn.btn-ghost.btn-sm` with active states. Not badge candidates. |
| PR #5 inline styles to tokens (163 remaining sites) | Separate PR. Not blocked on this plan. |
| `--text-2xs` token for 9px font | Single callsite override; a token for 9px adds machinery for a one-off. |

---

## What already exists (leverage in the codebase)

- **Token system** — `--gold`, `--gold-glow`, `--gold-dim`, `--border-gold-soft`, `--border-gold-strong`, `--plus`, `--plus-glow`, `--border-plus-soft` all in `theme.css`
- **Base classes** — `.badge` (base), `.btn` (base) with disabled treatment, `.btn-ghost`, `.btn-primary`, `.btn-sm`
- **Signal badges** — `.badge-breakout`, `.badge-move`, `.badge-watch`, `.badge-idle`, `.badge-nodata` — separate semantics, do not touch
- **Surface system** — `.surface`, `.surface-emphasis`, `.surface-emphasis-firm` already extracted (PR #3)
- **Modal/drawer** — `.modal-backdrop`, `.modal`, `.modal-header`, `.modal-section`, `.drawer-*` already extracted (PR #3/4)
- **Focus ring** — global `:focus-visible` rule already covers all new interactive elements (PR #4)
- **`tierBadge.ts`** — abstracts the NavBar PRO/PLUS badge inline styles. Not touched in this plan; will be the target of TASK-T05.

---

## Verified by

- Pattern inventory: Explore subagent grep across all 25 .tsx files in `frontend/src/`, 2026-05-08.
- Token availability: read of theme.css after items 1+2 ship.
- Tradeoff for Task 3 (single-use extraction): documented in task body.
- Design review: plan-design-review 2026-05-12 (5/10 → 8/10 overall).

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | clean | 6 issues, 0 critical gaps (SCOPE_REDUCED mode) |
| Design Review | `/plan-design-review` | UI/UX gaps | 1 | clean | score: 5/10 → 8/10, 8 decisions |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

**VERDICT: ENG + DESIGN CLEARED — ready to implement.**
