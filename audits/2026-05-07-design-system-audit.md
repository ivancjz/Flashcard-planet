# Flashcard Planet — design system audit

Date: 2026-05-07
Scope: `frontend/src/` (the SPA — 14 components, 8 pages, 1 token sheet, ~3,400 LOC)
Method: static review of the source tree. The live URL `flashcard-planet.up.railway.app` is blocked by the egress proxy from this environment, so visual verification against the deployed site was not possible — every finding below is grounded in a file path + line number you can re-check with `git blame`.

## Summary

**Components reviewed:** 14 components + 8 pages + 1 token sheet
**Issues found:** 18 (3 P0 broken, 8 P1 consistency, 7 P2 polish)
**Score:** **52/100**

The system is recognisable — there is one CSS file with named tokens, a `.btn` / `.badge` / `.surface` / `.nav-link` primitive set, and a coherent dark + gold visual identity. But it is roughly 30% codified and 70% inline. 344 inline `style={{}}` blocks across 22 files do most of the layout work; the token sheet covers only the colour palette, two radii, two spacing-adjacent values, and zero formal scales for type, spacing, shadow, or motion. Three referenced CSS variables are not defined anywhere — they fall back silently and the only reason the UI doesn't visibly break is that `border-color: unset` resolves to `currentColor` in dark mode, which is *almost* the right colour by accident.

The fastest wins are: define the three missing tokens (P0 — they are referenced live), introduce a spacing + type scale (P1 — currently 17 distinct `fontSize` values and 14 distinct `padding` values inline), and decide whether the recurring "gold-tinted card" pattern should become a `.surface-emphasis` class.

---

## P0 — broken token references

These three tokens are read at runtime but never defined in `theme.css`. Every site renders with `unset` (which CSS resolves to `initial` for the cascading property — usually `currentColor` for borders, which only looks correct because the page is dark on dark text).

| Token | Defined? | Referenced in |
|---|---|---|
| `--border-default` | No (theme has `--border-subtle`, `--border-strong`) | `components/CardPickerModal.tsx:69`, `components/SignalTimeline.tsx:50`, `pages/CardDetailPage.tsx:238`, `pages/ComparePage.tsx:136`, `pages/ComparePage.tsx:170` |
| `--radius-md` | No (theme has `--radius-sm: 6px`, `--radius-lg: 12px`) | `components/CardPickerModal.tsx:70`, `pages/ComparePage.tsx:171`, `pages/ComparePage.tsx:230` |
| `--text-inverse` | No (used with inline fallback `#0c0c10`) | `components/NavBar.tsx:81` |

**Recommendation:** add these three to `:root` in `theme.css`. Suggested values that match the existing visual language: `--border-default: rgba(255,255,255,0.10);` (between `subtle` 0.06 and `strong` 0.15), `--radius-md: 8px;` (the most common inline `borderRadius` value, used 7×), and `--text-inverse: #0c0c10;` (matches `--bg-base` — the colour already inlined in `NavBar`, `LandingPage`, `DashboardPage`).

---

## Token coverage

| Category | Defined tokens | Inline distinct values found |
|---|---|---|
| Colours — backgrounds | 3 (`--bg-base/-surface/-elevated`) | 0 hardcoded background hexes outside theme |
| Colours — text | 3 (`--text-primary/-secondary/-muted`) | None hardcoded |
| Colours — brand | 3 (`--gold`, `--gold-dim`, `--gold-glow`) | `#f0b429` repeated 2× inline (`pages/LandingPage.tsx:54`, `components/NavBar.tsx:37`) |
| Colours — semantic | 5 signal colours + `.up`/`.down` | `#ef4444` for danger/destructive repeated 5× across `pages/LandingPage.tsx:223`, `pages/CardDetailPage.tsx:315`, `pages/AlertsPage.tsx:51`, `components/NavBar.tsx:94`, `components/FilterDrawer.tsx:183`, `components/Sparkline.tsx:21` — no `--danger` / `--text-danger` token exists |
| Typography — families | 3 (`--font-display/-body/-mono`) | None hardcoded; `'monospace'` used once in `components/DevTierSwitcher.tsx:16` |
| Typography — sizes | 0 (sizes set inline everywhere) | 17 distinct `fontSize` values: 9, 10, 11, 12, 13, 14, 15, 16, 18, 20, 22, 24, 26, 28, 32, 48, 52 |
| Spacing | 0 (only `--nav-h: 56px`) | 14 distinct `padding` values + 12 distinct `gap` values inline |
| Radii | 2 (`--radius-sm: 6px`, `--radius-lg: 12px`) | 7 distinct inline `borderRadius` values: 3, 4, 6, 8, 10, 12, 20 |
| Shadow / elevation | 0 | Several one-off inline `boxShadow` values (`PlusUpgradeModal.tsx:21`, `CardPickerModal.tsx:71`, plus dynamic JS-driven shadows in `CardGrid.tsx:55`) |
| Motion | 4 keyframes (`shimmer`, `scroll-ticker`, `float-anim*`, `fade-up-anim`, `pulse`) | Per-element `transition: 0.15s` repeated; no shared duration / easing tokens |

