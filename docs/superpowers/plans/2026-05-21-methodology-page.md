# Methodology Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the public `/methodology` page — a static, math-rich credibility anchor for the Public Calls feature, documenting the prediction system, driver attribution rules, Brier score math, and known limitations.

**Architecture:** Static TSX page under the existing `PublicCallsLayout` shell; KaTeX loaded from CDN and triggered via `useEffect` + `renderMathInElement` after React mounts. No new API calls — methodology version reads from `import.meta.env.VITE_GIT_COMMIT_SHA`. Ten sections rendered inline as a single component file.

**Tech Stack:** React 18 + TypeScript, react-router-dom v7, KaTeX 0.16.11 (CDN), existing theme.css design tokens.

---

## File Structure

| Action | Path | Purpose |
|---|---|---|
| Modify | `frontend/index.html` | Add KaTeX CSS + JS CDN links |
| Create | `frontend/src/pages/calls/MethodologyPage.tsx` | All 10 sections, math rendering via useEffect |
| Modify | `frontend/src/main.tsx` | Register `/methodology` route under PublicCallsLayout |

`CallsPage.tsx` already links to `/methodology` at line 123 — no change needed there.

---

## Task 1: Add KaTeX CDN to index.html

**Files:**
- Modify: `frontend/index.html`

KaTeX auto-render detects `$$...$$` (display) and `$...$` (inline) patterns in DOM text nodes after React renders. We load via CDN so no npm install is needed.

- [ ] **Step 1: Add KaTeX CDN links to `<head>`**

Open `frontend/index.html`. Replace the current `<head>` block with:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Flashcard Planet</title>
    <!-- KaTeX — only used on /methodology; loaded globally for simplicity -->
    <link
      rel="stylesheet"
      href="https://cdnjs.cloudflare.com/ajax/libs/KaTeX/0.16.11/katex.min.css"
      crossorigin="anonymous"
    />
    <script
      defer
      src="https://cdnjs.cloudflare.com/ajax/libs/KaTeX/0.16.11/katex.min.js"
      crossorigin="anonymous"
    ></script>
    <script
      defer
      src="https://cdnjs.cloudflare.com/ajax/libs/KaTeX/0.16.11/contrib/auto-render.min.js"
      crossorigin="anonymous"
    ></script>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 2: Verify dev server still starts**

```
cd frontend && npm run dev
```

Expected: no errors in terminal, browser opens without console errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/index.html
git commit -m "feat(methodology): add KaTeX CDN to index.html"
```

---

## Task 2: Create MethodologyPage.tsx

**Files:**
- Create: `frontend/src/pages/calls/MethodologyPage.tsx`

This is the main deliverable. One file, ten sections, all inline styles following the existing `CallsPage.tsx` pattern (no Tailwind, all CSS vars from `theme.css`). KaTeX auto-render is called once on mount via `useEffect`.

Math strings use `$$...$$` delimiters so KaTeX auto-render processes them. They appear as JSX string literals inside `<span>` elements.

- [ ] **Step 1: Create the file with full content**

Create `frontend/src/pages/calls/MethodologyPage.tsx`:

```tsx
import { useEffect } from 'react'

declare global {
  interface Window {
    renderMathInElement?: (el: HTMLElement, opts?: object) => void
  }
}

const VERSION = import.meta.env.VITE_GIT_COMMIT_SHA
  ? `v0.1-${(import.meta.env.VITE_GIT_COMMIT_SHA as string).slice(0, 7)}`
  : 'v0.1'

const TODAY = new Date().toISOString().slice(0, 10)

// ── Shared style helpers ──────────────────────────────────────────────────────

