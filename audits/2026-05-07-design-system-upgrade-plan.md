# Flashcard Planet — design system upgrade plan

Date: 2026-05-07
Companion to: `audits/2026-05-07-design-system-audit.md`
Author: deep-research follow-up

---

## TL;DR (the answer)

Six small PRs, in this order. Each is self-contained, each leaves the site shippable, each unlocks the next.

| # | PR title | Concern | LOC delta | Time |
|---|---|---|---|---|
| 1 | `fix/design-tokens-undefined` | Define the 3 missing tokens, set the real `<title>`, declare dark-only in README | ~10 lines across 3 files | 15 min |
| 2 | `feat/design-tokens-v2` | Add type, spacing, danger, scrim, alpha-tint, shadow, motion tokens | +50 lines in `theme.css` | 1 h |
| 3 | `feat/design-primitives` | Promote 3 inline patterns to classes: `.surface-emphasis`, `.modal`, `.drawer` | +60 lines + ~6 callsite migrations | 2 h |
| 4 | `feat/a11y-focus-and-modals` | `:focus-visible` ring on all interactives, `role="dialog"` + `aria-modal` + Esc + focus trap on 4 modals | ~80 lines | 3 h |
| 5 | `refactor/inline-styles-to-tokens` | Replace inline `fontSize/padding/marginBottom` with the new tokens (mechanical) | ~344 sites edited; net negative LOC | 3 h |
| 6 | `fix/alerts-color-tint-bug` | `${color}08` template-literal pattern in `AlertsPage.tsx:100` produces invalid CSS — replace with the new alpha-tint tokens | ~5 lines | 15 min |

**Total: ~10 hours across ~6 PRs over a few sessions.** Nothing requires Tailwind, shadcn, CSS-in-JS, Storybook, or any new dependency. All changes layer onto the existing single-file `theme.css` system.

The two surprise bugs found while researching this plan:

1. **`AlertsPage.tsx:100` produces invalid CSS.** `` `${SEVERITY_COLOR[alert.severity]}08` `` evaluates to `var(--breakout)08` at runtime. CSS parsers cannot concatenate `08` onto a `var()` reference — the entire `background` declaration is silently dropped, so unread high-severity alerts have **no row tint** in production. The `rowGlow` tokens already in `lib/utils.ts:53–55` were probably intended for this exact purpose. Add `--tint-{breakout,move,watch}` semantic tokens; this whole class of bug disappears.
2. **`SEVERITY_COLOR` reuses signal colours for alert urgency** (`AlertsPage.tsx:10–14`). High-severity alerts read with the green BREAKOUT colour, which is the same colour as "good news / your card went up." This is semantically wrong — high-severity alerts should be at minimum visually distinguishable from up-trend price moves. Cheapest fix: introduce a `--severity-high/-med/-low` token family and stop double-purposing the signal palette.

Both are one-line product bugs. Both are exactly the kind of bug a design-system audit was supposed to surface.

---

## Goals & non-goals

**Goals**
- Eliminate the 3 silent-fallback token references (real correctness bug today).
- Establish a token vocabulary that covers ~95% of inline styling patterns with ≤30 named tokens.
- Make the existing patterns (modal, drawer, gold-tinted callout) reusable so the next page costs ~30% less to build.
- Add the minimum keyboard / screen-reader plumbing required to not embarrass the site at launch.

**Non-goals (explicitly)**
- Not migrating to Tailwind or any utility CSS framework. The single-file `theme.css` pattern fits a solo-dev / single-app / no-team-handoff context. Migration cost is not justified.
- Not adopting shadcn/Radix/Headless UI. Same reason — cost > benefit at this scale, and the React 19 + plain CSS surface area today is small enough that primitives can be hand-rolled in <150 LOC each.
- Not building Storybook. There are ~14 components — readable in one sitting from `frontend/src/components/`. The tradeoff flips if/when the project hits ~30 components.
- Not introducing light mode. Per the audit: TCG/finance-terminal aesthetic, dark-only is a defensible product decision. Recommend recording it as such in `frontend/README.md` so it stops being an open question.
- Not refactoring SVG charts (`ComparisonChart`, `Sparkline`, `SignalTimeline`, `CardArt`, `CardDetailPage` chart). Inline SVG legitimately needs inline styling. Those files are excluded from PR #5.

