import { useState } from 'react'
import type { PublicPrediction, ResolutionStatus } from '../../types/calls'

interface Props {
  predictions: PublicPrediction[]
}

type SortKey = 'resolution_date' | 'stated_probability' | 'resolution_status'

const STATUS_ORDER: Record<ResolutionStatus, number> = {
  HIT: 0, MISS: 1, PENDING: 2, AMBIGUOUS: 3, VOIDED: 4,
}

const STATUS_COLOR: Record<ResolutionStatus, string> = {
  HIT: 'var(--breakout)',
  MISS: 'var(--watch)',
  PENDING: 'var(--text-muted)',
  AMBIGUOUS: 'var(--idle)',
  VOIDED: 'var(--idle)',
}

function fmtDate(iso: string | null): string {
  if (!iso) return '—'
  return iso.slice(0, 10)
}

function fmtProb(p: number): string {
  return `${Math.round(p * 100)}%`
}

export default function CallsTable({ predictions }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>('resolution_date')
  const [sortAsc, setSortAsc] = useState(true)

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortAsc(a => !a)
    else { setSortKey(key); setSortAsc(true) }
  }

  const sorted = [...predictions].sort((a, b) => {
    let cmp = 0
    if (sortKey === 'resolution_date') {
      cmp = (a.resolution_date ?? '').localeCompare(b.resolution_date ?? '')
    } else if (sortKey === 'stated_probability') {
      cmp = a.stated_probability - b.stated_probability
    } else if (sortKey === 'resolution_status') {
      cmp = (STATUS_ORDER[a.resolution_status] ?? 9) - (STATUS_ORDER[b.resolution_status] ?? 9)
    }
    return sortAsc ? cmp : -cmp
  })

  if (predictions.length === 0) {
    return (
      <div style={{
        padding: '32px 0',
        textAlign: 'center',
        color: 'var(--text-muted)',
        fontFamily: "'Space Mono', monospace",
        fontSize: 13,
      }}>
        First cohort drops June 14.
      </div>
    )
  }

  const SortBtn = ({ k, label }: { k: SortKey; label: string }) => (
    <button
      onClick={() => toggleSort(k)}
      style={{
        background: 'none', border: 'none', color: 'var(--text-secondary)',
        fontFamily: "'Space Mono', monospace", fontSize: 11, cursor: 'pointer',
        padding: 0,
      }}
    >
      {label}{sortKey === k ? (sortAsc ? ' ↑' : ' ↓') : ''}
    </button>
  )

  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead>
          <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
            <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 400 }}>Call</th>
            <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 400 }}>
              <SortBtn k="stated_probability" label="Probability" />
            </th>
            <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 400 }}>
              <SortBtn k="resolution_date" label="Resolves" />
            </th>
            <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 400 }}>
              <SortBtn k="resolution_status" label="Result" />
            </th>
          </tr>
        </thead>
        <tbody>
          {sorted.map(p => (
            <tr key={p.id} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
              <td style={{ padding: '10px 12px', color: 'var(--text-primary)', maxWidth: 320 }}>
                {p.prediction_text}
              </td>
              <td style={{ padding: '10px 12px', fontFamily: "'Space Mono', monospace", color: 'var(--text-secondary)' }}>
                {fmtProb(p.stated_probability)}
              </td>
              <td style={{ padding: '10px 12px', fontFamily: "'Space Mono', monospace", color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
                {fmtDate(p.resolution_date)}
              </td>
              <td style={{ padding: '10px 12px', fontFamily: "'Space Mono', monospace", color: STATUS_COLOR[p.resolution_status] ?? 'var(--text-muted)', fontWeight: 700, fontSize: 11 }}>
                {p.resolution_status}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
