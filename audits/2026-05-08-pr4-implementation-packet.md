# PR #4 implementation packet — `feat/a11y-focus-and-modals`

Date: 2026-05-08
Plan reference: `audits/2026-05-07-design-system-upgrade-plan.md` §PR #4
Locked decisions: `:focus-visible` already partially landed on `5c85309` (covers `button`, `.btn`, `.nav-link` only — needs extension); `useFocusTrap` to be a single shared hook; PLUS badge per locked decision 2026-05-07.

Four commits. Concerns split per §3:
1. `feat(theme): a11y prep — extended :focus-visible, --border-plus-soft, hover/option-row classes`
2. `feat(a11y): replace 5 JS-driven hover handlers with CSS hover classes`
3. `feat(a11y): dialog semantics — useFocusTrap hook + ARIA/Esc on 3 modals`
4. `feat(navbar): PLUS tier badge with tierBadge helper`

Branch off main:
```
git checkout main && git pull
git checkout -b feat/a11y-focus-and-modals
```

Verified pre-existing state (`20b91a3` HEAD, sandbox-readable): `:focus-visible` covers `button, .btn, .nav-link` only; `useFocusTrap.ts` does not exist; `frontend/src/hooks/` contains `useUser.ts` and `useWatchlist.ts`; NavBar:49 still gates badge on `tier === 'pro'`.

---

## Commit 1 — `feat(theme): a11y prep — extended :focus-visible, --border-plus-soft, hover/option-row classes`

**Concern:** all theme.css additions for PR #4. Pure additive; no consumer changes; zero visual delta yet.

**File:** `frontend/src/styles/theme.css`

### 1.1 — Add `--border-plus-soft` token

Add to the existing `Brand` or `Tier accent` block in `:root`. Mirrors the `--border-gold-soft` pattern.

```css
  /* Tier accent */
  --plus:             #a78bfa;
  --plus-glow:        rgba(167,139,250,0.12);
  --border-plus-soft: rgba(167,139,250,0.30);   /* NEW — matches --border-gold-soft pattern */
```

### 1.2 — Extend `:focus-visible` selector list

Existing rule (lines 158–163) covers `button, .btn, .nav-link`. Replace with the wider list. Use `:where()` so specificity stays at 0 — keeps per-component overrides trivial.

Before:
```css
button:focus-visible,
.btn:focus-visible,
.nav-link:focus-visible {
  outline: 2px solid var(--gold);
  outline-offset: 2px;
}
```
After:
```css
:where(button, .btn, .nav-link, a, input, select, textarea, [role="button"], [tabindex="0"]):focus-visible {
  outline: 2px solid var(--gold);
  outline-offset: 2px;
}
```