const S = {
  page: {
    maxWidth: 760,
    margin: '0 auto',
    padding: '48px 24px 96px',
    lineHeight: 1.75,
  } as React.CSSProperties,

  h1: {
    fontFamily: 'Syne, sans-serif',
    fontSize: 'clamp(26px, 5vw, 40px)',
    fontWeight: 800,
    color: 'var(--text-primary)',
    marginBottom: 16,
    letterSpacing: '-0.5px',
  } as React.CSSProperties,

  lead: {
    fontSize: 15,
    color: 'var(--text-secondary)',
    lineHeight: 1.75,
    marginBottom: 8,
  } as React.CSSProperties,

  meta: {
    fontFamily: "'Space Mono', monospace",
    fontSize: 11,
    color: 'var(--text-muted)',
  } as React.CSSProperties,

  h2: {
    fontFamily: 'Syne, sans-serif',
    fontSize: 20,
    fontWeight: 700,
    color: 'var(--text-primary)',
    margin: '56px 0 16px',
    paddingTop: 8,
    borderTop: '1px solid var(--border-subtle)',
  } as React.CSSProperties,

  h3: {
    fontFamily: "'Space Mono', monospace",
    fontSize: 12,
    fontWeight: 700,
    color: 'var(--gold)',
    letterSpacing: '0.06em',
    textTransform: 'uppercase' as const,
    margin: '28px 0 10px',
  } as React.CSSProperties,

  p: {
    fontSize: 14,
    color: 'var(--text-secondary)',
    lineHeight: 1.8,
    marginBottom: 14,
  } as React.CSSProperties,

  code: {
    fontFamily: "'Space Mono', monospace",
    fontSize: 12,
    background: 'var(--bg-elevated)',
    border: '1px solid var(--border-subtle)',
    borderRadius: 'var(--radius-sm)',
    padding: '2px 6px',
    color: 'var(--text-primary)',
  } as React.CSSProperties,

  pre: {
    fontFamily: "'Space Mono', monospace",
    fontSize: 12,
    background: 'var(--bg-elevated)',
    border: '1px solid var(--border-subtle)',
    borderRadius: 'var(--radius-md)',
    padding: '16px 20px',
    color: 'var(--text-primary)',
    overflowX: 'auto' as const,
    margin: '12px 0 20px',
    lineHeight: 1.6,
    whiteSpace: 'pre' as const,
  } as React.CSSProperties,

  table: {
    width: '100%',
    borderCollapse: 'collapse' as const,
    fontSize: 13,
    marginBottom: 20,
  } as React.CSSProperties,

  th: {
    fontFamily: "'Space Mono', monospace",
    fontSize: 11,
    color: 'var(--text-muted)',
    textAlign: 'left' as const,
    padding: '8px 12px',
    borderBottom: '1px solid var(--border-subtle)',
    fontWeight: 700,
  } as React.CSSProperties,

  td: {
    padding: '9px 12px',
    color: 'var(--text-secondary)',
    borderBottom: '1px solid var(--border-subtle)',
    verticalAlign: 'top' as const,
  } as React.CSSProperties,

  tdCode: {
    padding: '9px 12px',
    fontFamily: "'Space Mono', monospace",
    fontSize: 12,
    color: 'var(--gold)',
    borderBottom: '1px solid var(--border-subtle)',
    verticalAlign: 'top' as const,
  } as React.CSSProperties,

  mathBlock: {
    fontFamily: "'Space Mono', monospace",
    fontSize: 13,
    background: 'var(--bg-elevated)',
    border: '1px solid var(--border-subtle)',
    borderRadius: 'var(--radius-md)',
    padding: '16px 20px',
    margin: '12px 0 20px',
    overflowX: 'auto' as const,
    color: 'var(--text-primary)',
  } as React.CSSProperties,

  tocItem: {
    display: 'block',
    fontSize: 13,
    color: 'var(--text-muted)',
    padding: '4px 0',
    fontFamily: "'Space Mono', monospace",
  } as React.CSSProperties,

  limitationN: {
    fontFamily: "'Space Mono', monospace",
    fontSize: 11,
    color: 'var(--gold)',
    fontWeight: 700,
    marginRight: 8,
  } as React.CSSProperties,

  note: {
    fontSize: 12,
    color: 'var(--text-muted)',
    fontStyle: 'italic' as const,
    lineHeight: 1.6,
    marginTop: 8,
  } as React.CSSProperties,

  divider: {
    border: 'none',
    borderTop: '1px solid var(--border-subtle)',
    margin: '40px 0',
  } as React.CSSProperties,
}

// ── Small presentational helpers ─────────────────────────────────────────────

function Code({ children }: { children: string }) {
  return <code style={S.code}>{children}</code>
}

function Pre({ children }: { children: string }) {
  return <pre style={S.pre}>{children}</pre>
}

// Math block: KaTeX auto-render processes $$...$$ inside text nodes.
function Math({ tex }: { tex: string }) {
  return (
    <div style={S.mathBlock}>
      {`$$${tex}$$`}
    </div>
  )
}

