# PR #6 implementation packet — `fix/alerts-color-tint-bug`

Date: 2026-05-08
Plan reference: `audits/2026-05-07-design-system-upgrade-plan.md` §PR #6
Bug: `AlertsPage.tsx:100` produces invalid CSS in production. High-severity unread alert rows have **no red row tint** because the `${var(--breakout)}08` template literal can't be parsed by browsers — the background declaration is silently dropped.

Scope is small — 2 commits. Fixes a real production-visible bug AND does the audit-locked decision (decouple alert severity from the signal palette).

Pre-flight verification (sandbox-readable, HEAD `45dc997`):
- `--severity-high/-med/-low` tokens present (theme.css:64–66)
- `--tint-danger` present (theme.css:56)
- AlertsPage.tsx use-sites unchanged from PR #51 — `SEVERITY_COLOR` defined line 10–14, used at lines 99 (border accent), 100 (broken background), 104 (status dot). Line 106 is emoji selection, not a colour use.
- The broken-CSS pattern is unique to AlertsPage:100 across the codebase (verified via `grep -rEn '\$\{[^}]+\}[0-9a-fA-F]{2}\b'`).

Branch off main:
```
git checkout main && git pull
git checkout -b fix/alerts-color-tint-bug
```

---

## Commit 1 — `feat(theme): add --tint-severity-{med,low} for alert row washes`

**Concern:** add the two missing tints needed by commit 2's row-wash fix. `--tint-danger` already exists and serves high severity; med and low don't have alpha-tint counterparts.

**File:** `frontend/src/styles/theme.css`

Add to the `Signal tints` block (theme.css:67–71 currently). Place adjacent to `--tint-danger` to keep tint family contiguous.

```css
  /* Signal tints — background-color only, never border-color */
  --tint-breakout:      rgba(34,197,94,0.08);
  --tint-move:          rgba(245,158,11,0.08);
  --tint-watch:         rgba(251,146,60,0.08);

  /* Severity tints (high reuses --tint-danger; med/low are dedicated) */
  --tint-severity-med:  rgba(245,158,11,0.08);     /* NEW — amber, alpha-08 of --severity-med */
  --tint-severity-low:  rgba(107,114,128,0.08);    /* NEW — grey,  alpha-08 of --severity-low */
```

Naming rationale: `--tint-danger` (existing) is the semantic alias for "danger context" — used by high-severity here, but also reusable for future error-state row tints elsewhere. `--tint-severity-med/-low` are dedicated to the alert-severity ramp (no other consumer planned). Both will be wired up in commit 2 — neither lands as dead config.

Why not introduce a new `color-mix()` pattern instead? Considered, rejected. The codebase has zero `color-mix()` usage today; adding it for one consumer site is a new pattern with marginal benefit. Two more rgba tokens follow the established pattern for ~2 extra LOC.

**Verified by:**
- `cd frontend && npm run build` — passes.
- `getComputedStyle(document.documentElement).getPropertyValue('--tint-severity-med')` → `"rgba(245,158,11,0.08)"`.
- Site visual: zero diff (no consumers yet).

**Commit message:**

```
feat(theme): add --tint-severity-{med,low} for alert row washes

The 2026-05-07 audit's PR #6 plan called for tinting alert rows by
severity. --tint-danger (existing) covers high-severity; med and low
have no alpha-tint counterparts in the existing scale. Adding two
tokens dedicated to the alert-severity ramp.

Tokens added:
  --tint-severity-med:  rgba(245,158,11,0.08)   (alpha-08 of --severity-med)
  --tint-severity-low:  rgba(107,114,128,0.08)  (alpha-08 of --severity-low)

Pure addition — both consumed by commit 2 (the AlertsPage migration).
Neither lands as dead config.

--tint-danger keeps its current name; "danger" stays a semantic alias
("danger context, any source") rather than being renamed
--tint-severity-high. Future error-state tints elsewhere can reuse
--tint-danger without coupling to alert severity.

Verified:
- Build: cd frontend && npm run build => no errors
- getComputedStyle resolves both new tokens to expected values
- grep --tint-severity theme.css => 2 lines (was 0)
```

