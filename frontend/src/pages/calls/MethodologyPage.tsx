import { useEffect } from 'react'
import { Link } from 'react-router-dom'

const s = {
  page: {
    maxWidth: 760,
    margin: '0 auto',
    padding: '56px 24px 96px',
  } as React.CSSProperties,

  h1: {
    fontFamily: 'Syne, sans-serif',
    fontWeight: 800,
    fontSize: 'clamp(24px, 4vw, 38px)',
    color: 'var(--text-primary)',
    marginBottom: 12,
    lineHeight: 1.15,
  } as React.CSSProperties,

  h2: {
    fontFamily: 'Syne, sans-serif',
    fontWeight: 700,
    fontSize: 20,
    color: 'var(--text-primary)',
    marginTop: 56,
    marginBottom: 16,
    paddingBottom: 8,
    borderBottom: '1px solid var(--border-subtle)',
  } as React.CSSProperties,

  h3: {
    fontFamily: 'Syne, sans-serif',
    fontWeight: 600,
    fontSize: 15,
    color: 'var(--text-primary)',
    marginTop: 28,
    marginBottom: 10,
  } as React.CSSProperties,

  p: {
    fontSize: 14,
    color: 'var(--text-secondary)',
    lineHeight: 1.75,
    marginBottom: 16,
  } as React.CSSProperties,

  formula: {
    display: 'block',
    fontFamily: "'Space Mono', monospace",
    fontSize: 13,
    color: 'var(--text-primary)',
    background: 'var(--bg-elevated)',
    border: '1px solid var(--border-subtle)',
    borderRadius: 'var(--radius-md)',
    padding: '14px 18px',
    marginBottom: 16,
    whiteSpace: 'pre-wrap',
    lineHeight: 1.7,
  } as React.CSSProperties,

  table: {
    width: '100%',
    borderCollapse: 'collapse' as const,
    fontSize: 13,
    marginBottom: 20,
  } as React.CSSProperties,

  note: {
    fontSize: 12,
    fontFamily: "'Space Mono', monospace",
    color: 'var(--text-muted)',
    background: 'var(--bg-surface)',
    border: '1px solid var(--border-subtle)',
    borderRadius: 'var(--radius-md)',
    padding: '10px 14px',
    marginBottom: 16,
  } as React.CSSProperties,

  divider: {
    border: 'none',
    borderTop: '1px solid var(--border-subtle)',
    margin: '48px 0',
  } as React.CSSProperties,

  meta: {
    fontSize: 11,
    fontFamily: "'Space Mono', monospace",
    color: 'var(--text-muted)',
  } as React.CSSProperties,
}

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th style={{
      textAlign: 'left',
      fontFamily: "'Space Mono', monospace",
      fontSize: 11,
      color: 'var(--text-muted)',
      padding: '8px 12px',
      borderBottom: '1px solid var(--border-subtle)',
      fontWeight: 400,
    }}>
      {children}
    </th>
  )
}

function Td({ children, mono }: { children: React.ReactNode; mono?: boolean }) {
  return (
    <td style={{
      padding: '9px 12px',
      borderBottom: '1px solid var(--border-subtle)',
      fontSize: 13,
      color: 'var(--text-secondary)',
      fontFamily: mono ? "'Space Mono', monospace" : undefined,
      verticalAlign: 'top',
    }}>
      {children}
    </td>
  )
}

function Code({ children }: { children: React.ReactNode }) {
  return (
    <code style={{
      fontFamily: "'Space Mono', monospace",
      fontSize: 12,
      color: 'var(--gold)',
      background: 'var(--bg-elevated)',
      padding: '1px 5px',
      borderRadius: 3,
    }}>
      {children}
    </code>
  )
}

