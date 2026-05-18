import { useEffect, useState } from 'react'
import { fetchCallsList, fetchCalibration } from '../../api/calls'
import type { CalibrationResponse, CallsListResponse } from '../../types/calls'
import ReliabilityDiagram from '../../components/calls/ReliabilityDiagram'
import CallsTable from '../../components/calls/CallsTable'
import HonestNWarning from '../../components/calls/HonestNWarning'

export default function CallsPage() {
  const [calibration, setCalibration] = useState<CalibrationResponse | null>(null)
  const [callsList, setCallsList] = useState<CallsListResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([fetchCalibration(), fetchCallsList('all')])
      .then(([cal, list]) => { setCalibration(cal); setCallsList(list) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div style={{ padding: 48, textAlign: 'center', color: 'var(--text-muted)', fontFamily: "'Space Mono', monospace", fontSize: 13 }}>
        Loading...
      </div>
    )
  }
  if (error) {
    return (
      <div style={{ padding: 48, textAlign: 'center', color: 'var(--watch)', fontFamily: "'Space Mono', monospace", fontSize: 13 }}>
        Failed to load: {error}
      </div>
    )
  }

  const cal = calibration!
  const totalResolved = cal.total_resolved

  // Compute overall hit rate from bins
  const weightedHits = cal.reliability_bins.reduce((s, b) => s + b.n * b.hit_rate, 0)
  const hitRateDisplay = totalResolved > 0
    ? `${Math.round((weightedHits / totalResolved) * 100)}%`
    : '—'

  return (
    <main style={{ maxWidth: 860, margin: '0 auto', padding: '48px 24px 80px' }}>

      {/* Headline */}
      <div style={{ marginBottom: 40 }}>
        <h1 style={{
          fontFamily: 'Syne, sans-serif',
          fontWeight: 800,
          fontSize: 'clamp(22px, 4vw, 36px)',
          color: 'var(--text-primary)',
          marginBottom: 12,
          lineHeight: 1.15,
        }}>
          First calibration cohort launches June 14, 2026.
        </h1>
        <p style={{ fontSize: 15, color: 'var(--text-secondary)', lineHeight: 1.7, maxWidth: 560 }}>
          We forecast. We grade ourselves.<br />
          Every prediction below is locked at creation, resolved automatically,
          and aggregated into a public Brier score.
        </p>
        <div style={{ marginTop: 20 }}>
          <HonestNWarning totalResolved={totalResolved} />
        </div>
      </div>

      {/* Metrics row */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
        gap: 12,
        marginBottom: 40,
      }}>
        {[
          { label: 'Total calls', value: cal.total_calls },
          { label: 'Resolved', value: totalResolved },
          { label: 'Hit rate', value: hitRateDisplay },
          { label: 'Brier score', value: cal.brier_score !== null ? cal.brier_score.toFixed(3) : '—' },
          { label: 'Baseline', value: cal.brier_baseline.toFixed(2) },
        ].map(({ label, value }) => (
          <div key={label} style={{
            background: 'var(--bg-surface)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-md)',
            padding: '14px 16px',
          }}>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: "'Space Mono', monospace", marginBottom: 6 }}>
              {label}
            </div>
            <div style={{ fontSize: 22, fontFamily: "'Space Mono', monospace", color: 'var(--text-primary)', fontWeight: 700 }}>
              {value}
            </div>
          </div>
        ))}
      </div>

      {/* Reliability diagram + explanation */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'min(320px, 100%) 1fr',
        gap: 32,
        marginBottom: 48,
        alignItems: 'start',
      }}>
        <div>
          <div style={{ fontSize: 12, fontFamily: "'Space Mono', monospace", color: 'var(--text-muted)', marginBottom: 12 }}>
            Reliability diagram
          </div>
          <ReliabilityDiagram bins={cal.reliability_bins} totalResolved={totalResolved} />
        </div>
        <div style={{ paddingTop: 28 }}>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7, marginBottom: 16 }}>
            Each dot is a decile of stated probabilities. Perfect calibration means
            the dots fall on the diagonal — a 70% call should resolve correctly 70% of the time.
          </p>
          <p style={{ fontSize: 12, fontFamily: "'Space Mono', monospace", color: 'var(--text-muted)' }}>
            Method: {cal.methodology_version}
          </p>
          <a
            href="/methodology"
            style={{
              display: 'inline-block',
              marginTop: 12,
              fontSize: 12,
              fontFamily: "'Space Mono', monospace",
              color: 'var(--gold)',
            }}
          >
            Methodology →
          </a>
        </div>
      </div>

      {/* Calls table */}
      <div>
        <div style={{ fontSize: 12, fontFamily: "'Space Mono', monospace", color: 'var(--text-muted)', marginBottom: 12 }}>
          All calls
        </div>
        <div style={{
          background: 'var(--bg-surface)',
          border: '1px solid var(--border-subtle)',
          borderRadius: 'var(--radius-lg)',
          overflow: 'hidden',
        }}>
          <CallsTable predictions={callsList?.predictions ?? []} />
        </div>
      </div>
    </main>
  )
}