**Most useful additions (in order of leverage):**

1. **Type scale.** Pick 6–7 sizes — say `--text-xs: 11px` / `-sm: 13px` / `-base: 14px` / `-md: 16px` / `-lg: 20px` / `-xl: 26px` / `-2xl: 48px`. The existing 17 distinct sizes can be collapsed into these with no visible loss; `13px` alone is used 41 times inline.
2. **Spacing scale.** A 4-step ramp (`--space-1: 4px` / `-2: 8px` / `-3: 12px` / `-4: 16px` / `-6: 24px` / `-8: 32px`) covers every value in current use except the hero one-offs (40, 48, 80) which can stay literal.
3. **Semantic colours.** `--danger` (the inlined `#ef4444`), `--danger-bg` (transparent variant for the unread-alerts badge), and the missing `--text-inverse`. Optional: `--success` already exists indirectly as `--breakout`; consider whether to alias.
4. **`--radius-md: 8px`** to fill the gap between `sm: 6px` and `lg: 12px`. Eight is the most-used inline radius today.
5. **Shadow tokens.** At least `--elev-1` (cards), `--elev-2` (modals), `--elev-glow-gold` (the recurring `0 0 48px rgba(240,180,41,0.12)` pattern in `PlusUpgradeModal.tsx:21`).

---

## Component completeness

| Component | File | LOC | Variants | States covered | Notes |
|---|---|---|---|---|---|
| Button (`.btn`) | `theme.css:60–93` | — | `primary`, `ghost`, `sm` | `:hover`, `:active` | No `:disabled`, no `:focus-visible`, no loading state, no destructive variant |
| Badge (`.badge`) | `theme.css:148–167` | — | `breakout`, `move`, `watch`, `idle`, `nodata` | static only | Tightly coupled to signal labels — not a generic badge |
| Surface (`.surface`) | `theme.css:170–174` | — | one variant | static | The "gold-tinted card" pattern (`AIAnalysisSection.tsx:9`, `PlusUpgradeModal.tsx:18–22`, `DashboardPage.tsx:312`, `LandingPage.tsx:188`) is reinvented inline 4× — should be `.surface-emphasis` or `.surface-gold` |
| NavLink (`.nav-link`) | `theme.css:136–146` | — | one | `:hover`, `.active` | OK |
| SignalBadge | `components/SignalBadge.tsx` | 7 | wraps `.badge-*` | — | Cleanest component in the tree |
| GameSwitcher | `components/GameSwitcher.tsx` | 87 | active / ghost / "+ More" popover | hover via `:not-allowed` cursor | Reinvents pill styling inline (`borderRadius: 20`) — overlaps with `.badge`. No keyboard handling for the popover; backdrop is a click-trap div with no `Esc` |
| FilterDrawer | `components/FilterDrawer.tsx` | 207 | one | `onMouseEnter`/`onMouseLeave` JS hover | Drawer has no `aria-modal`, no focus trap; `Esc` not bound; backdrop click works |
| CardPickerModal | `components/CardPickerModal.tsx` | 180 | one | — | Modal missing `role="dialog"`, `aria-modal="true"`; references undefined tokens (P0) |
| PlusUpgradeModal | `components/PlusUpgradeModal.tsx` | 58 | one | — | Same: no `role`/`aria-modal`. Backdrop click works |
| ProGate | `components/ProGate.tsx` | 36 | one | — | Inline backdrop colour `rgba(12,12,16,0.88)` — should be a `--scrim` token |
| CardGrid card | `components/CardGrid.tsx` | 149 | one | inline JS hover (`box-shadow` set via `currentTarget.style`) | Watchlist toggle has `aria-label`; the card itself does not have a clear focus state |
| Sparkline | `components/Sparkline.tsx` | 38 | trend up / down | static | Hardcodes `#ef4444` as the down stroke; otherwise tokenised |
| ComparisonChart | `components/ComparisonChart.tsx` | 167 | one | — | Hardcodes axis stroke `rgba(255,255,255,0.2)` and gridline `rgba(255,255,255,0.06)` — would benefit from `--chart-axis` / `--chart-gridline` tokens |
| AIAnalysisSection | `components/AIAnalysisSection.tsx` | 59 | gold-tinted surface | — | Reinvents the "gold-tinted card" pattern inline |
| DevTierSwitcher | `components/DevTierSwitcher.tsx` | 21 | — | — | Dev-only; uses `'monospace'` literal and inline `#fff` |
| TickerBar | `components/TickerBar.tsx` | 22 | one | `:hover` pauses animation | Clean |
| CardArt, NavBar, SignalTimeline | — | — | — | — | Mostly tokenised; SignalTimeline references undefined `--border-default` |