function Table({ head, rows }: { head: string[]; rows: string[][] }) {
  return (
    <table style={S.table}>
      <thead>
        <tr>
          {head.map(h => <th key={h} style={S.th}>{h}</th>)}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, i) => (
          <tr key={i}>
            {row.map((cell, j) => (
              <td key={j} style={j === 0 ? S.tdCode : S.td}>{cell}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

// ── Page component ────────────────────────────────────────────────────────────

export default function MethodologyPage() {
  useEffect(() => {
    const el = document.getElementById('methodology-content')
    if (!el) return
    // KaTeX auto-render is loaded via CDN with `defer` — may arrive slightly
    // after React hydrates. Poll briefly before giving up.
    let attempts = 0
    const id = setInterval(() => {
      attempts++
      if (typeof window.renderMathInElement === 'function') {
        clearInterval(id)
        window.renderMathInElement(el, {
          delimiters: [
            { left: '$$', right: '$$', display: true },
            { left: '$', right: '$', display: false },
          ],
          throwOnError: false,
        })
      } else if (attempts >= 20) {
        clearInterval(id)
      }
    }, 100)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    document.title = 'Methodology — Flashcard Planet'
    const desc = document.querySelector('meta[name="description"]')
    if (desc) {
      desc.setAttribute(
        'content',
        'How Flashcard Planet generates, locks, resolves, and grades its predictions. Brier scores, reliability diagrams, driver attribution.'
      )
    }
    return () => { document.title = 'Flashcard Planet' }
  }, [])

  return (
    <main id="methodology-content" style={S.page}>

      {/* ── 1. Header ────────────────────────────────────────────────────── */}
      <div style={{ marginBottom: 40 }}>
        <h1 style={S.h1}>Methodology</h1>
        <p style={S.lead}>
          Flashcard Planet publishes forecasts and grades its own accuracy.
          This page documents how. No claims are made here that aren't backed
          by math, citations, or explicit limitations.
        </p>
        <div style={{ display: 'flex', gap: 24, marginTop: 16 }}>
          <span style={S.meta}>Last updated: {TODAY}</span>
          <span style={S.meta}>Methodology version: {VERSION}</span>
        </div>
      </div>

      {/* ── 2. What this page is ─────────────────────────────────────────── */}
      <h2 style={S.h2}>What this page is</h2>
      <p style={S.p}>
        Every prediction on flashcardplanet.com/calls is locked at creation,
        resolved automatically against market data, and aggregated into a public
        Brier score. This page documents the system in enough detail that a
        competent reader can independently verify our calibration. If anything
        below is unclear, we'd consider that a documentation bug.
      </p>

      {/* ── 3. The four parts of a prediction ───────────────────────────── */}
      <h2 style={S.h2}>The four parts of a Flashcard Planet prediction</h2>
      <p style={S.p}>A prediction has four locked components:</p>
      <ol style={{ paddingLeft: 20, margin: '0 0 16px' }}>
        {[
          ['Target', 'A specific card variant (e.g. "Charizard 1st Edition Base Set PSA 10")'],
          ['Threshold', 'A specific price level + direction (e.g. "below $X" or "above $X" or "within band [low, high]")'],
          ['Resolution date', 'Exact UTC timestamp when the prediction resolves'],
          ['Stated probability', 'Our model\'s probability (0.0–1.0) that the threshold condition will be met by the resolution date'],
        ].map(([term, def]) => (
          <li key={term} style={{ fontSize: 14, color: 'var(--text-secondary)', marginBottom: 10 }}>
            <strong style={{ color: 'var(--text-primary)' }}>{term}</strong> — {def}
          </li>
        ))}
      </ol>
      <h3 style={S.h3}>Immutability</h3>
      <p style={S.p}>
        Once created, none of these four components can be modified. This is
        enforced at the database level via triggers — not policy, architecture.
        If we wanted to change a prediction after creation, we couldn't, even
        by mistake.
      </p>

      {/* ── 4. Driver attribution ────────────────────────────────────────── */}
      <h2 style={S.h2}>Driver attribution</h2>
      <p style={S.p}>
        For every signal we observe, we attempt to attribute the move to a
        primary driver. This creates a second dimension orthogonal to the signal
        tier (BREAKOUT / MOVE / WATCH / IDLE).
      </p>

      <h3 style={S.h3}>Driver taxonomy</h3>
      <Table
        head={['Driver', 'Definition']}
        rows={[
          ['MACRO', 'Overall market or set-level trend affecting the card'],
          ['META_SHIFT', 'Competitive meta change (relevant primarily for play-driven TCGs)'],
          ['SUPPLY_SHOCK', 'Reprint announcement, grading population update, sealed product release dilution'],
          ['EVENT_DRIVEN', 'Influencer activity, content publication, tournament result, or release within explicit event windows'],
          ['INFLUENCER_PROVENANCE', 'Celebrity-owned card premium (e.g. Logan Paul "Break" pedigree)'],
          ['UNKNOWN', 'Abnormal move detected, attribution unclear'],
        ]}
      />

      <h3 style={S.h3}>Attribution method (v1)</h3>
      <p style={S.p}>
        Rule-based engine. For each signal, evaluate these rules <em>in order</em>,
        stop at first match:
      </p>
      <ol style={{ paddingLeft: 20, margin: '0 0 16px' }}>
        {[
          'EVENT_DRIVEN (influencer/tournament) — INFLUENCER or TOURNAMENT event matching this card within window',
          'MACRO — ≥60% of cards in the same set show same signal direction. RELEASE event corroborates if present.',
          'SUPPLY_SHOCK — SUPPLY event within window + 14-day trailing buffer',
          'EVENT_DRIVEN (release-specific) — RELEASE event explicitly listing this card\'s UUID in affected_asset_ids',
          'Default: UNKNOWN with low confidence',
        ].map((rule, i) => (
          <li key={i} style={{ fontSize: 14, color: 'var(--text-secondary)', marginBottom: 8 }}>
            {rule}
          </li>
        ))}
      </ol>

      <h3 style={S.h3}>Confidence formula</h3>
      <Math tex={`\\text{recency}(t) = \\max\\!\\left(0,\\; 1 - \\frac{\\text{days\\_since\\_event}}{\\text{expected\\_window\\_days}}\\right)`} />
      <Math tex={`\\text{confidence} = \\text{recency}(t) \\times \\text{event\\_type\\_weight} \\times \\text{extra\\_multiplier}`} />
      <Table
        head={['Event type', 'Weight', 'Notes']}
        rows={[
          ['INFLUENCER', '0.90', 'Highest signal-to-noise'],
          ['RELEASE', '0.75', 'Predictable, well-documented, high impact'],
          ['TOURNAMENT', '0.70', 'Meta-shift indicator'],
          ['SUPPLY', '0.68', '0.85 base × 0.8 lookback adjustment for wider window'],
        ]}
      />

      <h3 style={S.h3}>Tiebreaker</h3>
      <p style={S.p}>
        When two or more events match the same card within their respective
        windows, the event with the <strong>highest confidence</strong> wins.
        Recency is used as a tiebreaker only when confidence values are equal.
        This prevents a recent low-weight event from overriding an older but
        structurally stronger driver.
      </p>

      <h3 style={S.h3}>Contamination window</h3>
      <p style={S.p}>
        The contamination window around each event is asymmetric:
      </p>
      <ul style={{ paddingLeft: 20, margin: '0 0 16px' }}>
        <li style={{ fontSize: 14, color: 'var(--text-secondary)', marginBottom: 8 }}>
          <strong style={{ color: 'var(--text-primary)' }}>Lead-in: 3 days before</strong>{' '}
          <Code>event_date</Code> — captures anticipation effects (leaks,
          datamined content, scheduled marketing campaigns building hype)
        </li>
        <li style={{ fontSize: 14, color: 'var(--text-secondary)', marginBottom: 8 }}>
          <strong style={{ color: 'var(--text-primary)' }}>Tail:</strong>{' '}
          <Code>expected_window_days + 2 days</Code> — buffer for delayed decay
          beyond the event's nominal window
        </li>
      </ul>
      <p style={S.p}>
        <Code>UNKNOWN</Code> is a valid output. We'd rather report honest
        uncertainty than fabricate a driver. Some fraction of attributions will
        be <Code>UNKNOWN</Code> — that's a floor we accept, not a bug to suppress.
      </p>

      <h3 style={S.h3}>Why this matters for predictions</h3>
      <p style={S.p}>
        Driver attribution makes the prediction reasoning transparent. A{' '}
        <Code>BREAKOUT</Code> card driven by <Code>EVENT_DRIVEN</Code>{' '}
        (e.g. a one-off YouTube video) should be expected to revert. A{' '}
        <Code>BREAKOUT</Code> driven by <Code>SUPPLY_SHOCK</Code>{' '}
        (e.g. confirmed reprint cancellation) is structural.
      </p>

      {/* ── 5. Brier score ───────────────────────────────────────────────── */}
      <h2 style={S.h2}>Brier score & calibration</h2>
      <h3 style={S.h3}>Formula</h3>
      <p style={S.p}>
        For a single prediction with stated probability <em>p</em> and actual
        outcome <em>o ∈ {'{0, 1}'}</em>:
      </p>
      <Math tex={`BS_i = (p_i - o_i)^2`} />
      <p style={S.p}>Across N resolved predictions:</p>
      <Math tex={`\\text{Mean Brier} = \\frac{1}{N} \\sum_{i=1}^{N} (p_i - o_i)^2`} />

      <h3 style={S.h3}>Interpretation</h3>
      <Table
        head={['Score', 'Meaning']}
        rows={[
          ['0.0', 'Perfect — all high-confidence calls hit, all low-confidence missed correctly'],
          ['0.25', 'Baseline — equivalent to always predicting 50%'],
          ['1.0', 'Worst case — systematically inverted predictions'],
        ]}
      />
      <p style={S.p}>
        Any model claiming forecasting value must beat the 0.25 baseline.
        Models with Mean Brier {'>'} 0.25 are worse than coin flips.
      </p>
      <p style={S.note}>
        Reference: Brier, G. W. (1950). "Verification of Forecasts Expressed in Terms
        of Probability." <em>Monthly Weather Review</em>, 78(1), 1–3.
      </p>

      {/* ── 6. Reliability diagram ───────────────────────────────────────── */}
      <h2 style={S.h2}>Reliability diagram</h2>
      <p style={S.p}>
        Brier score is a single number. The reliability diagram shows whether
        the model is calibrated <em>at all probability levels</em>, not just on
        average.
      </p>

      <h3 style={S.h3}>Construction</h3>
      <ol style={{ paddingLeft: 20, margin: '0 0 16px' }}>
        {[
          'Bin all resolved predictions by stated probability into deciles: [0%, 10%), [10%, 20%), … [90%, 100%]',
          'For each bin: compute mean stated probability, actual hit rate, and 95% Wilson confidence interval on hit rate',
          'Plot (mean stated probability, actual hit rate) per bin',
          'Overlay diagonal reference line y = x',
        ].map((step, i) => (
          <li key={i} style={{ fontSize: 14, color: 'var(--text-secondary)', marginBottom: 8 }}>
            {step}
          </li>
        ))}
      </ol>

      <h3 style={S.h3}>Interpretation</h3>
      <ul style={{ paddingLeft: 20, margin: '0 0 16px' }}>
        {[
          'Points on diagonal = perfectly calibrated at that probability level',
          'Points above diagonal = under-confident (we said 60% but actually hit 75%)',
          'Points below diagonal = over-confident (we said 80% but only hit 55%)',
          'Wilson CI bars show statistical uncertainty per bin',
        ].map((item, i) => (
          <li key={i} style={{ fontSize: 14, color: 'var(--text-secondary)', marginBottom: 6 }}>
            {item}
          </li>
        ))}
      </ul>

      <h3 style={S.h3}>Wilson 95% CI formula</h3>
      <p style={S.p}>
        For <em>k</em> hits out of <em>n</em> trials at bin probability{' '}
        <Math tex={`\\hat{p} = k/n`} />
      </p>
      <Math tex={`\\text{center} = \\frac{\\hat{p} + z^2/(2n)}{1 + z^2/n}`} />
      <Math tex={`\\text{margin} = \\frac{z\\,\\sqrt{\\hat{p}(1-\\hat{p})/n + z^2/(4n^2)}}{1 + z^2/n},\\quad z = 1.96`} />
      <p style={S.note}>
        Reference: Wilson, E. B. (1927). "Probable inference, the law of succession,
        and statistical inference." <em>Journal of the American Statistical
        Association</em>, 22(158), 209–212.
      </p>

      {/* ── 7. Honest n discipline ───────────────────────────────────────── */}
      <h2 style={S.h2}>Honest n discipline</h2>
      <p style={S.p}>
        Calibration is meaningless at small sample sizes. We display calibration
        plots from n=1 onward but accompany them with explicit warnings:
      </p>
      <Table
        head={['n', 'Warning displayed']}
        rows={[
          ['< 10', 'Pre-calibration. Treat all numbers as directional only.'],
          ['10–29', 'Below statistical significance threshold. Indicative but not conclusive.'],
          ['30–99', 'Above minimum threshold. Calibration is meaningful but noisy.'],
          ['≥ 100', 'Full confidence in calibration interpretation.'],
        ]}
      />
      <p style={S.p}>
        We never hide the calibration plot. We never wait until "calibration
        looks good" to publish. The honesty <em>is</em> the methodology.
      </p>

      {/* ── 8. Methodology version log ───────────────────────────────────── */}
      <h2 style={S.h2}>Methodology version log</h2>
      <p style={S.p}>
        Every change to driver attribution rules, fundamental signal computation,
        or scheduler logic increments the methodology version. Each prediction
        carries the version that generated it, creating a reproducible audit
        trail.
      </p>
      <Table
        head={['Version', 'Date', 'Changes']}
        rows={[
          [VERSION, TODAY, 'Initial public launch — rule-based driver attribution v1, Brier score calibration, Wilson CI reliability diagram'],
        ]}
      />

      {/* ── 9. Known limitations ─────────────────────────────────────────── */}
      <h2 style={S.h2}>Known limitations</h2>
      <p style={S.p}>Stated openly. This section will grow over time.</p>

      {[
        [
          'Driver attribution is rule-based, not learned.',
          'No ML model. Confidence numbers come from rule heuristics, not statistical estimation.',
        ],
        [
          'Event registry is human-curated.',
          'We maintain the market_events table manually for high-impact events. Real-time event detection from social media, news, or content platforms is not yet implemented.',
        ],
        [
          'Fundamental signal assumes event windows have known duration.',
          'We use an asymmetric contamination window per event — 3 days before event_date and expected_window_days + 2 days after (defaulting to a 16-day total span when expected_window_days is unspecified). Cards with overlapping events may have noisy fundamental signals where windows stack.',
        ],
        [
          'Resolution scheduler runs every 4 hours.',
          'A prediction resolving at 14:00 may show as resolved at 14:00, 18:00, 22:00, or later — never earlier. Maximum 4-hour delay.',
        ],
        [
          'Single-source per TCG.',
          'YGO uses CardMarket EUR data converted via a fixed USD rate. Pokemon uses TCGPlayer market price. Cross-source reconciliation is a future improvement.',
        ],
        [
          'No backtesting on historical Public Calls.',
          'Calibration is forward-only from launch. We cannot retroactively claim historical accuracy.',
        ],
        [
          'Sample size grows slowly.',
          'We generate predictions only on cards where our model has confidence the prediction is meaningful. n grows at ~5–20 predictions per month, not hundreds. Calibration significance takes time.',
        ],
        [
          'Hype premium math is directionally correct but not apples-to-apples.',
          'The "actual delta" uses the standard signal pipeline (asset_signals.price_delta_pct), which may include event-contaminated prices. The "fundamental delta" uses a cleaned baseline. The difference indicates hype direction and approximate magnitude, but precise percentage-point values should be treated as estimates. Future improvement: unify both algorithms to use identical baseline windows.',
        ],
        [
          'Fundamental ≠ Actual even on uncontaminated cards.',
          'Small numerical differences arise from algorithmic divergence, not genuine hype premium. Hype premium values within roughly ±2 percentage points should be interpreted as "no meaningful hype" rather than "exact equilibrium". Larger values (>5pp) indicate genuine divergence.',
        ],
        [
          'MACRO attribution cannot be validated via historical replay.',
          'MACRO depends on set-wide signal breadth at the moment of attribution. We do not store historical signal snapshots. Today\'s asset_signals cannot reproduce a past set-wide rally. MACRO is verified forward-only via production observation, not retrospectively.',
        ],
        [
          'Some source URLs are not machine-verifiable.',
          'Five RELEASE events cite pokemon.com URLs that bot-block automated verification. We classify these as "plausible, source-class trusted" on the basis that The Pokemon Company is the authoritative source for its own release dates, independently corroborated by Bulbapedia and Pokemon TCG news sites.',
        ],
      ].map(([title, body], i) => (
        <div key={i} style={{ marginBottom: 20 }}>
          <p style={{ ...S.p, marginBottom: 4 }}>
            <span style={S.limitationN}>{i + 1}.</span>
            <strong style={{ color: 'var(--text-primary)' }}>{title}</strong>
          </p>
          <p style={{ ...S.p, marginLeft: 20, marginBottom: 0 }}>{body}</p>
        </div>
      ))}

      {/* ── 10. Sources & references ─────────────────────────────────────── */}
      <h2 style={S.h2}>Sources & references</h2>

      <h3 style={S.h3}>Statistical methods</h3>
      <ul style={{ paddingLeft: 20, margin: '0 0 16px' }}>
        <li style={{ fontSize: 14, color: 'var(--text-secondary)', marginBottom: 8 }}>
          Brier, G. W. (1950). "Verification of Forecasts Expressed in Terms of Probability."
          <em> Monthly Weather Review</em>, 78(1), 1–3.
        </li>
        <li style={{ fontSize: 14, color: 'var(--text-secondary)', marginBottom: 8 }}>
          Wilson, E. B. (1927). "Probable inference, the law of succession, and statistical inference."
          <em> Journal of the American Statistical Association</em>, 22(158), 209–212.
        </li>
      </ul>

      <h3 style={S.h3}>Calibration design inspiration</h3>
      <ul style={{ paddingLeft: 20, margin: '0 0 16px' }}>
        <li style={{ fontSize: 14, color: 'var(--text-secondary)', marginBottom: 8 }}>
          Polymarket public reliability methodology
        </li>
        <li style={{ fontSize: 14, color: 'var(--text-secondary)', marginBottom: 8 }}>
          Tetlock, P. E. (2005). <em>Expert Political Judgment</em> — long-horizon forecasting calibration
        </li>
      </ul>

      <h3 style={S.h3}>Pokemon TCG market data</h3>
      <ul style={{ paddingLeft: 20, margin: '0 0 16px' }}>
        <li style={{ fontSize: 14, color: 'var(--text-secondary)', marginBottom: 8 }}>
          TCGPlayer market price methodology
        </li>
        <li style={{ fontSize: 14, color: 'var(--text-secondary)', marginBottom: 8 }}>
          CardMarket public price guide — daily S3 export, EUR-denominated
        </li>
      </ul>

      <hr style={S.divider} />
      <p style={S.note}>
        Methodology version {VERSION} · Last updated {TODAY} ·{' '}
        <a href="/calls" style={{ color: 'var(--gold)' }}>View all calls →</a>
      </p>

    </main>
  )
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```
cd frontend && npx tsc --noEmit
```

Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/calls/MethodologyPage.tsx
git commit -m "feat(methodology): implement MethodologyPage with all 10 sections and KaTeX math"
```

---

## Task 3: Register /methodology route in main.tsx

**Files:**
- Modify: `frontend/src/main.tsx`

Add `/methodology` as a sibling of `/calls` under `PublicCallsLayout`.

- [ ] **Step 1: Add import and route**

Open `frontend/src/main.tsx`. Add the import after line 18 (after `CallsPage` import):

```tsx
import MethodologyPage from './pages/calls/MethodologyPage'
```

Then in the `<Routes>` block, add this route after the existing `/calls` block (after line 37):

```tsx
<Route path="/methodology" element={<PublicCallsLayout />}>
  <Route index element={<MethodologyPage />} />
</Route>
```

The complete updated routes section:

```tsx
<Routes>
  <Route path="/" element={<LandingPage />} />
  <Route path="/market" element={<DashboardPage />} />
  <Route path="/market/:assetId" element={<CardDetailPage />} />
  <Route path="/alerts" element={<AlertsPage />} />
  <Route path="/watchlist" element={<WatchlistPage />} />
  <Route path="/compare" element={<ComparePage />} />
  <Route path="/account" element={<AccountPage />} />
  <Route path="/account/digest-preferences" element={<DigestPreferencesPage />} />
  <Route path="/pricing" element={<PricingPage />} />
  <Route path="/sealed" element={<SealedPage />} />
  <Route path="/calls" element={<PublicCallsLayout />}>
    <Route index element={<CallsPage />} />
  </Route>
  <Route path="/methodology" element={<PublicCallsLayout />}>
    <Route index element={<MethodologyPage />} />
  </Route>
</Routes>
```

- [ ] **Step 2: Start dev server and navigate to /methodology**

```
cd frontend && npm run dev
```

Open browser at `http://localhost:5173/methodology`. Verify:
- Page renders with "Methodology" heading
- All 10 sections visible
- Math blocks display (either rendered KaTeX or raw `$$...$$` strings — KaTeX may not render in dev if CDN not loaded; that's OK, verify in production)
- No console errors

- [ ] **Step 3: Verify /calls link to /methodology still works**

Navigate to `http://localhost:5173/calls`. Find the "Methodology →" link (line 123 of CallsPage.tsx). Click it. Should navigate to `/methodology`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/main.tsx
git commit -m "feat(methodology): add /methodology route to router"
```

---

## Task 4: Update page title and SEO meta tags

**Files:**
- Modify: `frontend/index.html` (update `<title>`)

The `MethodologyPage.tsx` already sets `document.title` via `useEffect`. The `index.html` title tag should use the app name (not "frontend").

- [ ] **Step 1: Update index.html title**

In `frontend/index.html`, the `<title>` tag was already updated to "Flashcard Planet" in Task 1. Confirm it reads:

```html
<title>Flashcard Planet</title>
```

If it still says "frontend", update it now.

- [ ] **Step 2: Add meta description to index.html**

In `frontend/index.html`, add a default meta description inside `<head>` (after the `<meta charset>` line):

```html
<meta name="description" content="Flashcard Planet — AI-powered TCG price signals for serious collectors and investors." />
<meta property="og:title" content="Flashcard Planet" />
```

`MethodologyPage.tsx` overrides the description via `useEffect` when on `/methodology`.

- [ ] **Step 3: Commit**

```bash
git add frontend/index.html
git commit -m "feat(methodology): add default meta tags and fix page title"
```

---

## Task 5: PR, Codex review, deploy

**Files:** None new — PR creation only.

- [ ] **Step 1: Create PR**

```bash
git push origin main
```

Then open GitHub and create a PR if working from a feature branch. If working directly on main (per repo convention), verify Railway auto-deploy triggered.

- [ ] **Step 2: Wait for Railway deploy**

Monitor Railway dashboard for deploy completion (~2–3 min).

- [ ] **Step 3: Verify production**

Navigate to `https://flashcard-planet.up.railway.app/methodology`.

Check:
- [ ] Page renders with "Methodology" heading
- [ ] Math formulas render as typeset equations (KaTeX CDN loaded in prod)
- [ ] Version shows git SHA prefix (if `VITE_GIT_COMMIT_SHA` is set in Railway, otherwise shows "v0.1")
- [ ] All 10 sections visible with correct content
- [ ] No console errors in browser devtools
- [ ] `/calls` → "Methodology →" link navigates correctly
- [ ] Mobile: text wraps cleanly, math blocks scroll horizontally if needed
- [ ] `document.title` reads "Methodology — Flashcard Planet" on the methodology page

- [ ] **Step 4: Set VITE_GIT_COMMIT_SHA in Railway (optional)**

In Railway → Variables → Backend service, add:
```
VITE_GIT_COMMIT_SHA = ${{RAILWAY_GIT_COMMIT_SHA}}
```

This shows the actual git commit hash in the methodology version string after the next deploy.

- [ ] **Step 5: Run Codex review (per repo convention)**

```bash
codex exec review --base main --ephemeral -o /tmp/review.txt && cat /tmp/review.txt
```

Address any P0/P1 findings before considering Gate 6 ready for Ivan review.

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|---|---|
| `/methodology` route | Task 3 |
| `PublicCallsLayout` pattern | Task 3 (nested under same layout) |
| KaTeX for math | Task 1 (CDN) + Task 2 (useEffect) |
| All 10 sections | Task 2 |
| Space Mono for math/numbers, Syne for headings | Task 2 (S.h1, S.h2, S.code, S.meta) |
| Dark trading-desk aesthetic | Task 2 (all CSS vars from theme.css) |
| Methodology version auto-pulled | Task 2 (`import.meta.env.VITE_GIT_COMMIT_SHA`) |
| "Last updated" timestamp | Task 2 (`const TODAY = new Date()...`) |
| Link from /calls to /methodology | Already exists in CallsPage.tsx line 123 |
| SEO meta tags | Task 4 |
| Mobile rendering | Task 2 (`clamp()` font size, `overflowX: auto` on math blocks) |
| No auth required | Confirmed — route is outside authenticated layout |

**Known gaps:**
- Footer link "on every Flashcard Planet page" — out of scope for this PR (requires modifying the main NavBar/footer which touches many pages). Deferred to Gate 10 frontend changes.
- `/calls` prominent link above calls table — already exists at line 123.
- GitHub source link in methodology page — marked optional in spec, deferred to post-launch.
- KaTeX rendering in dev depends on CDN availability; math strings degrade gracefully to raw `$$...$$` text if CDN is blocked in dev environment.

**No placeholders found.** All code blocks are complete and reference-consistent.
