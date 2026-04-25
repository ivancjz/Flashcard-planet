import { useState, useEffect, useRef } from 'react'
import { fetchCards } from '../api/api'
import SignalBadge from './SignalBadge'
import { signalToMeta } from '../lib/utils'
import type { CardSummary } from '../types/api'

interface Props {
  open: boolean
  onClose: () => void
  onSelect: (card: CardSummary) => void
  excludeIds: string[]   // already in comparison — disable these in results
  game?: string
}

export default function CardPickerModal({ open, onClose, onSelect, excludeIds, game = 'pokemon' }: Props) {
  const [query, setQuery] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const [results, setResults] = useState<CardSummary[]>([])
  const [loading, setLoading] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  // Focus input when modal opens; reset on close
  useEffect(() => {
    if (open) {
      setQuery('')
      setDebouncedQuery('')
      setResults([])
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }, [open])

  // Debounce search
  useEffect(() => {
    const t = setTimeout(() => setDebouncedQuery(query), 300)
    return () => clearTimeout(t)
  }, [query])

  // Fetch on debounced query change
  useEffect(() => {
    if (!debouncedQuery.trim()) {
      setResults([])
      return
    }
    setLoading(true)
    fetchCards({ game, search: debouncedQuery, sort: 'change', limit: 8 })
      .then(r => { setResults(r.cards); setLoading(false) })
      .catch(() => setLoading(false))
  }, [debouncedQuery, game])

  if (!open) return null

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        style={{
          position: 'fixed', inset: 0, zIndex: 100,
          background: 'rgba(12,12,16,0.75)',
          backdropFilter: 'blur(2px)',
        }}
      />

      {/* Modal */}
      <div style={{
        position: 'fixed', top: '15%', left: '50%', transform: 'translateX(-50%)',
        zIndex: 101, width: 'min(480px, 94vw)',
        background: 'var(--bg-elevated)',
        border: '1px solid var(--border-default)',
        borderRadius: 'var(--radius-md)',
        boxShadow: '0 24px 64px rgba(0,0,0,0.6)',
        overflow: 'hidden',
      }}>
        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '14px 16px',
          borderBottom: '1px solid var(--border-subtle)',
        }}>
          <span style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 14 }}>
            Add a card to compare
          </span>
          <button
            onClick={onClose}
            aria-label="Close"
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', fontSize: 20, lineHeight: 1 }}
          >
            ×
          </button>
        </div>

        {/* Search input */}
        <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border-subtle)' }}>
          <input
            ref={inputRef}
            type="search"
            placeholder="Search cards by name…"
            value={query}
            onChange={e => setQuery(e.target.value)}
            style={{
              width: '100%', boxSizing: 'border-box',
              padding: '9px 12px',
              background: 'var(--bg-surface)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-sm)',
              color: 'var(--text-primary)',
              fontFamily: 'var(--font-body)',
              fontSize: 14,
              outline: 'none',
            }}
            onFocus={e => (e.target.style.borderColor = 'var(--gold)')}
            onBlur={e => (e.target.style.borderColor = 'var(--border-subtle)')}
          />
        </div>

        {/* Results */}
        <div style={{ maxHeight: 320, overflowY: 'auto' }}>
          {!query.trim() && (
            <div style={{ padding: '24px 16px', textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>
              Type a card name to search
            </div>
          )}

          {query.trim() && loading && (
            <div style={{ padding: '24px 16px', textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>
              Searching…
            </div>
          )}

          {query.trim() && !loading && results.length === 0 && (
            <div style={{ padding: '24px 16px', textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>
              No cards match "{query}"
            </div>
          )}

          {results.map(card => {
            const already = excludeIds.includes(card.asset_id)
            const meta = signalToMeta(card.signal)
            return (
              <button
                key={card.asset_id}
                onClick={() => { if (!already) { onSelect(card); onClose() } }}
                disabled={already}
                style={{
                  width: '100%', textAlign: 'left',
                  display: 'flex', alignItems: 'center', gap: 12,
                  padding: '10px 16px',
                  background: 'none', border: 'none',
                  borderBottom: '1px solid var(--border-subtle)',
                  cursor: already ? 'default' : 'pointer',
                  opacity: already ? 0.4 : 1,
                  transition: 'background 0.1s',
                }}
                onMouseEnter={e => { if (!already) (e.currentTarget as HTMLButtonElement).style.background = 'var(--bg-surface)' }}
                onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = 'none' }}
              >
                {/* Color dot matching signal */}
                <div style={{ width: 8, height: 8, borderRadius: '50%', background: meta.color, flexShrink: 0 }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{
                    fontFamily: 'var(--font-display)', fontSize: 13, fontWeight: 600,
                    color: 'var(--text-primary)',
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }}>
                    {card.name}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{card.set_name}</div>
                </div>
                <div style={{ flexShrink: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <SignalBadge signal={card.signal} />
                  {already && <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>added</span>}
                </div>
              </button>
            )
          })}
        </div>
      </div>
    </>
  )
}