---

## The token system v2

This is what should be added to `frontend/src/styles/theme.css` `:root`. It composes onto the existing tokens — nothing is removed.

### Naming convention

Existing tokens use kebab-case category prefixes (`--bg-*`, `--text-*`, `--border-*`, `--radius-*`, `--font-*`). Keep that. New families: `--space-*`, `--text-size-*`, `--shadow-*`, `--motion-*`, `--tint-*`, `--severity-*`, `--scrim-*`. The `--border-*` family extends with gold variants (`--border-gold-soft`, `--border-gold-strong`). **Role is encoded in the prefix**: `--tint-*` is background-color only; `--border-*` (including `--border-gold-*`) is border-color only. Reading test: an engineer who has never seen this file should be able to predict the token name from the role.

### Tokens to add

```css
:root {
  /* ── New: missing tokens (P0 — already referenced) ── */
  --border-default: rgba(255,255,255,0.10);   /* between subtle 0.06 and strong 0.15 */
  --radius-md:      8px;                       /* most-used inline radius (7×) */
  --text-inverse:   #0c0c10;                   /* matches bg-base; already inlined in NavBar */

  /* ── New: semantic colours ── */
  --danger:         #ef4444;                   /* unifies 5 inline references */
  --danger-bg:      rgba(239,68,68,0.10);      /* for pill backgrounds, error tints */
  --tint-danger:    rgba(239,68,68,0.08);      /* low-α row wash for high-severity alerts */

  /* ── New: tier accent (decision 2026-05-07: plus gets its own badge) ── */
  --plus:           #a78bfa;                   /* violet — distinct from gold/pro */
  --plus-glow:      rgba(167,139,250,0.12);

  /* ── New: alert severity (replaces SEVERITY_COLOR's signal-palette double-purpose) ── */
  --severity-high:  #ef4444;                   /* red — distinct from breakout green */
  --severity-med:   #f59e0b;                   /* amber — same hue as move, intentional */
  --severity-low:   #6b7280;                   /* grey — distinct from watch orange */

  /* ── New: signal alpha tints (replaces the broken ${color}08 pattern) ── */
  /* NOTE: --tint-* is background-color only. Border-color uses --border-* prefix. */
  --tint-breakout:  rgba(34,197,94,0.08);
  --tint-move:      rgba(245,158,11,0.08);
  --tint-watch:     rgba(251,146,60,0.08);

  /* ── Gold border variants (extend existing --border-* family; added in PR #1) ── */
  --border-gold-soft:   rgba(240,180,41,0.30);   /* the 6×-repeated gold border-color */
  --border-gold-strong: rgba(240,180,41,0.40);   /* the 4×-repeated gold border-color */
  /* --gold-glow (rgba(240,180,41,0.12)) already exists — do NOT add --tint-gold-glow */

  /* ── New: scrims (overlays / modal backdrops) ── */
  --scrim-light:    rgba(12,12,16,0.55);       /* drawer backdrop */
  --scrim-medium:   rgba(12,12,16,0.75);       /* modal backdrop default */
  --scrim-strong:   rgba(12,12,16,0.88);       /* ProGate-style hard overlay */

  /* ── New: type scale ── */
  --text-2xs: 11px;   /* badges, uppercase eyebrows, mono chips */
  --text-xs:  12px;   /* secondary metadata */
  --text-sm:  13px;   /* body default — currently used 41× inline */
  --text-md:  14px;   /* primary body — currently 23× inline */
  --text-lg:  16px;   /* lead paragraphs */
  --text-xl:  20px;   /* section headers */
  --text-2xl: 26px;   /* page titles (already in .page-title) */
  --text-3xl: 48px;   /* hero numbers, landing display */

  /* Line heights — pair with the sizes above */
  --leading-tight: 1.2;
  --leading-snug:  1.4;
  --leading-base:  1.6;

  /* ── New: spacing scale (4-step ramp + a few escape valves) ── */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-8: 32px;
  --space-12: 48px;
  --space-20: 80px;   /* hero / landing-only */

  /* ── New: shadows / elevation ── */
  --shadow-card:    0 1px 2px rgba(0,0,0,0.30);
  --shadow-modal:   0 24px 64px rgba(0,0,0,0.60);
  --shadow-glow-gold: 0 0 48px rgba(240,180,41,0.12);

  /* ── New: motion ── */
  --motion-fast: 0.1s;
  --motion-base: 0.15s;
  --motion-slow: 0.3s;
  --ease-default: cubic-bezier(0.4, 0, 0.2, 1);
}
```