export default function MethodologyPage() {
  useEffect(() => {
    document.title = 'Methodology — Flashcard Planet'
    const desc = document.querySelector('meta[name="description"]')
    if (desc) {
      desc.setAttribute('content', 'How Flashcard Planet generates, locks, resolves, and grades its predictions. Brier scores, reliability diagrams, driver attribution.')
    }
    return () => { document.title = 'Flashcard Planet' }
  }, [])

  return (
    <main style={s.page}>

      {/* ── Header ──────────────────────────────────────────────── */}
      <h1 style={s.h1}>Methodology</h1>
      <p style={{ ...s.p, maxWidth: 540 }}>
        Flashcard Planet publishes forecasts and grades its own accuracy.
        This page documents how. No claims are made here that aren't backed
        by math, citations, or explicit limitations.
      </p>
      <p style={s.meta}>Last updated: 2026-05-24 · Methodology version: v0.1</p>

      {/* ── Section 2 ───────────────────────────────────────────── */}
      <h2 style={s.h2}>What this page is</h2>
      <p style={s.p}>
        Every prediction on flashcardplanet.com/calls is locked at creation, resolved automatically against
        market data, and aggregated into a public Brier score. This page documents the system in enough
        detail that a competent reader can independently verify our calibration. If anything below is
        unclear, we'd consider that a documentation bug.
      </p>

      {/* ── Section 3 ───────────────────────────────────────────── */}
      <h2 style={s.h2}>The four parts of a Flashcard Planet prediction</h2>
      <p style={s.p}>A prediction has four locked components:</p>

      <table style={s.table}>
        <thead>
          <tr>
            <Th>#</Th>
            <Th>Component</Th>
            <Th>Example</Th>
          </tr>
        </thead>
        <tbody>
          {[
            ['1', 'Target', 'Charizard 1st Edition Base Set PSA 10'],
            ['2', 'Threshold', '"below $X" or "above $X" or "within band [low, high]"'],
            ['3', 'Resolution date', 'Exact UTC timestamp when the prediction resolves'],
            ['4', 'Stated probability', 'Model probability that threshold condition will be met (0.0–1.0)'],
          ].map(([n, comp, ex]) => (
            <tr key={n}>
              <Td mono>{n}</Td>
              <Td mono>{comp}</Td>
              <Td>{ex}</Td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3 style={s.h3}>Immutability</h3>
      <p style={s.p}>
        Once created, none of these four components can be modified. This is enforced at the database
        level — not policy, architecture. If we wanted to change a prediction after creation, we couldn't,
        even by mistake.
      </p>

      {/* ── Section 4 ───────────────────────────────────────────── */}
      <h2 style={s.h2}>Driver attribution</h2>
      <p style={s.p}>
        For every signal we observe, we attempt to attribute the move to a primary driver. This creates
        a second dimension orthogonal to the signal tier (BREAKOUT/MOVE/WATCH/IDLE).
      </p>

      <h3 style={s.h3}>Driver taxonomy</h3>
      <table style={s.table}>
        <thead>
          <tr>
            <Th>Driver</Th>
            <Th>Definition</Th>
          </tr>
        </thead>
        <tbody>
          {[
            ['MACRO', 'Overall market or set-level trend affecting the card'],
            ['META_SHIFT', 'Competitive meta change (primarily for play-driven TCGs)'],
            ['SUPPLY_SHOCK', 'Reprint announcement, grading population update, sealed product dilution'],
            ['EVENT_DRIVEN', 'Influencer activity, content publication, tournament result, or release within event windows'],
            ['INFLUENCER_PROVENANCE', 'Celebrity-owned card premium (e.g. Logan Paul pedigree)'],
            ['UNKNOWN', 'Abnormal move detected, attribution unclear'],
          ].map(([d, def]) => (
            <tr key={d}>
              <Td mono><Code>{d}</Code></Td>
              <Td>{def}</Td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3 style={s.h3}>Attribution method (v1)</h3>
      <p style={s.p}>
        Rule-based engine. For each signal, evaluate these rules <em>in order</em>, stop at first match:
      </p>
      <table style={s.table}>
        <thead>
          <tr>
            <Th>Rule</Th>
            <Th>Condition</Th>
            <Th>Result</Th>
          </tr>
        </thead>
        <tbody>
          {[
            ['1', 'INFLUENCER or TOURNAMENT event matches this card within window', 'EVENT_DRIVEN'],
            ['2', '≥60% of cards in same set show same signal direction', 'MACRO'],
            ['3', 'SUPPLY event within window + 14-day trailing buffer', 'SUPPLY_SHOCK'],
            ['4', 'RELEASE event explicitly lists this card UUID in affected_asset_ids', 'EVENT_DRIVEN'],
            ['5', 'No rule matched', 'UNKNOWN'],
          ].map(([r, cond, res]) => (
            <tr key={r}>
              <Td mono>{r}</Td>
              <Td>{cond}</Td>
              <Td mono><Code>{res}</Code></Td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3 style={s.h3}>Confidence formula</h3>
      <pre style={s.formula}>{`recency(t)  = max(0, 1 − days_since_event / expected_window_days)
confidence  = recency(t) × event_type_weight × extra_multiplier`}</pre>

      <p style={{ ...s.p, marginBottom: 8 }}>Event type weights (calibrated v1):</p>
      <table style={s.table}>
        <thead>
          <tr>
            <Th>Type</Th>
            <Th>Weight</Th>
            <Th>Notes</Th>
          </tr>
        </thead>
        <tbody>
          {[
            ['INFLUENCER', '0.90', 'Highest signal-to-noise'],
            ['RELEASE', '0.75', 'Predictable, well-documented, high impact'],
            ['TOURNAMENT', '0.70', 'Meta-shift indicator'],
            ['SUPPLY', '0.68', '0.85 base × 0.8 lookback adjustment for wider window'],
          ].map(([t, w, n]) => (
            <tr key={t}>
              <Td mono><Code>{t}</Code></Td>
              <Td mono>{w}</Td>
              <Td>{n}</Td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3 style={s.h3}>Contamination window (fundamental signal)</h3>
      <p style={s.p}>
        The contamination window around each event is asymmetric:
      </p>
      <ul style={{ paddingLeft: 20, marginBottom: 16 }}>
        <li style={{ ...s.p, marginBottom: 6 }}>
          <strong style={{ color: 'var(--text-primary)' }}>Lead-in: 3 days before</strong>{' '}
          <Code>event_date</Code> — captures anticipation effects (leaks, datamined content,
          scheduled marketing building hype).
        </li>
        <li style={{ ...s.p, marginBottom: 0 }}>
          <strong style={{ color: 'var(--text-primary)' }}>Tail: <Code>expected_window_days</Code> + 2 days</strong>{' '}
          — buffer for delayed decay beyond the event's nominal window.
        </li>
      </ul>
      <p style={s.p}>
        Symmetric windows would either over-capture (false positives on the leading edge) or
        under-capture (missing the trailing decay).
      </p>

      <h3 style={s.h3}>Seeding discipline</h3>
      <p style={s.p}>
        For RELEASE events, only Pokemon-marketed headline chase cards are listed in{' '}
        <Code>affected_asset_ids</Code>. Pre-populating every conceivable chase candidate would
        force EVENT_DRIVEN attribution by data choice rather than letting the model arrive at it
        from price/breadth evidence. This preserves the integrity of MACRO and UNKNOWN attributions
        on the same set's non-headline cards.
      </p>

      <p style={{ ...s.p, marginBottom: 8 }}>
        <Code>UNKNOWN</Code> is a valid output. Some fraction of attributions will be UNKNOWN — that's
        a floor we accept, not a bug to suppress.
      </p>

      <h3 style={s.h3}>Validation status (Gate 2 close, 2026-05-24)</h3>
      <table style={s.table}>
        <thead>
          <tr>
            <Th>Rule</Th>
            <Th>Status</Th>
            <Th>Notes</Th>
          </tr>
        </thead>
        <tbody>
          {[
            ['Rule 1 — EVENT_DRIVEN (INFLUENCER/TOURNAMENT)', 'Forward-validated', 'Historical INFLUENCER events target vintage cards outside coverage. Modern events accumulate forward.'],
            ['Rule 2 — MACRO (set breadth)', 'Forward-validated', 'Historical signal snapshots not stored. Production observation validates going forward.'],
            ['Rule 3 — SUPPLY_SHOCK', 'Forward-validated', 'No verified SUPPLY events in current registry. Validates as events accumulate.'],
            ['Rule 4 — EVENT_DRIVEN (release-specific)', 'Retrospectively validated', 'n=7 historical RELEASE events. 7/7 attribution accuracy. Confidence 0.60–0.74.'],
            ['Rule 5 — Default UNKNOWN', 'Implicitly validated', 'All Universe Gap test cases correctly returned UNKNOWN.'],
          ].map(([r, st, n]) => (
            <tr key={r}>
              <Td>{r}</Td>
              <td style={{
                padding: '9px 12px',
                borderBottom: '1px solid var(--border-subtle)',
                fontSize: 13,
                fontFamily: "'Space Mono', monospace",
                color: st === 'Retrospectively validated' ? 'var(--breakout)' : 'var(--text-muted)',
                verticalAlign: 'top',
              }}>{st}</td>
              <Td>{n}</Td>
            </tr>
          ))}
        </tbody>
      </table>
      <p style={s.p}>
        Rules 1, 2, and 3 are not weaker for being forward-validated only — they are differently validated.
        Production observation across many predictions accumulates calibration data the way historical
        replay cannot.
      </p>

      {/* ── Section 5 ───────────────────────────────────────────── */}
      <h2 style={s.h2}>Brier score & calibration</h2>
      <p style={s.p}>
        For a single prediction with stated probability <Code>p</Code> and actual outcome{' '}
        <Code>o ∈ {'{'} 0, 1 {'}'}</Code>:
      </p>
      <pre style={s.formula}>{`BS = (p - o)²`}</pre>
      <p style={s.p}>Across N resolved predictions:</p>
      <pre style={s.formula}>{`Mean Brier = (1/N) × Σ (pᵢ - oᵢ)²`}</pre>

      <h3 style={s.h3}>Interpretation</h3>
      <table style={s.table}>
        <thead>
          <tr>
            <Th>Score</Th>
            <Th>Meaning</Th>
          </tr>
        </thead>
        <tbody>
          {[
            ['0.00', 'Perfect prediction'],
            ['0.25', 'Coin flip (always predict 50%) — our baseline'],
            ['1.00', 'Worst case (perfectly wrong)'],
          ].map(([score, meaning]) => (
            <tr key={score}>
              <Td mono>{score}</Td>
              <Td>{meaning}</Td>
            </tr>
          ))}
        </tbody>
      </table>
      <p style={s.p}>
        Any model claiming forecasting value must beat Brier = 0.25. Models with Mean Brier &gt; 0.25
        are worse than coin flips.
      </p>
      <p style={s.note}>
        Reference: Brier, G. W. (1950). "Verification of Forecasts Expressed in Terms of Probability."
        Monthly Weather Review, 78(1), 1–3.
      </p>

      {/* ── Section 6 ───────────────────────────────────────────── */}
      <h2 style={s.h2}>Reliability diagram</h2>
      <p style={s.p}>
        Brier score is a single number. The reliability diagram shows whether the model is calibrated
        at all probability levels, not just on average.
      </p>

      <h3 style={s.h3}>Construction</h3>
      <ol style={{ paddingLeft: 20, marginBottom: 16 }}>
        {[
          'Bin all resolved predictions by stated probability into deciles: [0%, 10%), [10%, 20%), …, [90%, 100%]',
          'For each bin: compute mean stated probability, actual hit rate, and 95% Wilson CI on hit rate',
          'Plot (mean stated probability, actual hit rate) per bin',
          'Overlay diagonal reference line y = x',
        ].map((step, i) => (
          <li key={i} style={{ ...s.p, marginBottom: 8 }}>{step}</li>
        ))}
      </ol>

      <h3 style={s.h3}>Interpretation</h3>
      <table style={s.table}>
        <thead>
          <tr>
            <Th>Position</Th>
            <Th>Meaning</Th>
          </tr>
        </thead>
        <tbody>
          {[
            ['On the diagonal', 'Perfectly calibrated at that probability level'],
            ['Above diagonal', 'Under-confident (said 60%, actually hit 75%)'],
            ['Below diagonal', 'Over-confident (said 80%, only hit 55%)'],
          ].map(([pos, meaning]) => (
            <tr key={pos}>
              <Td mono>{pos}</Td>
              <Td>{meaning}</Td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3 style={s.h3}>Wilson 95% CI formula</h3>
      <p style={s.p}>For k hits out of n trials at probability bin p̂ = k/n, z = 1.96 for 95% confidence:</p>
      <pre style={s.formula}>{`center = (p̂ + z²/2n)   / (1 + z²/n)
margin = z × sqrt(p̂(1-p̂)/n + z²/4n²) / (1 + z²/n)`}</pre>
      <p style={s.note}>
        Reference: Wilson, E. B. (1927). "Probable inference, the law of succession, and statistical
        inference." Journal of the American Statistical Association, 22(158), 209–212.
      </p>

      {/* ── Section 7 ───────────────────────────────────────────── */}
      <h2 style={s.h2}>Honest n discipline</h2>
      <p style={s.p}>
        Calibration is meaningless at small sample sizes. We display calibration plots from n=1 onward
        but accompany them with explicit warnings:
      </p>
      <table style={s.table}>
        <thead>
          <tr>
            <Th>n</Th>
            <Th>Warning level</Th>
          </tr>
        </thead>
        <tbody>
          {[
            ['n < 10', 'Pre-calibration. Treat all numbers as directional only.'],
            ['10 ≤ n < 30', 'Below statistical significance threshold. Indicative but not conclusive.'],
            ['30 ≤ n < 100', 'Above minimum threshold. Calibration is meaningful but noisy.'],
            ['n ≥ 100', 'Full confidence in calibration interpretation.'],
          ].map(([n, w]) => (
            <tr key={n}>
              <Td mono>{n}</Td>
              <Td>{w}</Td>
            </tr>
          ))}
        </tbody>
      </table>
      <p style={s.p}>
        We never hide the calibration plot. We never wait until "calibration looks good" to publish.
        The honesty <em>is</em> the methodology.
      </p>

      {/* ── Section 8 ───────────────────────────────────────────── */}
      <h2 style={s.h2}>Methodology version log</h2>
      <p style={s.p}>
        Every time we change driver attribution rules, fundamental signal computation, or scheduler
        logic, we increment methodology version. Each prediction carries the methodology version
        that generated it — so a reader can verify "this prediction was made by methodology version
        v0.1-abc123, which used rule set X."
      </p>
      <table style={s.table}>
        <thead>
          <tr>
            <Th>Version</Th>
            <Th>Date</Th>
            <Th>Changes</Th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <Td mono>v0.1</Td>
            <Td mono>2026-05-19</Td>
            <Td>
              Initial implementation. Rule-based driver attribution (5 rules). Brier score + Wilson CI
              reliability diagram. 7/7 RELEASE attribution accuracy on Gate 2 validation.
            </Td>
          </tr>
        </tbody>
      </table>

      {/* ── Section 9 ───────────────────────────────────────────── */}
      <h2 style={s.h2}>Known limitations</h2>
      <p style={{ ...s.p, marginBottom: 24 }}>Stated openly. This section will grow over time.</p>

      {[
        {
          n: 1,
          title: 'Driver attribution is rule-based, not learned.',
          body: 'No ML model. Confidence numbers come from rule heuristics, not statistical estimation.',
        },
        {
          n: 2,
          title: 'Event registry is human-curated.',
          body: 'We maintain market_events manually for high-impact events. Real-time event detection from social media, news, or content platforms is not yet implemented.',
        },
        {
          n: 3,
          title: 'Fundamental signal assumes event windows have known duration.',
          body: 'We use an asymmetric contamination window per event — 3 days before event_date and expected_window_days + 2 days after (defaulting to a 16-day total span when expected_window_days is unspecified). Cards with overlapping events from multiple sources may have noisy fundamental signals where windows stack.',
        },
        {
          n: 4,
          title: 'Resolution scheduler runs every 4 hours.',
          body: 'A prediction resolving at 14:00 may show as resolved at 14:00, 18:00, 22:00, or later — never earlier. Maximum 4-hour delay.',
        },
        {
          n: 5,
          title: 'Single-source per TCG.',
          body: 'YGO uses CardMarket EUR data converted via a fixed USD rate. Pokemon uses TCGPlayer market price. Cross-source reconciliation is a future improvement.',
        },
        {
          n: 6,
          title: 'No backtesting on historical Public Calls.',
          body: 'Calibration is forward-only from launch. We cannot retroactively claim historical accuracy.',
        },
        {
          n: 7,
          title: 'Sample size grows slowly.',
          body: 'We generate predictions only on cards where our model has confidence the prediction is meaningful — roughly 5–20 predictions per month. Calibration significance takes time.',
        },
        {
          n: 8,
          title: 'Hype premium math is directionally correct but not perfectly apples-to-apples.',
          body: 'The "actual delta" is computed by our standard signal pipeline, which may include event-contaminated prices in its baseline. The "fundamental delta" uses a cleaned baseline. The difference indicates hype direction and approximate magnitude, but precise percentage-point values should be treated as estimates.',
        },
        {
          n: 9,
          title: 'Fundamental ≠ Actual even on uncontaminated cards.',
          body: 'A card with no contamination events anywhere in its price history will not produce fundamental_signal == actual_signal. Hype premium values within roughly ±2 percentage points should be interpreted as "no meaningful hype" rather than "exact equilibrium". Values >5pp indicate genuine divergence.',
        },
        {
          n: 10,
          title: 'MACRO attribution cannot be validated via historical replay.',
          body: 'MACRO attribution depends on set-wide signal breadth at the moment of attribution — and we do not store historical signal snapshots. Today\'s asset_signals state cannot reproduce a past set-wide rally. MACRO is verified forward-only via production observation, not retrospectively.',
        },
        {
          n: 11,
          title: 'Some source URLs are not machine-verifiable.',
          body: 'Five RELEASE events in our market_events registry cite pokemon.com URLs that bot-block automated verification. We classify these as "plausible, source-class trusted" on the basis that (a) The Pokemon Company is the authoritative source for its own release dates and (b) these dates are independently corroborated by Bulbapedia and Pokemon TCG news sites.',
        },
      ].map(({ n, title, body }) => (
        <div key={n} style={{ marginBottom: 20 }}>
          <p style={{ ...s.p, marginBottom: 4 }}>
            <span style={{ fontFamily: "'Space Mono', monospace", fontSize: 12, color: 'var(--text-muted)', marginRight: 10 }}>
              {n}.
            </span>
            <strong style={{ color: 'var(--text-primary)' }}>{title}</strong>
          </p>
          <p style={{ ...s.p, paddingLeft: 22, marginBottom: 0 }}>{body}</p>
        </div>
      ))}

      {/* ── Section 10 ──────────────────────────────────────────── */}
      <h2 style={s.h2}>Sources & references</h2>

      <h3 style={s.h3}>Statistical methods</h3>
      <ul style={{ paddingLeft: 20, marginBottom: 20 }}>
        {[
          'Brier, G. W. (1950). "Verification of Forecasts Expressed in Terms of Probability." Monthly Weather Review, 78(1), 1–3.',
          'Wilson, E. B. (1927). "Probable Inference, the Law of Succession, and Statistical Inference." Journal of the American Statistical Association, 22(158), 209–212.',
        ].map(ref => (
          <li key={ref} style={{ ...s.p, marginBottom: 8 }}>{ref}</li>
        ))}
      </ul>

      <h3 style={s.h3}>Calibration design</h3>
      <ul style={{ paddingLeft: 20, marginBottom: 20 }}>
        {[
          'Polymarket public reliability methodology',
          'Tetlock, P. E. (2005). Expert Political Judgment — long-horizon forecasting calibration.',
        ].map(ref => (
          <li key={ref} style={{ ...s.p, marginBottom: 8 }}>{ref}</li>
        ))}
      </ul>

      <hr style={s.divider} />

      <div style={{ display: 'flex', gap: 24, alignItems: 'center', flexWrap: 'wrap' }}>
        <Link
          to="/calls"
          style={{
            fontSize: 12,
            fontFamily: "'Space Mono', monospace",
            color: 'var(--gold)',
          }}
        >
          ← Public calls
        </Link>
        <span style={s.meta}>
          Methodology version v0.1 · Flashcard Planet
        </span>
      </div>

    </main>
  )
}
