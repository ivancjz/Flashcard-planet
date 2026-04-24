import { useEffect, useState } from 'react'
import { fetchSetOptions, fetchRarityOptions } from '../api/api'
import type { SetOption, RarityOption } from '../types/api'

export interface FilterState {
  selectedSets: string[]
  selectedRarities: string[]
  priceMin: number | null
  priceMax: number | null
}

interface Props extends FilterState {
  open: boolean
  game: string
  onClose: () => void
  onChange: (state: FilterState) => void
}

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '8px 10px',
  background: 'var(--bg-base)',
  border: '1px solid var(--border-subtle)',
  borderRadius: 'var(--radius-sm)',
  color: 'var(--text-primary)',
  fontFamily: 'var(--font-mono)',
  fontSize: 13,
  outline: 'none',
  boxSizing: 'border-box',
}

const sectionHead: React.CSSProperties = {
  fontFamily: 'var(--font-display)',
  fontWeight: 700,
  fontSize: 13,
  color: 'var(--text-primary)',
  marginBottom: 10,
  paddingBottom: 8,
  borderBottom: '1px solid var(--border-subtle)',
}

export default function FilterDrawer({ open, game, onClose, onChange, selectedSets, selectedRarities, priceMin, priceMax }: Props) {
  const [sets, setSets] = useState<SetOption[]>([])
  const [rarities, setRarities] = useState<RarityOption[]>([])
  const [loadingOpts, setLoadingOpts] = useState(false)

  useEffect(() => {
    if (!open) return
    setLoadingOpts(true)
    Promise.all([fetchSetOptions(game), fetchRarityOptions(game)])
      .then(([s, r]) => { setSets(s); setRarities(r) })
      .finally(() => setLoadingOpts(false))
  }, [open, game])

  if (!open) return null

  function toggleSet(id: string) {
    const next = selectedSets.includes(id)
      ? selectedSets.filter(s => s !== id)
      : [...selectedSets, id]
    onChange({ selectedSets: next, selectedRarities, priceMin, priceMax })
  }

  function toggleRarity(val: string) {
    const next = selectedRarities.includes(val)
      ? selectedRarities.filter(r => r !== val)
      : [...selectedRarities, val]
    onChange({ selectedSets, selectedRarities: next, priceMin, priceMax })
  }

  function clearAll() {
    onChange({ selectedSets: [], selectedRarities: [], priceMin: null, priceMax: null })
  }

  const activeCount =
    (selectedSets.length > 0 ? 1 : 0) +
    (selectedRarities.length > 0 ? 1 : 0) +
    (priceMin != null || priceMax != null ? 1 : 0)

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 200 }}
      />

      {/* Drawer panel */}
      <div style={{
        position: 'fixed', top: 0, right: 0, bottom: 0,
        width: 'clamp(280px, 100vw, 380px)',
        background: 'var(--bg-elevated)',
        borderLeft: '1px solid var(--border-subtle)',
        zIndex: 201,
        display: 'flex', flexDirection: 'column',
        overflowY: 'hidden',
      }}>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '20px 20px 14px' }}>
          <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 16 }}>Filters</span>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 22, lineHeight: 1 }}>×</button>
        </div>

        {/* Scrollable content */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '0 20px' }}>
          {loadingOpts ? (
            <div style={{ color: 'var(--text-muted)', fontSize: 13, padding: '20px 0' }}>Loading options…</div>
          ) : (
            <>
              {/* Set section */}
              <div style={{ marginBottom: 24 }}>
                <div style={sectionHead}>Set</div>
                {sets.length === 0 ? (
                  <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>No sets available</div>
                ) : (
                  <div style={{ maxHeight: 220, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 2 }}>
                    {sets.map(set => (
                      <label key={set.id} style={{ display: 'flex', alignItems: 'center', padding: '6px 4px', cursor: 'pointer', borderRadius: 4, gap: 8 }}
                        onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-base)')}
                        onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>
                        <input
                          type="checkbox"
                          checked={selectedSets.includes(set.id)}
                          onChange={() => toggleSet(set.id)}
                          style={{ accentColor: 'var(--gold)', flexShrink: 0 }}
                        />
                        <span style={{ flex: 1, fontSize: 13, color: 'var(--text-primary)' }}>{set.name}</span>
                        <span style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>{set.count}</span>
                      </label>
                    ))}
                  </div>
                )}
              </div>

              {/* Rarity section */}
              <div style={{ marginBottom: 24 }}>
                <div style={sectionHead}>Rarity</div>
                {rarities.length === 0 ? (
                  <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>No rarities available</div>
                ) : (
                  <div style={{ maxHeight: 200, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 2 }}>
                    {rarities.map(r => (
                      <label key={r.value} style={{ display: 'flex', alignItems: 'center', padding: '6px 4px', cursor: 'pointer', borderRadius: 4, gap: 8 }}
                        onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-base)')}
                        onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>
                        <input
                          type="checkbox"
                          checked={selectedRarities.includes(r.value)}
                          onChange={() => toggleRarity(r.value)}
                          style={{ accentColor: 'var(--gold)', flexShrink: 0 }}
                        />
                        <span style={{ flex: 1, fontSize: 13, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.value}</span>
                        <span style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>{r.count}</span>
                      </label>
                    ))}
                  </div>
                )}
              </div>

              {/* Price range section */}
              <div style={{ marginBottom: 24 }}>
                <div style={sectionHead}>TCG Price (USD)</div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <input
                    type="number"
                    placeholder="Min"
                    min={0}
                    value={priceMin ?? ''}
                    onChange={e => onChange({ selectedSets, selectedRarities, priceMin: e.target.value ? Number(e.target.value) : null, priceMax })}
                    style={{ ...inputStyle, width: '50%' }}
                  />
                  <span style={{ color: 'var(--text-muted)', flexShrink: 0 }}>—</span>
                  <input
                    type="number"
                    placeholder="Max"
                    min={0}
                    value={priceMax ?? ''}
                    onChange={e => onChange({ selectedSets, selectedRarities, priceMin, priceMax: e.target.value ? Number(e.target.value) : null })}
                    style={{ ...inputStyle, width: '50%' }}
                  />
                </div>
                {priceMin != null && priceMax != null && priceMin > priceMax && (
                  <div style={{ color: '#ef4444', fontSize: 11, marginTop: 6 }}>Min must be ≤ Max</div>
                )}
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div style={{ padding: 20, borderTop: '1px solid var(--border-subtle)', display: 'flex', gap: 10 }}>
          <button
            onClick={clearAll}
            className="btn btn-ghost"
            style={{ flex: 1, justifyContent: 'center' }}
            disabled={activeCount === 0}
          >
            Clear all
          </button>
          <button onClick={onClose} className="btn btn-primary" style={{ flex: 1, justifyContent: 'center' }}>
            Apply
          </button>
        </div>
      </div>
    </>
  )
}