**Cross-cutting state gaps:**
- **No `:focus-visible` styling exists in the entire codebase.** Several interactive elements rely on `onMouseEnter`/`onMouseLeave` JS handlers (`FilterDrawer.tsx:119–120`, `CardGrid.tsx:68–69`, `CardGrid.tsx:55`) which means keyboard users get no visual feedback at all.
- **No `:disabled` styling on `.btn`.** A disabled state currently just looks like an active button — clickable.
- **No loading state on buttons.** "Save" actions in `DigestPreferencesPage` and `DashboardPage` set local `saving` state but render plain text — no spinner primitive exists.

---

## Naming consistency

| Issue | Sites | Recommendation |
|---|---|---|
| Two parallel scales for *almost* the same scrim colour | `rgba(0,0,0,0.55)` (FilterDrawer:85), `rgba(0,0,0,0.65)` (PlusUpgradeModal:10), `rgba(0,0,0,0.8)` (DevTierSwitcher:9), `rgba(12,12,16,0.7)` (ComparePage:238, CardGrid:62), `rgba(12,12,16,0.75)` (CardPickerModal:59), `rgba(12,12,16,0.85)` (theme.css:105 nav), `rgba(12,12,16,0.88)` (ProGate:24) | Settle on 2–3 scrim tokens (`--scrim-light/-medium/-strong`) and use them everywhere |
| Gold-accent border replicated as a string literal | `border: '1px solid rgba(240,180,41,0.3)'` — appears in 6 places (`AIAnalysisSection.tsx:9`, `AIAnalysisSection.tsx:50`, `LandingPage.tsx:171`, `PlusUpgradeModal.tsx:20`, `NavBar.tsx:53`, `DashboardPage.tsx:312`) and `0.4` variant in 4 more (`PlusUpgradeModal.tsx:41`, `LandingPage.tsx:188`, `LandingPage.tsx:204`, `LandingPage.tsx:214`) | Add `--border-gold-soft` (0.3) and `--border-gold-strong` (0.4) tokens |
| Mix of CSS-class + inline-style for the same primitive | Buttons in `PlusUpgradeModal:35–46` use inline pill styling but also `className="btn btn-ghost"` 3 lines below — two different styling paradigms in one component | Pick one: classes for primitives, inline only for layout |
| `class` naming is consistent (kebab-case BEM-ish), but the SignalBadge labels mix glyph + word (`'▲ Breakout'`, `'◆ Move'`, `'◆ Watch'`) | `lib/utils.ts:53–55` | Consider whether the glyph belongs in a `<span class="badge-glyph">` so the label can be read by screen readers without the symbol |

---

## Inline-style sprawl

344 inline `style={{}}` blocks across 22 files. Hotspots:

| File | Inline `style={{}}` count | Note |
|---|---|---|
| `pages/LandingPage.tsx` | 52 | Hero section is layout-heavy, expected, but the 7 different gold-tinted callout boxes could share a class |
| `pages/CardDetailPage.tsx` | 47 | SVG chart legitimately needs inline; the surrounding layout could be tokenised |
| `pages/ComparePage.tsx` | 35 | Three references to the missing `--radius-md` are here |
| `components/FilterDrawer.tsx` | 30 | Drawer chrome alone is ~15 inline blocks; could become `.drawer` / `.drawer-header` / `.drawer-section` classes |
| `pages/DashboardPage.tsx` | 28 | Stat tile pattern repeats |
| `pages/AlertsPage.tsx` | 22 | Alert row layout repeats |