---

## Commit 2 — `fix(alerts): resolve invalid-CSS row tint and decouple severity from signal palette`

**Concern:** fix the AlertsPage:100 broken-CSS bug AND complete the audit-locked decoupling of alert severity from the signal palette.

### 2.1 — Add `lib/alertSeverity.ts` helper + test

Mirrors the `parseTier` / `tierBadge` pattern. The helper makes the bug regression-testable: a `var()` reference can never accidentally be concatenated with `08` again, because the helper returns the full token reference as a string.

`frontend/src/lib/alertSeverity.ts`:

```ts
import type { AlertEvent } from '../types/api'

export type Severity = AlertEvent['severity']  // 'high' | 'medium' | 'low'

export interface AlertSeverityStyles {
  /** Solid colour — used for border-left accent and the unread-status dot. */
  accent: string
  /** Low-alpha row wash — used as background-color on unread rows. */
  tint: string
}

/**
 * Map an alert severity to its visual treatment.
 *
 * Decoupled from the signal palette (--breakout, --move, --watch) per the
 * 2026-05-07 audit decision: alert severity and signal label are distinct
 * concepts, and reusing the signal greens / oranges for alerts produces
 * "high-severity reads as good-news colour" semantic clash.
 *
 * Regression guard: the previous AlertsPage implementation concatenated
 * `var(--breakout)` with `08` at runtime to produce a row tint, which
 * is invalid CSS — the background declaration was silently dropped.
 * Returning fully-formed token references here makes that class of bug
 * structurally impossible.
 */
export function alertSeverityStyles(severity: Severity): AlertSeverityStyles {
  if (severity === 'high') {
    return { accent: 'var(--severity-high)', tint: 'var(--tint-danger)' }
  }
  if (severity === 'medium') {
    return { accent: 'var(--severity-med)', tint: 'var(--tint-severity-med)' }
  }
  return { accent: 'var(--severity-low)', tint: 'var(--tint-severity-low)' }
}
```

`frontend/src/lib/alertSeverity.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { alertSeverityStyles } from './alertSeverity'

describe('alertSeverityStyles', () => {
  it("returns --severity-high + --tint-danger for 'high'", () => {
    const s = alertSeverityStyles('high')
    expect(s.accent).toBe('var(--severity-high)')
    expect(s.tint).toBe('var(--tint-danger)')
  })

  it("returns --severity-med + --tint-severity-med for 'medium'", () => {
    const s = alertSeverityStyles('medium')
    expect(s.accent).toBe('var(--severity-med)')
    expect(s.tint).toBe('var(--tint-severity-med)')
  })

  it("returns --severity-low + --tint-severity-low for 'low'", () => {
    const s = alertSeverityStyles('low')
    expect(s.accent).toBe('var(--severity-low)')
    expect(s.tint).toBe('var(--tint-severity-low)')
  })

  it('returns full token strings (no runtime concatenation)', () => {
    // Regression guard for the AlertsPage.tsx:100 bug: any value that
    // contains "var(" and ends with a separate alpha suffix at runtime
    // produces invalid CSS. The helper must return ONLY tokens or hex.
    for (const sev of ['high', 'medium', 'low'] as const) {
      const { accent, tint } = alertSeverityStyles(sev)
      expect(accent).toMatch(/^var\(--/)
      expect(tint).toMatch(/^var\(--/)
    }
  })
})
```

The fourth test is the structural regression guard — even if someone later "optimises" the helper by reverting to the broken pattern, this test fails.

### 2.2 — Update `AlertsPage.tsx`

**Remove** the `SEVERITY_COLOR` const at lines 10–14 entirely.

**Add** import at the top:
```ts
import { alertSeverityStyles } from '../lib/alertSeverity'
```

**Update the three use sites** (lines 99, 100, 104):

