import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import NavBar from '../components/NavBar'
import TickerBar from '../components/TickerBar'
import GameSwitcher from '../components/GameSwitcher'
import ProGate from '../components/ProGate'
import FilterDrawer from '../components/FilterDrawer'
import CardGrid from '../components/CardGrid'
import type { FilterState } from '../components/FilterDrawer'
import { fetchStats, fetchCards, fetchTicker, fetchSetOptions, exportCardsCsv } from '../api/api'
import type { Signal, CardSummary, MarketStats, TickerItem } from '../types/api'

type SortKey = 'change' | 'price' | 'volume' | 'recent'
const FILTERS: Array<{ value: Signal | 'ALL'; label: string }> = [
  { value: 'ALL', label: 'All' },
  { value: 'BREAKOUT', label: '▲ Breakout' },
  { value: 'MOVE', label: '◆ Move' },
  { value: 'WATCH', label: '◆ Watch' },
  { value: 'IDLE', label: '— Idle' },
]

export default function DashboardPage() {
  const nav = useNavigate()
  const [stats, setStats] = useState<MarketStats | null>(null)
  const [ticker, setTicker] = useState<TickerItem[]>([])
  const [cards, setCards] = useState<CardSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [signal, setSignal] = useState<Signal | 'ALL'>('ALL')
  const [sort, setSort] = useState<SortKey>('change')
  const [activeGame, setActiveGame] = useState('pokemon')
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const searchRef = useRef<HTMLInputElement>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [selectedSets, setSelectedSets] = useState<string[]>([])
  const [selectedRarities, setSelectedRarities] = useState<string[]>([])
  const [priceMin, setPriceMin] = useState<number | null>(null)
  const [priceMax, setPriceMax] = useState<number | null>(null)
  const [setNameMap, setSetNameMap] = useState<Record<string, string>>({})

  useEffect(() => { fetchStats().then(setStats); fetchTicker().then(setTicker) }, [])

  // Load set name map when drawer is first opened (for chip labels)
  useEffect(() => {
    if (!drawerOpen) return
    fetchSetOptions(activeGame).then(sets => {
      const map: Record<string, string> = {}
      sets.forEach(s => { map[s.id] = s.name })
      setSetNameMap(map)
    })
  }, [drawerOpen, activeGame])

  // Debounce search: wait 300ms after last keystroke before hitting API
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 300)
    return () => clearTimeout(t)
  }, [search])

  const LIVE_GAMES = ['pokemon', 'yugioh']

  const activeFilterCount =
    (selectedSets.length > 0 ? 1 : 0) +
    (selectedRarities.length > 0 ? 1 : 0) +
    (priceMin != null || priceMax != null ? 1 : 0)

  useEffect(() => {
    if (!LIVE_GAMES.includes(activeGame)) return
    setLoading(true)
    fetchCards({
      game: activeGame,
      signal,
      sort,
      search: debouncedSearch,
      set_id: selectedSets.length ? selectedSets : undefined,
      rarity: selectedRarities.length ? selectedRarities : undefined,
      price_min: priceMin ?? undefined,
      price_max: priceMax ?? undefined,
    })
      .then(r => { setCards(r.cards); setLoading(false) })
      .catch(() => setLoading(false))
  }, [signal, sort, activeGame, debouncedSearch, selectedSets, selectedRarities, priceMin, priceMax])

  function handleGameChange(gameId: string) {
    setActiveGame(gameId)
    setSearch('')
    setDebouncedSearch('')
    setSelectedSets([])
    setSelectedRarities([])
    setPriceMin(null)
    setPriceMax(null)
  }

  function handleFilterChange(state: FilterState) {
    setSelectedSets(state.selectedSets)
    setSelectedRarities(state.selectedRarities)
    setPriceMin(state.priceMin)
    setPriceMax(state.priceMax)
  }

  const emptyState = debouncedSearch ? (
    <div style={{ textAlign: 'center', padding: '48px 0', color: 'var(--text-muted)' }}>
      <div style={{ fontSize: 32, marginBottom: 12 }}>🔍</div>
      <div style={{ fontFamily: 'var(--font-display)', fontSize: 16, marginBottom: 8, color: 'var(--text-secondary)' }}>
        No cards match "{debouncedSearch}"
      </div>
      <div style={{ fontSize: 13 }}>Try a different name, or clear the search to see all cards.</div>
    </div>
  ) : activeFilterCount > 0 ? (
    <div style={{ textAlign: 'center', padding: '48px 0', color: 'var(--text-muted)' }}>
      <div style={{ fontSize: 32, marginBottom: 12 }}>🔎</div>
      <div style={{ fontFamily: 'var(--font-display)', fontSize: 16, marginBottom: 8, color: 'var(--text-secondary)' }}>
        No cards match these filters
      </div>
      <button className="btn btn-ghost btn-sm" onClick={() => { setSelectedSets([]); setSelectedRarities([]); setPriceMin(null); setPriceMax(null) }}>
        Clear filters
      </button>
    </div>
  ) : (
    <div style={{ textAlign: 'center', padding: 80, color: 'var(--text-muted)' }}>No cards match this filter</div>
  )

  return (
    <div>
      <NavBar />
      <GameSwitcher activeGame={activeGame} onGameChange={handleGameChange} />
      <TickerBar items={ticker} />
      <div className="page-content">
        {/* Stat tiles */}
        {stats && (
          <div className="stats-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: 12, marginBottom: 28 }}>
            {([
              { label: 'Total assets', value: stats.total_assets },
              { label: 'Breakout', value: stats.signal_counts.BREAKOUT, color: 'var(--breakout)' },
              { label: 'Move', value: stats.signal_counts.MOVE, color: 'var(--move)' },
              { label: 'Watch', value: stats.signal_counts.WATCH, color: 'var(--watch)' },
            ] as const).map(tile => (
              <div key={tile.label} className="surface" style={{ padding: '16px 20px' }}>
                <div className="stat-number" style={{ fontFamily: 'var(--font-mono)', fontSize: 26, fontWeight: 700, color: ('color' in tile ? tile.color : 'var(--text-primary)') as string }}>
                  {tile.value}
                </div>
                <div className="stat-label" style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>{tile.label}</div>
              </div>
            ))}
          </div>
        )}

        {/* Search + Filters button */}
        <div style={{ display: 'flex', gap: 10, marginBottom: activeFilterCount > 0 ? 10 : 16, alignItems: 'stretch' }}>
        <div style={{ position: 'relative', flex: 1 }}>
          <svg
            width={16} height={16} viewBox="0 0 24 24"
            style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)', pointerEvents: 'none' }}
            fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
          >
            <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            ref={searchRef}
            type="search"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search cards by name…"
            style={{
              width: '100%', boxSizing: 'border-box',
              padding: '9px 36px 9px 38px',
              background: 'var(--bg-surface)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-sm)',
              color: 'var(--text-primary)',
              fontFamily: 'var(--font-body)',
              fontSize: 14,
              outline: 'none',
              transition: 'border-color 0.15s',
            }}
            onFocus={e => (e.target.style.borderColor = 'var(--gold)')}
            onBlur={e => (e.target.style.borderColor = 'var(--border-subtle)')}
          />
          {search && (
            <button
              onClick={() => { setSearch(''); searchRef.current?.focus() }}
              aria-label="Clear search"
              style={{ position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', fontSize: 18, lineHeight: 1, padding: '0 2px' }}
            >×</button>
          )}
        </div>

        {/* Filters button */}
        <button
          onClick={() => setDrawerOpen(true)}
          className="btn btn-ghost"
          style={{ position: 'relative', whiteSpace: 'nowrap', flexShrink: 0 }}
        >
          Filters
          {activeFilterCount > 0 && (
            <span style={{ marginLeft: 6, background: 'var(--gold)', color: '#0c0c10', fontSize: 10, fontWeight: 700, padding: '1px 6px', borderRadius: 10 }}>
              {activeFilterCount}
            </span>
          )}
        </button>
        <button
          className="btn btn-ghost"
          onClick={() => exportCardsCsv({
            game: activeGame,
            signal,
            sort,
            search: debouncedSearch || undefined,
            set_id: selectedSets.length ? selectedSets : undefined,
            rarity: selectedRarities.length ? selectedRarities : undefined,
            price_min: priceMin ?? undefined,
            price_max: priceMax ?? undefined,
          })}
          title="Export current view as CSV"
          style={{ whiteSpace: 'nowrap', flexShrink: 0 }}
        >
          ↓ Export
        </button>
        </div>

        {/* Active filter chips */}
        {activeFilterCount > 0 && (
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 16 }}>
            {selectedSets.map(id => (
              <Chip key={id} label={setNameMap[id] ?? id} onRemove={() => setSelectedSets(selectedSets.filter(s => s !== id))} />
            ))}
            {selectedRarities.map(r => (
              <Chip key={r} label={r} onRemove={() => setSelectedRarities(selectedRarities.filter(x => x !== r))} />
            ))}
            {(priceMin != null || priceMax != null) && (
              <Chip
                label={`$${priceMin ?? 0}–${priceMax != null ? '$' + priceMax : '∞'}`}
                onRemove={() => { setPriceMin(null); setPriceMax(null) }}
              />
            )}
          </div>
        )}

        {/* Filters + sort */}
        <div className="filter-sort-bar">
          <div className="filter-row">
            {FILTERS.map(f => (
              <button
                key={f.value}
                className="btn btn-ghost btn-sm"
                onClick={() => setSignal(f.value)}
                style={signal === f.value ? { background: 'var(--bg-elevated)', color: 'var(--text-primary)', borderColor: 'var(--border-strong)' } : {}}
              >
                {f.label}
              </button>
            ))}
          </div>
          <div className="sort-row">
            <button className="btn btn-ghost btn-sm" onClick={() => setSort('change')}
              style={sort === 'change' ? { background: 'var(--bg-elevated)', color: 'var(--gold)', borderColor: 'var(--gold-dim)' } : {}}>
              Change
            </button>
            <button className="btn btn-ghost btn-sm" onClick={() => setSort('price')}
              style={sort === 'price' ? { background: 'var(--bg-elevated)', color: 'var(--gold)', borderColor: 'var(--gold-dim)' } : {}}>
              Price
            </button>
            <ProGate feature="Sort by Volume" reason="Advanced sorting on Pro plan">
              <button className="btn btn-ghost btn-sm" onClick={() => setSort('volume')}
                style={sort === 'volume' ? { background: 'var(--bg-elevated)', color: 'var(--gold)', borderColor: 'var(--gold-dim)' } : {}}>
                Volume
              </button>
            </ProGate>
            <ProGate feature="Sort by Recent" reason="Advanced sorting on Pro plan">
              <button className="btn btn-ghost btn-sm" onClick={() => setSort('recent')}
                style={sort === 'recent' ? { background: 'var(--bg-elevated)', color: 'var(--gold)', borderColor: 'var(--gold-dim)' } : {}}>
                Recent
              </button>
            </ProGate>
          </div>
        </div>

        {/* Card grid */}
        {!LIVE_GAMES.includes(activeGame) ? (
          <div style={{ textAlign: 'center', padding: '64px 0', color: 'var(--text-muted)' }}>
            <div style={{ fontSize: 48, marginBottom: 16 }}>🧙</div>
            <div style={{ fontFamily: 'var(--font-display)', fontSize: 18, color: 'var(--text-primary)', marginBottom: 8 }}>
              {activeGame} support is coming
            </div>
            <div style={{ fontSize: 14 }}>Signal analysis for this game is in development.</div>
          </div>
        ) : (
          <CardGrid
            cards={cards}
            loading={loading}
            onCardClick={id => nav(`/market/${id}`)}
            emptyState={emptyState}
          />
        )}
      </div>

      <FilterDrawer
        open={drawerOpen}
        game={activeGame}
        onClose={() => setDrawerOpen(false)}
        selectedSets={selectedSets}
        selectedRarities={selectedRarities}
        priceMin={priceMin}
        priceMax={priceMax}
        onChange={handleFilterChange}
      />
    </div>
  )
}

function Chip({ label, onRemove }: { label: string; onRemove: () => void }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      background: 'var(--gold-glow)', color: 'var(--gold)',
      border: '1px solid rgba(240,180,41,0.3)',
      borderRadius: 12, padding: '2px 8px 2px 10px', fontSize: 12,
      maxWidth: 220, overflow: 'hidden',
    }}>
      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{label}</span>
      <button onClick={onRemove} style={{ background: 'none', border: 'none', color: 'var(--gold)', cursor: 'pointer', padding: 0, fontSize: 16, lineHeight: 1, flexShrink: 0 }}>×</button>
    </span>
  )
}