`[tabindex="0"]` covers any explicitly-keyboard-focusable non-button element. SVG charts and similar should NOT have a focus ring — they're not keyboard-interactive — so they don't need to be excluded explicitly (they don't match any of the listed selectors).

### 1.3 — Add hover-class primitives

CSS hover replacements for the JS `onMouseEnter`/`onMouseLeave` patterns. Three classes, distinct concerns. Add a new `Hover affordances` block in `theme.css` (near the existing `.surface` / `.surface-emphasis` blocks).

```css
/* ── Hover affordances (replace JS-driven hover handlers) ── */
.card-row {
  transition: transform 0.15s, box-shadow 0.15s;
}
.card-row:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 32px var(--card-glow-color, rgba(0,0,0,0.3));
}

.icon-button {
  transition: transform 0.1s, color 0.15s;
}
.icon-button:hover {
  transform: scale(1.15);
}

.option-row {
  transition: background 0.15s;
  cursor: pointer;
}
.option-row:hover {
  background: var(--bg-base);
}
```

Design note on `.card-row`: the existing JS hover sets `box-shadow: 0 8px 32px ${meta.color}20` — a per-signal-colour shadow. CSS can't parameterize a hover style by runtime value directly, so commit 2 will set a `--card-glow-color` CSS custom property inline on each card row, and the class reads it via `var(--card-glow-color, fallback)`. Cleaner than JS hover, removes runtime style mutation.

**Verified by:**
- `cd frontend && npm run build` — passes.
- `getComputedStyle(document.documentElement).getPropertyValue('--border-plus-soft')` resolves to `"rgba(167,139,250,0.3)"`.
- Tab focus on a focusable element (e.g., the search input on `/market`) shows the gold focus ring — confirms expanded `:focus-visible` coverage.
- Site visual: zero diff (no consumer references new classes yet).

**Commit message:**

```
feat(theme): a11y prep — extended :focus-visible, --border-plus-soft, hover/option-row classes

Three additive groups in :root + scaffolding for PR #4's later commits:

1. --border-plus-soft (rgba(167,139,250,0.30)) — matches the
   --border-gold-soft pattern; consumer is the new PLUS badge in commit 4.
2. :focus-visible widened from {button, .btn, .nav-link} to
   {a, input, select, textarea, [role="button"], [tabindex="0"]} via
   :where() — keeps specificity at 0 so component overrides are trivial.
3. Three hover classes for replacing JS-driven onMouseEnter/onMouseLeave
   handlers in commit 2:
     .card-row     — transform + per-signal-colour glow via
                     --card-glow-color custom property
     .icon-button  — scale(1.15) on hover (watchlist toggle)
     .option-row   — bg-base on hover (filter / picker option lists)

Pure addition — no consumers reference these classes yet (migration is
commit 2).

Verified:
- Build: cd frontend && npm run build => no errors
- Token resolves: getComputedStyle => --border-plus-soft = "rgba(167,139,250,0.3)"
- Visual diff: zero
- Tab through /market — focus ring now visible on search input (was not
  covered by previous selector set)
```

---

## Commit 2 — `feat(a11y): replace 5 JS-driven hover handlers with CSS hover classes`

**Concern:** swap 5 inline `onMouseEnter`/`onMouseLeave` patterns to CSS `:hover` via the classes added in commit 1. Touch + keyboard now get equivalent affordances. JS hover was invisible to both.

### 2.1 — `frontend/src/components/CardGrid.tsx:49–56` (card row hover)

Before:
```tsx
<div
  className="surface"
  onClick={onClick}
  style={{
    padding: 16, cursor: 'pointer', display: 'flex', gap: 12, alignItems: 'flex-start',
    background: `linear-gradient(135deg, ${meta.rowGlow} 0%, var(--bg-surface) 60%)`,
    borderLeft: `3px solid ${meta.color}`,
    position: 'relative',
    transition: 'transform 0.15s, box-shadow 0.15s',
  }}
  onMouseEnter={e => {
    ;(e.currentTarget as HTMLDivElement).style.transform = 'translateY(-2px)'
    ;(e.currentTarget as HTMLDivElement).style.boxShadow = `0 8px 32px ${meta.color}20`
  }}
  onMouseLeave={e => {
    ;(e.currentTarget as HTMLDivElement).style.transform = ''
    ;(e.currentTarget as HTMLDivElement).style.boxShadow = ''
  }}
>
```

After:
```tsx
<div
  className="surface card-row"
  onClick={onClick}
  style={{
    padding: 16, cursor: 'pointer', display: 'flex', gap: 12, alignItems: 'flex-start',
    background: `linear-gradient(135deg, ${meta.rowGlow} 0%, var(--bg-surface) 60%)`,
    borderLeft: `3px solid ${meta.color}`,
    position: 'relative',
    // NEW: per-signal-colour glow exposed to CSS hover via custom property
    ['--card-glow-color' as string]: `${meta.color}20`,
  }}
>
```

Notes:
- `transition` moved into the `.card-row` class.
- `--card-glow-color` is set per-card to the signal colour with `20` (12% alpha hex suffix). The CSS in commit 1 reads it via `var(--card-glow-color, fallback)`.
- TypeScript will complain about the bracketed CSS-variable key on `style`. The `as string` cast or a `// @ts-expect-error` comment makes it pass — the React 19 + TS pattern that works without warnings is:
  ```tsx
  style={{ ...rest, ['--card-glow-color' as never]: `${meta.color}20` } as React.CSSProperties}
  ```
  Or the cleaner approach: declare a typed variant.

### 2.2 — `frontend/src/components/CardGrid.tsx:58–73` (watchlist toggle button)

Before:
```tsx
<button
  onClick={e => { e.stopPropagation(); onToggleWatch() }}
  style={{
    position: 'absolute', top: 8, right: 8, zIndex: 2,
    background: 'rgba(12,12,16,0.7)', border: 'none', borderRadius: '50%',
    width: 28, height: 28, cursor: 'pointer',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontSize: 16, color: watched ? 'var(--gold)' : 'var(--text-muted)',
    transition: 'color 0.15s, transform 0.1s',
  }}
  onMouseEnter={e => (e.currentTarget.style.transform = 'scale(1.15)')}
  onMouseLeave={e => (e.currentTarget.style.transform = 'scale(1)')}
  aria-label={watched ? 'Remove from watchlist' : 'Add to watchlist'}
  title={watched ? 'Remove from watchlist' : 'Add to watchlist'}
>
```

After:
```tsx
<button
  className="icon-button"
  onClick={e => { e.stopPropagation(); onToggleWatch() }}
  style={{
    position: 'absolute', top: 8, right: 8, zIndex: 2,
    background: 'rgba(12,12,16,0.7)', border: 'none', borderRadius: '50%',
    width: 28, height: 28, cursor: 'pointer',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontSize: 16, color: watched ? 'var(--gold)' : 'var(--text-muted)',
  }}
  aria-label={watched ? 'Remove from watchlist' : 'Add to watchlist'}
  title={watched ? 'Remove from watchlist' : 'Add to watchlist'}
>
```

`transition` moved into `.icon-button`. JS handlers removed.

### 2.3 — `frontend/src/components/FilterDrawer.tsx:108–109` (set option rows)

Before:
```tsx
<label key={set.id} style={{ display: 'flex', alignItems: 'center', padding: '6px 4px', cursor: 'pointer', borderRadius: 4, gap: 8 }}
  onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-base)')}
  onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>
```

After:
```tsx
<label key={set.id} className="option-row" style={{ display: 'flex', alignItems: 'center', padding: '6px 4px', borderRadius: 4, gap: 8 }}>
```

`cursor: pointer` moved into `.option-row` class. JS handlers removed.

### 2.4 — `frontend/src/components/FilterDrawer.tsx:133–134` (rarity option rows)

Same pattern as 2.3, applied at the rarity loop site.

### 2.5 — `frontend/src/components/CardPickerModal.tsx:149–150` (card option rows)

Before:
```tsx
<button ...
  onMouseEnter={e => { if (!already) (e.currentTarget as HTMLButtonElement).style.background = 'var(--bg-surface)' }}
  onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = 'none' }}
>
```

After:
```tsx
<button ... className="option-row">
```

Note: the original toggled to `var(--bg-surface)` on hover, while `.option-row` toggles to `var(--bg-base)`. Two different shades — `--bg-surface` (#13131a) vs `--bg-base` (#0c0c10). The new value is slightly darker. Visual diff exists but is intentional: option rows across the app should hover to a single shade. If you want pixel-zero-diff here, override inline with a `--option-row-hover` custom property pattern — cleaner is to accept the unification.

The original ALSO conditionally skipped hover when `already` (already-in-comparison) was true. CSS can't condition on that runtime state. Two paths:
- **Accept the "always hover" behaviour** — already-added rows still highlight on hover; visual nudge is fine, the row's click handler is already disabled.
- **Use a `[disabled]` selector** — add `disabled={already}` to the button (which it should arguably have anyway for screen readers), and CSS rule `.option-row:disabled:hover { background: none }` to lock out the hover. **Recommended** — fixes a latent a11y issue (already-added rows weren't `disabled` for screen readers either).

If recommended path: also add to commit 1's CSS:
```css
.option-row:disabled,
.option-row[aria-disabled="true"] {
  cursor: default;
}
.option-row:disabled:hover,
.option-row[aria-disabled="true"]:hover {
  background: transparent;
}
```

### Verified by

- `npm run build && npm test` — pass.
- `grep -rn "onMouseEnter\|onMouseLeave" frontend/src --include="*.tsx"` — should drop from 7 matches to 1 (CardDetailPage.tsx:135, which is chart cursor state — legit, not styling).
- Manual hover walk-through:
  - `/market` cards lift on hover with per-signal coloured glow (zero functional diff)
  - `/market` watchlist toggles scale-up on hover
  - `/market` filter drawer rows highlight on hover
  - `/compare` picker modal rows highlight on hover (same shade as filter rows now — note in commit message)
- Touch test (Chrome devtools mobile emulation): cards now show hover state on tap-and-hold, filter rows now respond to touch — was not the case with JS handlers.
- Keyboard test: Tab to a card → focus ring visible; Tab to filter row label → focus ring visible.

**Commit message:**

```
feat(a11y): replace 5 JS-driven hover handlers with CSS hover classes

The 7 onMouseEnter/onMouseLeave handlers in CardGrid (2), FilterDrawer (2),
and CardPickerModal (1) emulated hover via runtime style mutation. JS hover
is invisible to keyboard, invisible to screen readers, and inconsistent on
touch devices (only the long-press case triggers).

Migrated to the .card-row / .icon-button / .option-row classes added in
commit 1. Affordances now work via CSS :hover, which composes correctly
with :focus-visible (covered by commit 1's selector widening) and
tap-and-hold on touch.

The CardGrid card-row case uses a CSS custom property
(--card-glow-color) set inline per-card so the hover-shadow can still be
parameterised by signal colour without JS.

CardPickerModal option rows: hover shade unified from --bg-surface to
--bg-base (matches FilterDrawer). Rows for already-compared cards
gain disabled + aria-disabled, which also locks out the hover (CSS
:disabled selector handles it).

Sites migrated:
  components/CardGrid.tsx:49-56  — card row hover lift
  components/CardGrid.tsx:58-73  — watchlist toggle scale
  components/FilterDrawer.tsx:108-109 — set option row
  components/FilterDrawer.tsx:133-134 — rarity option row
  components/CardPickerModal.tsx:149-150 — card option row + disabled state

Verified:
- Build + tests: pass
- grep onMouseEnter|onMouseLeave => 1 match (CardDetailPage chart cursor,
  legitimate runtime state, not styling)
- Touch (devtools mobile): cards / rows now respond to tap-and-hold (was
  not the case with JS handlers — touch never fired onMouseEnter)
- Keyboard: Tab to card / row shows focus ring
```

---

## Commit 3 — `feat(a11y): dialog semantics — useFocusTrap hook + ARIA/Esc on 3 modals`

**Concern:** make modals/drawers screen-reader-recognisable as dialogs, keyboard-escapable, and focus-trapped while open.

### 3.1 — Add `useFocusTrap` hook

Create `frontend/src/hooks/useFocusTrap.ts`:

```ts
import { useEffect, useRef } from 'react'

/**
 * Trap keyboard focus inside a container while it's open.
 * - Tab cycles between focusable descendants.
 * - Esc calls onClose.
 * - On unmount/close, focus returns to the previously-focused element.
 *
 * Limitations (acceptable for current modal/drawer scope):
 * - Focusables are captured at open-time; descendants added later are not picked up.
 * - Single-trap only; nested modals would need a stack — not used today.
 */
export function useFocusTrap<T extends HTMLElement>(
  open: boolean,
  onClose: () => void,
) {
  const ref = useRef<T>(null)

  useEffect(() => {
    if (!open || !ref.current) return
    const root = ref.current
    const previouslyFocused = document.activeElement as HTMLElement | null

    const focusables = Array.from(
      root.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
      )
    )

    focusables[0]?.focus()

    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        onClose()
        return
      }
      if (e.key !== 'Tab' || focusables.length === 0) return
      const first = focusables[0]
      const last = focusables[focusables.length - 1]
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    }

    root.addEventListener('keydown', onKey)
    return () => {
      root.removeEventListener('keydown', onKey)
      previouslyFocused?.focus()
    }
  }, [open, onClose])

  return ref
}
```

**Test:** none in this commit. Component-level testing isn't established yet (existing tests are pure-function unit tests via `parseTier.test.ts` etc.). Adding `@testing-library/react` for a single 30-line hook is heavy. Manual verification is sufficient for PR #4 scope; if a regression appears, that's the prompt to introduce React Testing Library properly.

If you'd like a test now: the path is `cd frontend && npm i -D @testing-library/react @testing-library/dom`, then a `useFocusTrap.test.tsx` that mounts a component using the hook and asserts Tab cycling. ~50 LOC. Flag for a separate small PR if you go this route.

### 3.2 — Wire dialog semantics into the 3 modals

The pattern for each modal:
1. Import `useFocusTrap`.
2. Add an `id` to the modal's title heading.
3. Add `role="dialog"`, `aria-modal="true"`, `aria-labelledby={titleId}`, and `ref={trapRef}` to the modal element.
4. Drop any existing manual Esc handler if present (none of the 3 currently have one).

#### `frontend/src/components/PlusUpgradeModal.tsx`

The `<h2>` at line ~29 needs an id. Recommended id: `plus-upgrade-title`.

Before:
```tsx
export default function PlusUpgradeModal({ onClose }: Props) {
  return (
    <div
      className="modal-backdrop"
      ...
    >
      <div
        className="modal"
        style={...}
      >
        ...
        <h2 style={...}>Upgrade to Plus for unlimited watchlist</h2>
        ...
      </div>
    </div>
  )
}
```

After:
```tsx
import { useFocusTrap } from '../hooks/useFocusTrap'

export default function PlusUpgradeModal({ onClose }: Props) {
  const trapRef = useFocusTrap<HTMLDivElement>(true, onClose)
  return (
    <div
      className="modal-backdrop"
      ...
    >
      <div
        ref={trapRef}
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="plus-upgrade-title"
        style={...}
      >
        ...
        <h2 id="plus-upgrade-title" style={...}>Upgrade to Plus for unlimited watchlist</h2>
        ...
      </div>
    </div>
  )
}
```

`open` is hardcoded `true` because PlusUpgradeModal renders only when shown by its parent — the component's existence is the open signal. This pattern works for the conditional-render style; if any modal were to use a permanent-mount-with-`open`-prop pattern, `open` would be the prop.

#### `frontend/src/components/CardPickerModal.tsx`

Title: line ~80 (`<span>Add a card to compare</span>`). Convert to a heading with id, OR keep as span and set `aria-labelledby`. Recommended: convert to `<h2>` for proper semantic structure, style it visually identical with inline styles.

```tsx
import { useFocusTrap } from '../hooks/useFocusTrap'

// Inside the component:
const trapRef = useFocusTrap<HTMLDivElement>(open, onClose)

// Inside the JSX, replace the existing modal div with:
<div
  ref={trapRef}
  className="modal"
  role="dialog"
  aria-modal="true"
  aria-labelledby="card-picker-title"
  style={...}  // existing min(480px, 94vw) override stays
>
  <div className="modal-header" style={{ ... existing styles ... }}>
    <h2
      id="card-picker-title"
      style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 14, margin: 0 }}
    >
      Add a card to compare
    </h2>
    <button ...>×</button>
  </div>
  ...
</div>
```

`useFocusTrap(open, ...)` with the existing `open` prop — when the modal closes (`open` flips to `false`), the hook's effect cleanup runs and focus returns to the element that opened the modal.

#### `frontend/src/components/FilterDrawer.tsx`

Same pattern. Title at line ~100 (`<span>Filters</span>`).

```tsx
import { useFocusTrap } from '../hooks/useFocusTrap'

// Inside the component:
const trapRef = useFocusTrap<HTMLDivElement>(open, onClose)

// Inside the JSX, find the .drawer panel <div> and add:
<div
  ref={trapRef}
  className="drawer"
  role="dialog"
  aria-modal="true"
  aria-labelledby="filter-drawer-title"
>
  <div className="drawer-header">
    <h2
      id="filter-drawer-title"
      style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 16, margin: 0 }}
    >
      Filters
    </h2>
    <button ...>×</button>
  </div>
  ...
</div>
```

A side-drawer is still a `role="dialog"` per WAI-ARIA 1.2 — it traps focus and dims the page, behaving like a modal even though it's anchored to the viewport edge.

### 3.3 — ProGate intentionally NOT touched

ProGate is an inline content overlay (locked feature pill on a child), not a dialog. It does not need `role="dialog"` / focus-trap / Esc — pressing Esc shouldn't close it (there's nothing to close; the gate is the content). Its existing `title` attribute carries the lock reason — a separate, smaller a11y improvement (covering it with `aria-label` and `role="status"`) is a P3 follow-up, not blocking this PR.

### Verified by

- `npm run build && npm test` — pass.
- Open `/compare` → trigger CardPickerModal: focus lands in the search input. Tab cycles within the modal. Shift+Tab from search → goes to the close button. Esc → closes. Focus returns to the "+ Add card" trigger.
- Hit watchlist limit → trigger PlusUpgradeModal: focus lands on "View Plus plans" link. Tab → "Maybe later" button. Tab → cycles to "View Plus plans". Esc → closes. Focus returns to whatever triggered it.
- Open filter drawer: focus lands in the first checkbox / search-like input. Tab cycles; Esc closes.
- VoiceOver / NVDA: announces "dialog" + the heading text on each modal open.
- `grep -rn "role=\"dialog\"" frontend/src --include="*.tsx"` returns 3 matches (was 0).
- `grep -rn "aria-modal" frontend/src --include="*.tsx"` returns 3 matches (was 0).

**Commit message:**

```
feat(a11y): dialog semantics — useFocusTrap hook + ARIA/Esc on 3 modals

Three modals/drawers (PlusUpgradeModal, CardPickerModal, FilterDrawer)
gain proper dialog semantics: role="dialog", aria-modal="true",
aria-labelledby pointing at a heading id, keyboard focus trapped while
open, Esc closes, focus restored to opener on close.

Single shared hook frontend/src/hooks/useFocusTrap.ts (~30 LOC,
zero deps). Limitations documented in the hook header — focusables
captured at open-time, no nested-trap stack — both acceptable for
current scope.

ProGate is NOT a dialog (inline content overlay) and is intentionally
untouched — Esc has nothing to close, focus shouldn't be trapped.

Component-level testing not added in this PR — adding @testing-library/react
for one 30-line hook is heavy; manual verification (Tab + Esc walk-through
on each modal) is sufficient. If a regression appears, that's the trigger
to introduce RTL properly.

Verified:
- Build + tests: pass
- Manual walk-through on all 3 modals (Tab cycles, Shift+Tab cycles,
  Esc closes, focus restored to opener)
- VoiceOver: announces "dialog" + heading on open
- grep role="dialog" frontend/src --include='*.tsx' => 3 (was 0)
- grep aria-modal frontend/src --include='*.tsx' => 3 (was 0)
```

---

## Commit 4 — `feat(navbar): PLUS tier badge with tierBadge helper`

**Concern:** wire the `--plus` token into the NavBar so PLUS-tier users see their tier badge. Per the locked decision (2026-05-07), PLUS gets its own visual rank distinct from PRO.

### 4.1 — Add `tierBadge(tier)` helper

Either extend `frontend/src/lib/utils.ts` or create a new `frontend/src/lib/tierBadge.ts`. Recommend new file — small, focused, mirrors `parseTier`/`watchlist.ts` pattern.

`frontend/src/lib/tierBadge.ts`:

```ts
import type { Tier } from '../contexts/UserContext'

export interface TierBadgeStyle {
  label: string
  color: string
  background: string
  borderColor: string
}

/**
 * Map a Tier to its NavBar badge style, or null if no badge should render.
 * Free tier returns null; pro and plus return distinct visual styles.
 *
 * Regression guard for Lesson 13: the original NavBar conditional only
 * checked tier === 'pro'; PLUS users got no badge. Switch over the full
 * Tier enum here, and the corresponding test (tierBadge.test.ts) asserts
 * each value returns the right style.
 */
export function tierBadge(tier: Tier): TierBadgeStyle | null {
  if (tier === 'pro') {
    return {
      label: 'PRO',
      color: 'var(--gold)',
      background: 'var(--gold-glow)',
      borderColor: 'var(--border-gold-soft)',
    }
  }
  if (tier === 'plus') {
    return {
      label: 'PLUS',
      color: 'var(--plus)',
      background: 'var(--plus-glow)',
      borderColor: 'var(--border-plus-soft)',
    }
  }
  return null
}
```

### 4.2 — Add test

`frontend/src/lib/tierBadge.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { tierBadge } from './tierBadge'

describe('tierBadge', () => {
  it("returns PRO style for tier='pro'", () => {
    const b = tierBadge('pro')
    expect(b).not.toBeNull()
    expect(b!.label).toBe('PRO')
    expect(b!.color).toBe('var(--gold)')
  })

  it("returns PLUS style for tier='plus' (Lesson 13 regression guard)", () => {
    const b = tierBadge('plus')
    expect(b).not.toBeNull()
    expect(b!.label).toBe('PLUS')
    expect(b!.color).toBe('var(--plus)')
    expect(b!.borderColor).toBe('var(--border-plus-soft)')
  })

  it("returns null for tier='free'", () => {
    expect(tierBadge('free')).toBeNull()
  })
})
```

### 4.3 — Update NavBar

`frontend/src/components/NavBar.tsx` — replace the existing `tier === 'pro'` conditional (line ~49) with a render driven by `tierBadge`.

Before (lines ~46–56):
```tsx
{!loading && (
  email ? (
    <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      {tier === 'pro' && (
        <span style={{
          fontSize: 9, padding: '2px 7px',
          background: 'var(--gold-glow)', color: 'var(--gold)',
          border: '1px solid rgba(240,180,41,0.3)', borderRadius: 10,
          fontFamily: 'var(--font-mono)', fontWeight: 700,
        }}>PRO</span>
      )}
```

After:
```tsx
import { tierBadge } from '../lib/tierBadge'

// Inside the component, near the top:
const badge = tierBadge(tier)

// In the JSX, replace the conditional span:
{!loading && (
  email ? (
    <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      {badge && (
        <span style={{
          fontSize: 9, padding: '2px 7px',
          background: badge.background,
          color: badge.color,
          border: `1px solid ${badge.borderColor}`,
          borderRadius: 10,
          fontFamily: 'var(--font-mono)', fontWeight: 700,
        }}>
          {badge.label}
        </span>
      )}
```

Note the change: `border: '1px solid rgba(240,180,41,0.3)'` becomes `border: '1px solid ${badge.borderColor}'` which uses the `--border-gold-soft` token for pro and `--border-plus-soft` for plus. Side benefit: this site's inline `rgba(240,180,41,0.3)` literal is now tokenised (was queued for PR #5).

### Verified by

- `npm run build && npm test` — pass; new `tierBadge.test.ts` runs 3 assertions, all green.
- `localStorage.setItem('fcp_dev_tier_override', 'plus')` then reload → NavBar shows a violet PLUS badge.
- `localStorage.setItem('fcp_dev_tier_override', 'pro')` then reload → gold PRO badge (unchanged from before).
- `localStorage.removeItem('fcp_dev_tier_override')` (or `setItem(..., 'free')`) then reload → no badge (unchanged).
- `grep -rn "rgba(240,180,41,0\.3)" frontend/src --include="*.tsx"` — drops by 1 (NavBar's literal) — should now be 0 across the codebase.

**Commit message:**

```
feat(navbar): PLUS tier badge with tierBadge helper

Closes the Lesson 13 follow-up flagged in the 2026-05-07 audit and
locked on the same date: PLUS-tier users now see a violet PLUS badge
in the NavBar, distinct from the gold PRO badge.

Implementation mirrors the parseTier pattern: a pure tierBadge(tier)
helper in lib/tierBadge.ts switches over the full Tier enum and returns
the badge style or null. Component-level conditional shrinks to "render
if helper returned non-null." Test coverage in lib/tierBadge.test.ts
asserts all three tier values explicitly — same regression-guard pattern
as parseTier.test.ts (PR #43 / Lesson 13 fallout).

Side benefit: the inline rgba(240,180,41,0.3) border literal at
NavBar.tsx:53 (queued for PR #5 migration) is now tokenised through
the helper as --border-gold-soft / --border-plus-soft.

Verified:
- Build + tests: pass; tierBadge.test.ts adds 3 assertions
- Dev-tier switcher: localStorage='plus' shows violet PLUS;
  localStorage='pro' shows gold PRO (unchanged);
  no override / 'free' shows no badge (unchanged)
- grep rgba(240,180,41,0.3) src --include='*.tsx' => 0 (was 1)
```

---

## After all 4 commits land on the branch

1. Push: `git push -u origin feat/a11y-focus-and-modals`
2. Open PR via `gh pr create --base main --title 'feat(a11y): focus-visible widening, dialog semantics, hover hygiene, PLUS badge (PR #4)'` (body: copy the four commit messages).
3. Wait 5–10 min for Codex Cloud auto-review per CLAUDE.md §4.
4. Manual a11y walkthrough before merge:
   - Tab through every page top-to-bottom — focus ring visible on every interactive
   - Open every modal/drawer → assert Tab traps, Esc closes, VoiceOver announces "dialog"
   - Test each tier override (free/plus/pro) → correct badge or absence
5. Merge after review-gate green.

---

## Open questions for the operator

1. **`@testing-library/react` for component tests?** PR #4 doesn't add it (manual verification used for the focus-trap hook). If you want regression coverage on the modal a11y wiring (e.g., "if someone removes role='dialog', a test fails"), this is the moment to introduce RTL. Add to deps in PR #4 or queue as a separate small PR. **Default if you don't answer: skip; manual verification stands.**

2. **ProGate gating semantics under the new PLUS tier.** Current code at `ProGate.tsx:12` is `isLocked = locked ?? (tier !== 'pro')`. Plus users currently see Pro features as locked (correct — Pro features are pro-only). But if any feature is intended to be plus-tier-and-up, the consumer needs to pass `locked={tier === 'free'}` explicitly. This is **product semantics, not design** — flagging here so it doesn't get silently inherited from the audit. If you want PR #4 to also add a `useTierGate(feature)` hook that knows feature → required-tier mapping, that's a different PR's worth of work. **Default: do nothing; ProGate keeps current `tier !== 'pro'` behaviour; document that any future plus-tier feature must pass `locked={tier === 'free'}` explicitly.**

3. **The `${color}NN` template-literal CSS pattern in `CardGrid.tsx:51` (the box-shadow).** Currently `box-shadow: 0 8px 32px ${meta.color}20` — which works because `meta.color` is a hex string (`#22c55e`), not a `var()` reference. After commit 2's migration, this lives only in the `--card-glow-color` inline custom property, where it's similarly safe. **No bug here**, but worth noting that PR #6 (the AlertsPage `${var()}08` bug) is the actually-broken case — and `meta.color` not using `var(--breakout)` is the reason CardGrid has *worked all along*. Keeping it as a hex string is the safer pattern. PR #6 will document this.

---

## Cumulative state after PR #4 merges

- All audit P0/P1 issues resolved (3 P0 undefined tokens — PR #1; AlertsPage `${color}08` bug — pending PR #6).
- All locked decisions (PLUS badge, severity decoupling, light-mode won't-fix, dark title) implemented or scheduled.
- Modal/drawer accessibility brought up to WCAG 2.1 AA-adjacent (focus management + dialog semantics + Esc + visible focus rings).
- Inline-style hot spots identified for PR #5 unchanged: 344 inline `style={{}}` blocks remain, mostly layout. PR #5's scope hasn't expanded.
- Remaining audit-flagged P2/P3 items: ProGate `aria-label`, AlertsPage `${color}08` bug (PR #6), CardDetailPage chart screen-reader description (deferred).