Before (lines 91–104):
```tsx
return (
  <div
    key={alert.id}
    onClick={() => handleRead(alert.id)}
    style={{
      padding: '14px 20px',
      borderBottom: i < displayedAlerts.length - 1 ? '1px solid var(--border-subtle)' : 'none',
      display: 'flex', alignItems: 'center', gap: 14,
      cursor: 'pointer',
      borderLeft: isRead ? '3px solid transparent' : `3px solid ${SEVERITY_COLOR[alert.severity]}`,
      background: isRead ? 'transparent' : `${SEVERITY_COLOR[alert.severity]}08`,
      transition: 'background 0.15s',
    }}
  >
    <div style={{ width: 8, height: 8, borderRadius: '50%', flexShrink: 0, background: isRead ? 'transparent' : SEVERITY_COLOR[alert.severity] }} />
```

After:
```tsx
const sev = alertSeverityStyles(alert.severity)
return (
  <div
    key={alert.id}
    onClick={() => handleRead(alert.id)}
    style={{
      padding: '14px 20px',
      borderBottom: i < displayedAlerts.length - 1 ? '1px solid var(--border-subtle)' : 'none',
      display: 'flex', alignItems: 'center', gap: 14,
      cursor: 'pointer',
      borderLeft: isRead ? '3px solid transparent' : `3px solid ${sev.accent}`,
      background: isRead ? 'transparent' : sev.tint,
      transition: 'background 0.15s',
    }}
  >
    <div style={{ width: 8, height: 8, borderRadius: '50%', flexShrink: 0, background: isRead ? 'transparent' : sev.accent }} />
```