This isn't itself broken — inline styles work — but it makes future restyling cost-of-change quadratic in the number of pages. The pragmatic threshold for promoting an inline pattern to a class is "appears identical in 3+ places." By that bar: gold-tinted callout, alert row, stat tile, modal scaffold, and drawer scaffold all qualify today.

---

## Accessibility (skim — full WCAG audit is a separate skill)

| Area | State | Risk |
|---|---|---|
| Focus indicators | None defined anywhere | Keyboard navigation is invisible — WCAG 2.4.7 fail |
| Modal semantics | No `role="dialog"` / `aria-modal` on `CardPickerModal`, `PlusUpgradeModal`, `FilterDrawer`, `ProGate` | Screen readers don't announce as modal; focus not trapped |
| `aria-label` on icon buttons | Present on 5 (close, clear, watchlist toggle) — see grep above | OK where it exists |
| Hover-only affordances | `FilterDrawer.tsx:119–120`, `CardGrid.tsx:55,68–69` use JS `onMouseEnter` for hover state | Touch + keyboard users get no equivalent feedback |
| Colour-only signal labels | `signalToMeta` already includes a glyph prefix (`▲`, `◆`) which helps colourblind users | Decent baseline |

Recommend running `/design:accessibility-review` against this same tree for the formal WCAG 2.1 AA pass.

---

## Light mode

There is no light mode. `theme.css` defines exactly one set of values for `:root` and the body sets `background: var(--bg-base)` (=`#0c0c10`) unconditionally. This is fine if dark-only is the product decision (it likely is for a TCG / Bloomberg-terminal aesthetic), but worth naming explicitly so it doesn't get re-asked. If light mode ever becomes a goal, every inline `rgba(255,255,255,0.X)` border would need to flip — there are 6 such literals in the codebase today.

---

## Priority actions

1. **Define the three missing tokens** (`--border-default`, `--radius-md`, `--text-inverse`) in `theme.css`. One-line PR. Eliminates the silent-fallback risk across 5 files.
2. **Introduce a type scale and a spacing scale** as CSS variables. Even just adding the tokens (without rewriting every inline `fontSize: 13` to `var(--text-sm)`) makes future work consistent. New code references the tokens; old code is a tidy-up backlog.
3. **Add `--danger`, `--scrim-{light|medium|strong}`, and `--border-gold-{soft|strong}` tokens.** These are the values most-frequently inlined as raw `rgba()`. Together they eliminate ~20 string-literal repetitions.
4. **Promote three patterns to classes**: `.surface-emphasis` (gold-tinted card), `.modal` + `.modal-backdrop`, `.drawer` + `.drawer-section`. Each lives in 3+ places and each is currently re-derived via inline styles.
5. **Add a `:focus-visible` ring to `.btn`, `.nav-link`, and the unstyled icon-buttons.** One short block in `theme.css`. Closes the largest accessibility hole.
6. **Add `:disabled` and a loading variant to `.btn`.** Required before the next billing/checkout flow ships — there are at least two in-flight save buttons today (`DigestPreferencesPage`, `DashboardPage`) that visibly do nothing while a request is in-flight.
7. **Decide light-mode posture explicitly.** "Dark-only — won't fix" is a valid answer; just record it so future contributors don't re-litigate.

---

## What I could not verify

- The deployed site at `flashcard-planet.up.railway.app` is blocked by the egress proxy from this environment, so I could not confirm that the rendered output matches the source. All findings are static-source-derived.
- Whether the `tier === 'pro'` checks in `NavBar.tsx:49`, `AccountPage.tsx:11`, `DigestPreferencesPage.tsx:18`, and `lib/watchlist.ts:79` correctly handle the `'plus'` tier added per CLAUDE.md Lesson 13. Spot-check: `parseTier` (UserContext.tsx:11) is correctly defensive; `DigestPreferencesPage`'s `if (tier === 'free')` guard correctly admits both `plus` and `pro`; `NavBar`'s `tier === 'pro'` only renders the PRO badge for pro — `plus` users see no badge. May be intentional (separate PLUS badge planned) or a gap. Worth confirming with operator.
- I did not inspect `frontend/dist/` — assumed build output, not source-of-truth.