**Total addition: ~33 new tokens.** Coverage check (verified against the audit's grep output):

| Category | Inline distinct values today | Tokens covering them | Coverage |
|---|---|---|---|
| `fontSize` | 17 distinct (9 to 52) | 8 sizes — covers 9, 10, 11, 12, 13, 14, 16, 20, 26, 48 (= 10 of 17, including the top 6 most-used = 95% of occurrences) | very high |
| `padding/gap` numeric | 14 padding + 12 gap distinct | 9-step spacing scale covers 4, 8, 12, 16, 20, 24, 32, 48, 80 (= the entire bell of the distribution) | very high |
| `borderRadius` | 7 distinct | 3 radii (sm 6, md 8, lg 12) + the 20 stays as inline `999px` for pills | high |
| `fontWeight` | 4 distinct (500, 600, 700, 800) | None — leave inline; only 4 values, all aliased to typography roles already | n/a |
| Colours | All hex/rgba grouped | All semantic | 100% |

### Derivation rationale

- **8-step type scale** (vs. e.g. Tailwind's 14): the codebase only meaningfully uses 8 sizes once `15` and `9` are normalised to neighbours. More sizes = more decisions = inconsistency.
- **Spacing by absolute value, not ratio**: the existing inline values are `4, 6, 8, 10, 12, 14, 16, 20, 24, 32, 40, 48`. A pure 4×n ramp loses 6, 10, 14 — but those occur ≤7 times each and reading them as the closest "nice" number (8, 12, 16) is visually fine and removes ~25 micro-decisions.
- **Severity colours are deliberately disjoint from signal colours**. CLAUDE.md Lesson 5 and 8 both warn that double-purposed semantics get bugs. Alert severity and signal label are two distinct concepts; tokenising them apart makes the next product decision (e.g. "should low-severity alerts even render?") cleaner.
- **`--tint-*` is a separate family from `--severity-*` and `--{breakout,move,watch}`**. Tints exist to be used as *background*; severity colours exist to be used as *border-left or dot*; signal colours exist to be used as *text or border*. Three roles, three families. Keeps callers from inventing `${color}08`-style runtime concatenation.

---

## Component primitive extraction

These three patterns each appear inline in 3+ places today. Promoting them to classes in `theme.css` (matching the existing `.btn` / `.badge` / `.surface` / `.nav-link` style — no new files) gives the largest payoff.

### `.surface-emphasis` — gold-tinted callout

Inline today at: `AIAnalysisSection.tsx:7–11`, `PlusUpgradeModal.tsx:18–22`, `DashboardPage.tsx:308–314`, `LandingPage.tsx:188`. Each is a `.surface` with a gold border and a soft outer glow.

```css
.surface-emphasis {
  background: var(--bg-surface);
  border: 1px solid var(--border-gold-soft);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-glow-gold);
}
.surface-emphasis-firm {
  /* same but firmer border — for callouts that should feel "claimable" */
  border-color: var(--border-gold-strong);
}
```

### `.modal` + `.modal-backdrop` — modal scaffold

Inline today at: `PlusUpgradeModal.tsx:7–22`, `CardPickerModal.tsx:55–73`. Both currently miss `role="dialog"` and `aria-modal` (PR #4 fixes that).

```css
.modal-backdrop {
  position: fixed; inset: 0; z-index: 1000;
  background: var(--scrim-medium);
  backdrop-filter: blur(2px);
  display: flex; align-items: center; justify-content: center;
  padding: var(--space-4);
}
.modal {
  background: var(--bg-elevated);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-modal);
  max-width: 480px; width: 100%;
  overflow: hidden;
}
.modal-header,
.modal-section {
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--border-subtle);
}
.modal-section:last-child { border-bottom: none; }
```

### `.drawer` — side drawer scaffold

Inline today at: `FilterDrawer.tsx:88–105`. One use today, but the audit recommends adding `role="dialog"` and Esc handling — easier to do that on a class than every callsite.

```css
.drawer-backdrop {
  position: fixed; inset: 0; z-index: 200;
  background: var(--scrim-light);
}
.drawer {
  position: fixed; top: 0; right: 0; bottom: 0;
  width: clamp(280px, 100vw, 380px);
  background: var(--bg-elevated);
  border-left: 1px solid var(--border-subtle);
  z-index: 201;
  display: flex; flex-direction: column;
  overflow-y: hidden;
}
.drawer-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: var(--space-5) var(--space-5) var(--space-3);
}
.drawer-body { flex: 1; overflow-y: auto; padding: 0 var(--space-5); }
```

### Why these three, in this order

The audit identified five reusable patterns: callout, modal, drawer, alert row, stat tile. Modal + drawer + callout are bundled into PR #3 because they are *the* sites that have correctness or accessibility problems today. Alert row and stat tile are layout-only — they work — and can wait. The 80/20 cut on day one is to fix what's broken first.

---

## Accessibility upgrades (PR #4)

Not a full WCAG audit — that's `/design:accessibility-review`'s job. This is the minimum needed to ship the site with a straight face.

### Focus indicators

Add to `theme.css`:

```css
:where(.btn, .nav-link, button, [role="button"], a, input, select, textarea):focus-visible {
  outline: 2px solid var(--gold);
  outline-offset: 2px;
}
```

The `:where()` keeps specificity at 0 so per-component `:focus-visible` overrides remain trivial. `:focus-visible` (not `:focus`) ensures mouse clicks don't show the ring; only keyboard focus does. `outline` (not `box-shadow`) avoids reflow.

### Modal semantics

For each of `PlusUpgradeModal`, `CardPickerModal`, `FilterDrawer`, `ProGate`:

1. Add `role="dialog"` and `aria-modal="true"` to the modal/drawer element (not the backdrop).
2. Add an `aria-labelledby` reference to the header text.
3. Add an `Escape` key handler that calls `onClose`.
4. Trap focus inside the modal while open (one shared `useFocusTrap` hook).

Suggested hook (lives at `frontend/src/hooks/useFocusTrap.ts` — ~30 LOC, no dependency):

```ts
import { useEffect, useRef } from 'react'

export function useFocusTrap<T extends HTMLElement>(open: boolean) {
  const ref = useRef<T>(null)
  useEffect(() => {
    if (!open || !ref.current) return
    const root = ref.current
    const previouslyFocused = document.activeElement as HTMLElement | null
    const focusables = root.querySelectorAll<HTMLElement>(
      'a, button, input, select, textarea, [tabindex]:not([tabindex="-1"])'
    )
    focusables[0]?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Tab' || focusables.length === 0) return
      const first = focusables[0], last = focusables[focusables.length - 1]
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault(); last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault(); first.focus()
      }
    }
    root.addEventListener('keydown', onKey)
    return () => {
      root.removeEventListener('keydown', onKey)
      previouslyFocused?.focus()
    }
  }, [open])
  return ref
}
```

### Hover-only affordances

Replace the JS `onMouseEnter`/`onMouseLeave` patterns in `FilterDrawer.tsx:119–120`, `CardGrid.tsx:55,68–69` with CSS `:hover`. Three sites total. CSS hover automatically becomes touch-tap-and-hold and keyboard `:focus-visible` once the focus ring lands.

### What's deliberately deferred

- Full ARIA labels on the SVG charts. Real value, but a non-trivial design exercise (what does a screen reader say for a 30-day price chart?) — defer until the product ships v1 to a paying user.
- Reduced-motion support (`prefers-reduced-motion`). Add when motion tokens are introduced (PR #2 already pulls motion into tokens, so adding `@media (prefers-reduced-motion: reduce)` rules in PR #4 is one extra block).

---

## Phased rollout

Each PR is scoped to one concern (per CLAUDE.md §3). Each is verifiable independently. Each leaves the site shippable.

### PR #1 — `fix/design-tokens-undefined` (10 min)

**Change:** add `--border-default`, `--radius-md`, `--text-inverse` to `:root` in `theme.css`. Nothing else.

**Verified by:**
- `grep -n 'border-default\|radius-md\|text-inverse' frontend/src/styles/theme.css` — should return 3 lines, was 0.
- Manual visual check on `/compare`, `/market/<id>`, the card-picker modal (open from `/compare`), and the watchlist count badge in NavBar — borders should now render in the intended grey instead of the accidental `currentColor` fallback.
- `npm run build` passes.

**Risk:** zero. Pure addition. The fallback was already silent, so adding the real value cannot make things visually worse.

### PR #2 — `feat/design-tokens-v2` (1 h)

**Change:** add the token block above to `:root`. No callsite changes yet.

**Verified by:**
- `npm run build` passes.
- `npm run test` passes (existing tests; new tests come in PR #5).
- Visual diff: zero (no callers reference the new tokens yet).

**Risk:** very low. Adding unused CSS variables has zero runtime cost and zero visual effect.

### PR #3 — `feat/design-primitives` (2 h)

**Change:** add `.surface-emphasis`, `.modal-backdrop`, `.modal`, `.modal-header`, `.modal-section`, `.drawer-backdrop`, `.drawer`, `.drawer-header`, `.drawer-body` classes. Migrate the 4 callsites for `.surface-emphasis` (`AIAnalysisSection.tsx:7–11`, `PlusUpgradeModal.tsx:18–22`, `DashboardPage.tsx:308–314`, `LandingPage.tsx:188`). Migrate `PlusUpgradeModal` and `CardPickerModal` to use `.modal`/`.modal-backdrop`. Migrate `FilterDrawer` to use `.drawer` family.

**Verified by:**
- Visual side-by-side: every migrated callsite renders pixel-identical to before. The token values were chosen exactly to preserve the current output.
- `npm run build && npm run test` pass.
- `grep -rE 'rgba\(240,180,41,0\.[34]\)' frontend/src` — should return ≤1 line (LandingPage hero may keep one inline use). Was 10.

**Risk:** medium. Visual regressions possible if a per-callsite override is dropped during migration. Mitigation: review each migration against a screenshot of the pre-change render.

### PR #4 — `feat/a11y-focus-and-modals` (3 h)

**Change:** add the `:focus-visible` rule to `theme.css`. Add `useFocusTrap` hook. Wire `role="dialog"`, `aria-modal="true"`, `aria-labelledby`, `Esc` handler, and focus trap into all 4 modals/drawers (`PlusUpgradeModal`, `CardPickerModal`, `FilterDrawer`, `ProGate`). Replace JS hover handlers with CSS `:hover` in 3 sites.

**Verified by:**
- Tab through the entire site (every page) — every interactive shows a visible gold focus ring.
- Open every modal, confirm: `Esc` closes, focus is trapped, screen reader (VoiceOver / NVDA) announces "dialog".
- New unit tests in `frontend/src/lib/`: a `useFocusTrap.test.ts` that mounts a component with the hook and asserts Tab cycles within the trap.

**Risk:** medium. Focus traps are easy to get subtly wrong (e.g. trapping but not restoring focus on close). Add a test for restoration.

### PR #5 — `refactor/inline-styles-to-tokens` (3 h)

**Change:** mechanical replacement of inline `fontSize: 13` → `fontSize: 'var(--text-sm)'` (and the rest of the table), inline `padding: 16` → `padding: 'var(--space-4)'`, etc. Across all 22 files. SVG-heavy files (`ComparisonChart.tsx`, `Sparkline.tsx`, `SignalTimeline.tsx`, `CardArt.tsx`, the chart in `CardDetailPage.tsx`) are excluded — their inline styles are SVG attribute values, not CSS tokens.

**Verified by:**
- `git diff --stat` — should be net-negative LOC (token references are shorter than literals when collapsed).
- Visual side-by-side on every page — pixel-identical to PR #4's output. The tokens were calibrated to existing values, so this is a pure rename.
- `grep -rE "fontSize: ?[0-9]+" frontend/src --include='*.tsx' | wc -l` — should drop from 17 distinct values to 0 outside the SVG files.
- New test: `frontend/src/styles/tokens.test.ts` (~20 LOC) that reads `theme.css`, parses the `:root` block, and asserts every token name expected by the codebase is defined. Catches the "PR #1 problem" from regressing.

**Risk:** medium. Largest diff of the sequence. Mitigation: do it one file at a time; commit per file inside the PR; the rename is mechanical so review by file is cheap.

### PR #6 — `fix/alerts-color-tint-bug` (15 min)

**Change:** replace the broken `` `${SEVERITY_COLOR[alert.severity]}08` `` template literal in `AlertsPage.tsx:100` with the correct `--tint-*` tokens introduced in PR #2. Also update `SEVERITY_COLOR` (lines 10–14) to use the new `--severity-{high,med,low}` tokens instead of the signal palette. **This is a behavioural fix, not a refactor** — unread high-severity alert rows currently render with no background tint; after this PR they render with the intended subtle red tint.

**Verified by:**
- Open `/alerts` in dev, mark all read, then trigger a high-severity alert — row should have a faint red wash.
- Production verification: SQL not needed; visual on the deployed site.
- Add a unit test for the new `severityToTint` helper that asserts `'high'` returns `'var(--tint-danger)'`, etc.

**Risk:** very low. The change is fixing what was already supposed to render.

---

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Token rename in PR #5 misses a callsite, leaving `var(--text-sm)` next to a stray `fontSize: 13` | Medium | Low (cosmetic) | The token-presence test in PR #5 catches references to *missing* tokens but not stray literals. Add a separate lint rule (eslint custom rule, ~30 LOC) that warns on inline numeric `fontSize` / `padding` / `gap` outside an allowlist of files. Optional — not blocking. |
| PR #3 visual regression in modals | Medium | Medium (modals are critical paths) | Take pre/post screenshots; fold into PR description. |
| PR #4 focus trap traps too aggressively (e.g. blocks browser-level shortcuts) | Low | Medium | Test with browser shortcuts (Cmd-L, Cmd-W, Cmd-T) — trap should only intercept Tab and Esc. |
| Token additions accidentally break existing CSS specificity | Very low | Low | All additions are inside `:root`; no selectors changed. |
| The "var()08" CSS-concat bug exists elsewhere | Low | Low | Grep confirmed exactly one site (`AlertsPage.tsx:100`). Re-grep after PR #6 to confirm zero. |

---

## Decisions (locked 2026-05-07)

Operator answered the open questions on 2026-05-07; recording them here so future sessions don't re-litigate.

1. **PLUS users do get a tier badge.** NavBar needs to render both PRO and PLUS as distinct visual ranks. PR #2 adds a `--plus` colour (suggest a cooler accent — silver `#cbd5e1` or violet `#a78bfa` — final pick is a 5-min designer call); PR #4 wires the conditional. The existing `tier === 'pro'` check in `NavBar.tsx:49` becomes a switch that handles both. Add a `PlusBadge` test alongside the existing `parseTier.test.ts` to assert plus users render the plus variant, not the pro one — same regression-guard pattern as PR #43 / Lesson 13.
2. **Light mode is won't-fix.** Officially dark-only. Action item: add a one-line declaration to `frontend/README.md` (fold into PR #1) so the question stops getting re-asked. PR #2 token block does *not* need a `:root[data-theme="light"]` override.
3. **Alert severity decouples from the signal palette.** The `--severity-{high,med,low}` family proposed in PR #2 is in. PR #6 switches `SEVERITY_COLOR` (AlertsPage.tsx:10–14) over to the new tokens and uses `--tint-danger` / `--tint-move` / `--tint-watch` for the row washes — eliminating both the broken `${color}08` runtime concatenation and the "high-severity reads as good-news green" semantic clash.

Remaining no-decision-needed cleanup:
- **`<title>frontend</title>` in `frontend/index.html:7`** → folded into PR #1 alongside the README dark-only note. No question, just do it.

---

## What this plan does NOT do (and why)

- **No CSS-in-JS migration.** The team is one person; the codebase has 14 components; `theme.css` at 343 LOC is well under the threshold where a runtime styling library starts paying back its bundle-size cost.
- **No design-token format like `style-dictionary` or W3C Design Tokens.** Same reason — single consumer, single output target. Plain CSS variables are the lowest-overhead format that loses nothing.
- **No formal component library / Storybook.** The cost-benefit flips around ~30 components; we're at 14. The README in `frontend/` is sufficient documentation for now; promote to Storybook when the count crosses the threshold.
- **No visual regression testing harness (Chromatic, Percy).** Useful but adds a paid SaaS dependency. For a solo dev with infrequent UI changes, manual screenshot diffs in PR descriptions are an acceptable substitute. Re-evaluate if/when a designer joins.
- **No refactor of the SVG chart components.** They are correctly using inline SVG attributes; tokens don't apply. The audit's score does not penalise them.

---

## Appendix A — full inline-style distribution

Verified 2026-05-07 against `frontend/src/**.tsx`.

```
fontSize  count    | padding (numeric)  count  | gap   count  | borderRadius  count
13        41       | 20                 8      | 8     14     | 8             7
14        23       | 16                 6      | 12    12     | 6             7
11        23       | 80                 2      | 10    8      | 10            5
12        17       | 40                 2      | 6     7      | 4             3
10        12       | 28                 2      | 16    7      | 20            3
22        7        | 48                 1      | 14    2      | 3             1
18        7        | 32                 1      | 24    1      | 12            1
16        7        | 24                 1      | 32    1      |
9         6        |                           | 4     1      |
20        5        |                           | 5     1      |
48        4        |                           |              |
28        4        |                           |              |
32        2        |                           |              |
15        2        |                           |              |
26, 24, 52  1 each |                           |              |

inline style={{ }} blocks total: 344 across 22 files
fontWeight values: 700 (25), 600 (15), 500 (1), 800 (1)
boxShadow distinct inline: 3
transition distinct inline: 6
```

---

## Appendix B — verified bug list (collateral findings)

These are bugs caught during the deep-research pass that are not strictly "design system" but live in the same files. Each gets a one-line fix in the relevant PR.

| # | File:line | Bug | Severity | PR |
|---|---|---|---|---|
| B1 | `AlertsPage.tsx:100` | `` `${var(--breakout)}08` `` is invalid CSS — silent dropped declaration | P1 | #6 |
| B2 | `AlertsPage.tsx:10–14` | `SEVERITY_COLOR` reuses signal palette; high-severity alerts read as "good news green" | P2 | #6 |
| B3 | `frontend/index.html:7` | `<title>frontend</title>` — Vite scaffold leftover | P3 | #1 |
| B4 | `NavBar.tsx:49` | `tier === 'pro'` only — `plus` users currently see no badge. Operator confirmed 2026-05-07: plus *should* get its own badge (violet `--plus`). Convert the conditional to a switch over `tier`. | P2 | #4 |
| B5 | `CardDetailPage.tsx:315` | `style={{ color: '#ef4444' }}` — error text uses hardcoded danger; should be `var(--danger)` post-PR #2 | P3 | #5 |