Three changes:
1. `borderLeft`: `${SEVERITY_COLOR[alert.severity]}` → `${sev.accent}` — same template-literal pattern, but `sev.accent` is `var(--severity-high)` which composes correctly inside `3px solid var(...)`. (CSS shorthand allows `var()` inside; that's valid syntax.)
2. `background`: `${SEVERITY_COLOR[alert.severity]}08` → `sev.tint` — **bug fix.** The old runtime concatenation produced `var(--breakout)08` which is invalid; the new `sev.tint` is `var(--tint-danger)` which is valid.
3. `background` of the dot: `SEVERITY_COLOR[alert.severity]` → `sev.accent` — purely a rename, semantically identical.

**Visual changes from this fix (intentional):**
- High-severity unread rows: gain a faint red background wash (was: no wash — bug). This is the audit-flagged production bug now fixed.
- Border-left accent and dot: red instead of green for high-severity (was: `var(--breakout)` = green from PR #51's SEVERITY_COLOR mapping). Audit-locked decoupling.
- Medium-severity rows: amber instead of `var(--move)` — same hue (#f59e0b in both), pixel-identical.
- Low-severity rows: grey instead of `var(--watch)` — different colour (was orange-ish #fb923c, now neutral grey #6b7280). Audit-locked decoupling.

**Verified by:**
- `npm run build && npm test` — pass; new `alertSeverity.test.ts` adds 4 assertions, all green.
- Browser DevTools on `/alerts` with at least one unread high-severity alert: row's `background` resolves to `rgba(239,68,68,0.08)` (red wash) — was empty before due to the bug.
- Browser DevTools on `/alerts` with unread medium / low: backgrounds resolve to `rgba(245,158,11,0.08)` and `rgba(107,114,128,0.08)` respectively — were also empty before (same bug, all severities).
- `grep -rEn '\$\{[^}]+\}[0-9a-fA-F]{2}\b' frontend/src --include="*.tsx"` returns 0 matches — the broken-CSS pattern is gone codebase-wide. Was 1 match (AlertsPage:100).
- `grep -n "SEVERITY_COLOR" frontend/src/pages/AlertsPage.tsx` returns 0 — old const fully removed.

**Commit message:**

```
fix(alerts): resolve invalid-CSS row tint and decouple severity from signal palette

Two coupled fixes that were one bug all along.

(1) Bug fix — AlertsPage.tsx:100 produced INVALID CSS in production.
The pattern `${SEVERITY_COLOR[alert.severity]}08` evaluated at runtime
to `var(--breakout)08`, which browsers cannot parse — the background
declaration was silently dropped. Result: unread alert rows had no
severity tint visible to users at any severity level.

CSS spec note: var() resolution happens before the surrounding shorthand
is parsed, but the var() reference itself is a token. You can't
concatenate a separate hex-alpha suffix onto it as a string at runtime
and expect the browser to splice it into the resolved hex. The fix is
to return a complete, parser-safe token reference from a typed helper
rather than constructing the string at the call site.

(2) Audit-locked decoupling — alert severity stops reusing the signal
palette (--breakout / --move / --watch). High-severity reading as
"breakout green" (the same colour the product uses for "this card just
went up") was a semantic clash. Now: severity-high uses --severity-high
(red, dedicated), severity-medium uses --severity-med (amber), severity-low
uses --severity-low (grey).

Implementation: new lib/alertSeverity.ts helper mirrors the parseTier /
tierBadge pattern. alertSeverityStyles(severity) returns { accent, tint }
both as full var(--token-name) strings. Test guards: assertion that all
return values match /^var\(--/ — even if someone later "optimises" by
reverting to runtime concatenation, the test fails.

Visual changes (all intentional, all per audit-locked decisions):
- High unread: gains red row wash (was: no wash, the bug)
- High accent: red (was: green from previous SEVERITY_COLOR['high'] = --breakout)
- Medium unread: amber row wash (was: no wash) — colour pixel-identical to old
- Low accent: grey (was: orange-ish --watch) — neutral now
- Low unread: grey row wash (was: no wash)

Verified:
- Build + tests: pass; lib/alertSeverity.test.ts adds 4 assertions
- DevTools on /alerts: unread row backgrounds resolve to expected
  rgba (was: empty / dropped)
- grep '${...}NN' broken-CSS pattern => 0 codebase-wide (was 1)
- grep SEVERITY_COLOR AlertsPage.tsx => 0 (const fully replaced)

Closes the 2026-05-07 audit's B1 (bug, P1) and B2 (semantic decoupling,
P2) findings.
```

---

## After both commits land on the branch

1. Push: `git push -u origin fix/alerts-color-tint-bug`
2. Open PR via `gh pr create --base main --title 'fix(alerts): resolve invalid-CSS row tint + decouple severity from signal palette (PR #6)'`. Body: copy both commit messages.
3. Codex Cloud auto-review (5–10 min). Fallback: `@codex review`.
4. Manual verification before merge:
   - `/alerts` with unread alerts of each severity — every row has a visible faint coloured wash matching its severity
   - Mark all read — washes disappear (only border-left + dot stay coloured for unread; transparent for read)
   - Hover an unread row — wash + cursor:pointer behave normally
5. Merge after review-gate green.

---

## What this PR does NOT do

- **Does not extend the helper to other components.** Only AlertsPage uses severity today. If a future feature (e.g., a digest-email preview, a discord-alert preview pane) needs severity treatment, reuse `alertSeverityStyles()` then.
- **Does not unify the dot/border colour with the row tint** beyond what's already coupled. They're different shades by design (solid accent + faint wash); the helper returns both as separate fields so callers compose explicitly.
- **Does not touch the emoji selection at AlertsPage:106** (`severity === 'high' ? '🔥' : ...`). Glyphs aren't styling tokens; that ternary stays inline as content logic.

---

## Cumulative state after PR #6 merges

- All audit P0/P1 issues resolved:
  - 3 missing tokens (PR #1) ✅
  - AlertsPage `${color}08` invalid CSS (PR #6) ✅ this PR
- All locked decisions implemented:
  - PLUS badge (PR #4) ✅
  - severity decoupling (PR #6) ✅ this PR
  - light-mode won't-fix (PR #1 README note) ✅
  - title fix (PR #1) ✅
- Remaining work: PR #5 (inline-style migration, ~344 sites, ~3h, mechanical refactor).

After PR #6 merges, **PR #5 is the only thing left in the original 6-PR plan.** PR #5 can be opened immediately or batched (the design system is fully functional without it; PR #5 is hygiene/maintainability, not correctness).
