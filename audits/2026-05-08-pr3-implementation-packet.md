# PR #3 implementation packet — `feat/design-primitives`

Date: 2026-05-08
Plan reference: `audits/2026-05-07-design-system-upgrade-plan.md` §PR #3
Locked decisions: chrome-only `.modal` (caller owns padding); `--space-5: 20px` lands here.

Three commits, in order. Each independently verifiable. Run `cd frontend && npm run build && npm test` between commits as a smoke check.

Branch off main:
```
git checkout main && git pull
git checkout -b feat/design-primitives
```

---

## Commit 1 — `feat(theme): add shadow tokens and --space-5 for PR #3 prep`

**Concern:** add the four tokens that PR #3's classes will consume. Pure additive; no consumer changes; zero visual delta.

**File:** `frontend/src/styles/theme.css`

**Edit 1.1** — add `--space-5: 20px` between `--space-4` and `--space-6`:

```css
  /* Spacing scale */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;        /* NEW — most-common inline padding (8 sites in audit) */
  --space-6: 24px;
  --space-8: 32px;
```

**Edit 1.2** — add a Shadows / elevation block after the Typography block (or wherever fits the `:root` organization established in PR #47):

```css
  /* Shadows / elevation */
  --shadow-card:      0 1px 2px rgba(0,0,0,0.30);
  --shadow-modal:     0 24px 64px rgba(0,0,0,0.60);
  --shadow-glow-gold: 0 0 48px rgba(240,180,41,0.12);
```

Rationale for the values:
- `--shadow-modal` matches `CardPickerModal.tsx:71` exactly (`'0 24px 64px rgba(0,0,0,0.6)'`).
- `--shadow-glow-gold` matches `PlusUpgradeModal.tsx:21` exactly (`'0 0 48px rgba(240,180,41,0.12)'`) and is a cleaner alias than reusing `--gold-glow` (which is a *colour*, not a shadow filter).
- `--shadow-card` is a new value, not yet used. Lands here so it exists when the next "lift" affordance ships (e.g., the `CardGrid.tsx:55` JS-set hover shadow). If you'd rather defer it under the dead-config rule (§3), drop just this one line — `.surface-emphasis` and `.modal` don't need it.

**Verified by:**
- `cd frontend && npm run build` — should succeed (`built in <250ms`).
- `npm run dev` then in browser console: `getComputedStyle(document.documentElement).getPropertyValue('--space-5')` → `"20px"`; same for the three shadows.
- `grep -nE '^\s+--shadow-|--space-5' frontend/src/styles/theme.css` returns exactly 4 lines.

**Commit message:**

```
feat(theme): add shadow tokens and --space-5 for PR #3 prep

The audit appendix shows padding: 20 is the most-common inline padding
value (8 sites), but PR #2's spacing scale skipped --space-5. Adding it
here so PR #3's .drawer-header (which uses 20px in FilterDrawer.tsx:99)
can reference it directly.

Three shadow tokens added with values that exactly match existing inline
boxShadow strings in CardPickerModal.tsx:71 and PlusUpgradeModal.tsx:21,
plus one new --shadow-card for future card-lift affordances.

Tokens added:
  --space-5:           20px
  --shadow-card:       0 1px 2px rgba(0,0,0,0.30)
  --shadow-modal:      0 24px 64px rgba(0,0,0,0.60)         (= CardPickerModal.tsx:71)
  --shadow-glow-gold:  0 0 48px rgba(240,180,41,0.12)       (= PlusUpgradeModal.tsx:21)

Pure addition — no consumers changed.

Verified:
- Build: cd frontend && npm run build => no errors
- getComputedStyle resolves all 4 new tokens to expected values
- grep -nE '^\s+--shadow-|--space-5' theme.css => 4 lines
```

---

## Commit 2 — `feat(theme): add .surface-emphasis, .modal*, .drawer* primitive classes`

**Concern:** define the three primitive class families. CSS-only, no JSX/TSX changes; site renders identically because nothing references the new classes yet.

**File:** `frontend/src/styles/theme.css`

**Edit 2.1** — add after the existing `.surface` block:

```css
/* ── Surface variants ── */
.surface-emphasis {
  background: var(--bg-surface);
  border: 1px solid var(--border-gold-soft);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-glow-gold);
}
.surface-emphasis-firm {
  /* For callouts that should feel "claimable" — stronger gold border */
  background: var(--bg-surface);
  border: 1px solid var(--border-gold-strong);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-glow-gold);
}
```

Naming note: uses `--border-gold-{soft,strong}` per the Q1 decision (PR #47 amend) — NOT `--tint-gold-*`.

**Edit 2.2** — add a Modal block:

```css
/* ── Modal scaffold (chrome only — caller owns inner padding) ── */
.modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: var(--scrim-medium);
  backdrop-filter: blur(2px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-4);
}
.modal {
  background: var(--bg-elevated);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-modal);
  max-width: 480px;
  width: 100%;
  overflow: hidden;
}
```

Note: per the chrome-only decision, `.modal` does NOT define `padding`. PlusUpgradeModal will override `max-width` (420) and `border-radius` (--radius-lg) inline; CardPickerModal will override `width` (`min(480px, 94vw)`) inline. Both modals end up visually identical pre/post.

**Edit 2.3** — add a Drawer block:

```css
/* ── Drawer scaffold ── */
.drawer-backdrop {
  position: fixed;
  inset: 0;
  z-index: 200;
  background: var(--scrim-light);
}
.drawer {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  width: clamp(280px, 100vw, 380px);
  background: var(--bg-elevated);
  border-left: 1px solid var(--border-subtle);
  z-index: 201;
  display: flex;
  flex-direction: column;
  overflow-y: hidden;
}
.drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-5) var(--space-5) var(--space-3);
}
.drawer-body {
  flex: 1;
  overflow-y: auto;
  padding: 0 var(--space-5);
}
```

**Verified by:**
- `npm run build` — succeeds.
- Site visual: zero diff (no consumer references the new classes yet).
- `grep -cE '^\.(surface-emphasis|modal|drawer)' frontend/src/styles/theme.css` ≥ 8 (the 8 new class selectors).

**Commit message:**

```
feat(theme): add .surface-emphasis, .modal*, .drawer* primitive classes

Three reusable patterns identified in the 2026-05-07 audit, each
appearing inline in 3+ sites today, get promoted to classes alongside
the existing .btn / .badge / .surface / .nav-link primitives.

Classes added:
  .surface-emphasis        — gold-tinted card scaffold
  .surface-emphasis-firm   — same with firmer border (claimable feel)
  .modal-backdrop / .modal — chrome-only modal scaffold
                             (caller owns inner padding)
  .drawer-backdrop / .drawer / .drawer-header / .drawer-body
                           — side-drawer scaffold

.modal intentionally does NOT define padding — the two existing modals
(PlusUpgradeModal, CardPickerModal) use structurally different inner
layouts; forcing uniform padding would break one or the other.
PlusUpgradeModal will override max-width (420) and border-radius
(--radius-lg) inline; CardPickerModal will override width (min(480px,
94vw)). Both stay visually identical pre/post-migration.

Pure addition — no consumers reference these classes yet (the
migration is a separate commit).

Verified:
- Build: cd frontend && npm run build => no errors
- Visual diff: zero (no consumer references new classes yet)
- grep -cE '^\.(surface-emphasis|modal|drawer)' theme.css >= 8
```

---

## Commit 3 — `refactor(components): migrate gold-tint and modal/drawer scaffolds to design primitives`

**Concern:** swap the inline patterns over to the new classes. Goal: visual zero-diff. Every value that differs from a class default goes into an inline override; document each in the commit message.

### 3.1 — `.surface-emphasis` migrations (4 sites)

**`frontend/src/components/AIAnalysisSection.tsx:7–11`**

The current `boxStyle` constant inlines the gold-tinted surface. Replace the inline border/background/shadow with `className="surface-emphasis"` on the rendered `<div>`. Keep any padding/margin/etc that's already there as inline (the class is chrome-only).

Before:
```tsx
const boxStyle: React.CSSProperties = {
  background: 'var(--bg-surface)',
  border: '1px solid rgba(240,180,41,0.3)',
  borderRadius: 12,
  padding: 20,
  ...
}
```
After:
```tsx
const boxStyle: React.CSSProperties = {
  padding: 20,    // OR use 'var(--space-5)' — preference noted in plan
  ...
}
// In the JSX, the rendered <div> gains className="surface-emphasis"
```

**`frontend/src/components/AIAnalysisSection.tsx:50`** — second gold-bordered container in this file. Same swap pattern.

**`frontend/src/pages/DashboardPage.tsx:308–314`** — gold-tinted callout. Swap to `className="surface-emphasis"`. Confirm the inline `borderRadius` is removed (class supplies `var(--radius-lg)` = 12px, which matches current).

**`frontend/src/pages/LandingPage.tsx:188`** — single gold-tinted callout box. Swap. Note `LandingPage:171, 204, 214` use the `0.4`-alpha border variant — those are `.surface-emphasis-firm` candidates. Recommend migrating LandingPage:171 to `.surface-emphasis-firm` (it's the "COMING SOON" pill, claimable feel); leave LandingPage:204 and :214 inline for now (they're inside the auth-form interactive region — easier to reason about as inline until that page gets its own primitive).

**Visual override audit (preserve pre-migration appearance):**
- AIAnalysisSection currently has `borderRadius: 12` inline → matches class default `--radius-lg`. No override needed.
- DashboardPage uses `borderRadius: 12` → matches. No override.
- LandingPage:188 has `borderRadius: 6` inline → DOES NOT MATCH default. Add `style={{ borderRadius: 'var(--radius-sm)' }}` override.

### 3.2 — `.modal` migrations (2 sites)

**`frontend/src/components/PlusUpgradeModal.tsx`**

Replace the outer fixed-positioned overlay div with `className="modal-backdrop"`, removing the inline `position: fixed; inset: 0; z-index; background; backdropFilter; padding` (all moved to class). Keep the `onClick={e => { if (e.target === e.currentTarget) onClose() }}` handler.

Replace the inner `.surface`-styled div with `className="modal"`. Inline overrides to preserve current visual:
```tsx
style={{
  maxWidth: 420,                       // class default is 480
  borderRadius: 'var(--radius-lg)',    // class default is var(--radius-md)
  border: '1px solid var(--border-gold-soft)',  // class default is --border-default
  boxShadow: 'var(--shadow-glow-gold)', // class default is --shadow-modal
  padding: 32,                          // class has no padding default
}}
```

Note: PlusUpgradeModal currently uses the gold border + gold glow — that's actually the `.surface-emphasis` look applied to a modal. Consider: should this modal use `className="modal surface-emphasis"` (composition)? **No** — `.modal` and `.surface-emphasis` both set `border` and `box-shadow`; cascade order would make it brittle. Cleaner to inline the gold-emphasis bits as overrides. (If this composition pattern shows up a third time, that's the signal to extract `.modal-emphasis`.)

**`frontend/src/components/CardPickerModal.tsx`**

Replace the backdrop div with `className="modal-backdrop"`. Replace the modal div with `className="modal"`. Inline overrides to preserve current visual:
```tsx
style={{
  width: 'min(480px, 94vw)',  // current; class default `width: 100%; max-width: 480px` is close but not identical (the 94vw gutter on small viewports differs)
}}
```

The header / search / list sections inside keep their existing inline `padding` — `.modal` is chrome-only.

### 3.3 — `.drawer` migration (1 site)

**`frontend/src/components/FilterDrawer.tsx:80–105`**

Replace the backdrop `<div>` with `className="drawer-backdrop"`. Replace the panel `<div>` with `className="drawer"`. Replace the header `<div>` with `className="drawer-header"`. Replace the scrollable content `<div>` with `className="drawer-body"`.

Visual override audit:
- Existing header padding is `'20px 20px 14px'` → class default is `var(--space-5) var(--space-5) var(--space-3)` = `20px 20px 12px`. **2px difference at the bottom.** Either accept the round 14→12, or override with `style={{ paddingBottom: 14 }}`. Recommend accept the round (simpler, 2px is below visual-noticeable threshold for this layout).
- Existing body padding is `'0 20px'` → class default is `0 var(--space-5)` = `0 20px`. Matches exactly.
- Existing footer at FilterDrawer:191 has `padding: 20` and `borderTop: '1px solid var(--border-subtle)'` — this is the actions row, NOT covered by `.drawer-header` or `.drawer-body`. Leave it inline (or extract `.drawer-footer` later if a second drawer needs it).

**Verified by:**
- `npm run build && npm test` — pass.
- Side-by-side screenshot: open `/compare` (PlusUpgradeModal triggers via watchlist limit), open `/compare` picker (CardPickerModal), open `/market` filter drawer (FilterDrawer), AI Analysis section on `/market/<assetId>`. All four should be pixel-identical to the pre-merge screenshot — minor exception: FilterDrawer header bottom-padding 14→12 (2px).
- `grep -rE "rgba\(240,180,41,0\.3\)" frontend/src --include="*.tsx"` should drop from 6 to 1–2 (remaining LandingPage uses).
- `grep -rE "rgba\(0,0,0,0\.6[05]\)" frontend/src --include="*.tsx"` should drop to 0 — modal backdrops go through `--scrim-medium` now.

**Commit message:**

```
refactor(components): migrate gold-tint and modal/drawer scaffolds to design primitives

Migrates the three reusable patterns from PR #3 commit 2 to their
class form. Goal: visual zero-diff (with one documented 2px exception
on FilterDrawer header bottom padding).

.surface-emphasis applied to:
  - components/AIAnalysisSection.tsx (2 callsites: lines ~7, ~50)
  - pages/DashboardPage.tsx:308-314
  - pages/LandingPage.tsx:188 (with --radius-sm inline override)
.surface-emphasis-firm applied to:
  - pages/LandingPage.tsx:171 (COMING SOON pill)

.modal / .modal-backdrop applied to:
  - components/PlusUpgradeModal.tsx (with maxWidth, --radius-lg,
    --border-gold-soft, --shadow-glow-gold, padding:32 inline overrides
    to preserve gold-emphasis look)
  - components/CardPickerModal.tsx (with width: min(480px, 94vw)
    inline override)

.drawer / .drawer-header / .drawer-body applied to:
  - components/FilterDrawer.tsx (header, panel, body, backdrop swapped;
    footer left inline)

Preserved overrides documented inline at each site.

Verified:
- Build: cd frontend && npm run build => no errors
- Tests: cd frontend && npm test => all green
- Visual side-by-side at /market, /compare, /market/<id>:
    AIAnalysisSection: pixel-identical
    DashboardPage gold callout: pixel-identical
    LandingPage hero gold pills: pixel-identical
    PlusUpgradeModal: pixel-identical
    CardPickerModal: pixel-identical
    FilterDrawer: header bottom-padding 14px -> 12px (2px diff,
      below visual-noticeable threshold; documented)
- Inline-style cleanup audit:
    grep -rE 'rgba\(240,180,41,0\.3\)' src --include='*.tsx'
      => dropped from 6 to <=2 (remaining: LandingPage non-callout uses)
    grep -rE 'rgba\(0,0,0,0\.6\)' src --include='*.tsx'
      => 0 (modal shadows / scrims all tokenised now)
```

---

## After all 3 commits land on the branch

1. Push: `git push -u origin feat/design-primitives`.
2. Open PR via `gh pr create --base main --title 'feat(theme): design primitives — surface-emphasis, modal, drawer'` (body: copy the three commit messages).
3. Wait 5–10 min for Codex Cloud auto-review per CLAUDE.md §4. Fallback: `@codex review` on PR comment.
4. Merge after review-gate green. Railway auto-deploys.
5. Visual verification on production deploy: the four sites listed above.
6. **Important:** because PR #3 is the first PR that exercises the audit's "zero-visual-diff migration" claim, do a careful walkthrough — any divergence here is a learning signal for PR #5 (the much larger inline-style migration) about what slips through.

---

## What's NOT in this packet (and why)

- **PR #4 (a11y modals)** stays separate. PR #3's modals get class scaffolding now; the `role="dialog"` / `aria-modal` / focus-trap work lands in PR #4 with a single shared `useFocusTrap` hook.
- **CardGrid.tsx hover shadow.** The audit flagged the JS-driven hover shadow at `CardGrid.tsx:55` — the new `--shadow-card` token is sized for that callsite, but migration is part of PR #4's "replace JS hover with CSS hover" sweep, not here.
- **`--motion-*` tokens.** No PR #3 consumer needs them yet. Defer.
- **The remaining `0.4`-alpha gold border sites in LandingPage:204, :214.** They're inside the auth-form interactive region; cleaner to migrate them when that page gets its own primitive (or fold into PR #5).
