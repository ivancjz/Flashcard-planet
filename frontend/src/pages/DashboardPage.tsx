import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import NavBar from '../components/NavBar'
import TickerBar from '../components/TickerBar'
import GameSwitcher from '../components/GameSwitcher'
import FilterDrawer from '../components/FilterDrawer'
import CardGrid from '../components/CardGrid'
import ProGate from '../components/ProGate'
import type { FilterState } from '../components/FilterDrawer'
import { fetchStats, fetchCards, fetchTicker, fetchSetOptions, fetchMarketOverview, fetchLatestDailyMarketReport } from '../api/api'
import type { Signal, CardSummary, MarketStats, TickerItem, MarketOverview, MarketNumber, DailyMarketReport } from '../types/api'

type SortKey = 'change' | 'price' | 'volume' | 'recent' | 'signal'
type SignalFilter = Signal | 'ALL' | 'INVESTMENT'
const FILTERS: Array<{ value: SignalFilter; label: string }> = [
  { value: 'ALL', label: 'All' },
  { value: 'INVESTMENT', label: '▲ Signals' },
  { value: 'BREAKOUT', label: '▲ Breakout' },
  { value: 'MOVE', label: '◆ Move' },
  { value: 'WATCH', label: '◆ Watch' },
  { value: 'IDLE', label: '— Idle' },
]

export default function DashboardPage() {
  const nav = useNavigate()
  const [stats, setStats] = useState<MarketStats | null>(null)
  const [dailyReport, setDailyReport] = useState<DailyMarketReport | null | undefined>(undefined)
  const [dailyReportUnavailable, setDailyReportUnavailable] = useState(false)
  const [marketOverview, setMarketOverview] = useState<MarketOverview | null>(null)
  const [marketOverviewUnavailable, setMarketOverviewUnavailable] = useState(false)
  const [ticker, setTicker] = useState<TickerItem[]>([])
  const [cards, setCards] = useState<CardSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [signal, setSignal] = useState<SignalFilter>('ALL')
  const [sort, setSort] = useState<SortKey>('signal')
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

  useEffect(() => {
    fetchStats().then(setStats)
    fetchTicker().then(setTicker)
    fetchLatestDailyMarketReport()
      .then(data => {
        setDailyReport(data)
        setDailyReportUnavailable(false)
      })
      .catch(() => {
        setDailyReport(null)
        setDailyReportUnavailable(true)
      })
    fetchMarketOverview()
      .then(data => {
        setMarketOverview(data)
        setMarketOverviewUnavailable(false)
      })
      .catch(() => setMarketOverviewUnavailable(true))
  }, [])

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
        <DailyMarketReportPanel report={dailyReport} unavailable={dailyReportUnavailable} />
        <MarketOverviewPanel overview={marketOverview} unavailable={marketOverviewUnavailable} />

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
        <ProGate feature="CSV export" reason="Export signal data on Pro plan">
          <a
            href={`/api/v1/web/cards/export.csv?game=${activeGame}`}
            className="btn btn-ghost btn-sm"
            style={{ textDecoration: 'none' }}
            download
          >
            Export CSV
          </a>
        </ProGate>
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
            <button className="btn btn-ghost btn-sm" onClick={() => setSort('signal')}
              style={sort === 'signal' ? { background: 'var(--bg-elevated)', color: 'var(--gold)', borderColor: 'var(--gold-dim)' } : {}}>
              Signal
            </button>
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

function formatMarketPercent(value: MarketNumber | null | undefined): string {
  const numericValue = Number(value)
  if (!Number.isFinite(numericValue)) return 'N/A'
  return `${numericValue >= 0 ? '+' : ''}${numericValue.toFixed(2)}%`
}

function formatMarketLabel(value: string): string {
  return value
    .split('_')
    .filter(Boolean)
    .map(part => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

function formatReportDate(value: string): string {
  const parsed = new Date(`${value}T00:00:00Z`)
  if (Number.isNaN(parsed.getTime())) return value
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(parsed)
}

function DailyMarketReportPanel({
  report,
  unavailable,
}: {
  report: DailyMarketReport | null | undefined
  unavailable: boolean
}) {
  if (unavailable) {
    return (
      <section aria-label="Flashcard Planet Daily" aria-live="polite" aria-atomic="true" className="surface" style={{ padding: 20, minHeight: 96, marginBottom: 24, borderLeft: '3px solid var(--down)' }}>
        <div style={{ fontFamily: 'var(--font-display)', fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>
          Flashcard Planet Daily
        </div>
        <div style={{ marginTop: 8, color: 'var(--text-muted)', fontSize: 13 }}>Daily report unavailable.</div>
      </section>
    )
  }

  if (report === undefined) {
    return (
      <section aria-label="Flashcard Planet Daily" aria-live="polite" aria-atomic="true" aria-busy="true" className="surface" style={{ padding: 20, minHeight: 96, marginBottom: 24, borderLeft: '3px solid var(--border-strong)' }}>
        <div style={{ fontFamily: 'var(--font-display)', fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>
          Flashcard Planet Daily
        </div>
        <div style={{ marginTop: 8, color: 'var(--text-muted)', fontSize: 13 }}>Loading the latest market brief...</div>
      </section>
    )
  }

  if (report === null) {
    return (
      <section aria-label="Flashcard Planet Daily" aria-live="polite" aria-atomic="true" className="surface" style={{ padding: 20, minHeight: 96, marginBottom: 24, borderLeft: '3px solid var(--border-strong)' }}>
        <div style={{ fontFamily: 'var(--font-display)', fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>
          Flashcard Planet Daily
        </div>
        <div style={{ marginTop: 8, color: 'var(--text-muted)', fontSize: 13 }}>Today's report has not been generated yet.</div>
      </section>
    )
  }

  const sentiment = formatMarketLabel(report.market_sentiment)
  const confidence = `${formatMarketLabel(report.confidence_label)} confidence`
  const sentimentColor = report.market_sentiment === 'bullish'
    ? 'var(--up)'
    : report.market_sentiment === 'bearish'
      ? 'var(--down)'
      : 'var(--text-secondary)'

  return (
    <section
      aria-label="Flashcard Planet Daily"
      aria-live="polite"
      aria-atomic="true"
      className="surface-emphasis"
      style={{ padding: 20, marginBottom: 24, borderLeft: '3px solid var(--gold)' }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'flex-start', flexWrap: 'wrap' }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 11, color: 'var(--gold)', textTransform: 'uppercase', letterSpacing: 0, marginBottom: 6 }}>
            Flashcard Planet Daily
          </div>
          <h2 style={{ margin: 0, fontFamily: 'var(--font-display)', fontSize: 20, lineHeight: 1.3, color: 'var(--text-primary)', overflowWrap: 'anywhere' }}>
            {report.title}
          </h2>
        </div>
        <time dateTime={report.report_date} style={{ flexShrink: 0, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: 12, paddingTop: 2 }}>
          {formatReportDate(report.report_date)}
        </time>
      </div>

      <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', marginTop: 14, fontFamily: 'var(--font-mono)', fontSize: 12 }}>
        <span style={{ color: sentimentColor, fontWeight: 700 }}>{sentiment}</span>
        <span aria-hidden="true" style={{ color: 'var(--border-strong)' }}>|</span>
        <span style={{ color: 'var(--text-muted)' }}>{confidence}</span>
      </div>

      <p style={{ margin: '16px 0 0', maxWidth: 880, color: 'var(--text-secondary)', fontSize: 14, lineHeight: 1.65 }}>
        {report.summary}
      </p>

      {report.evidence.length > 0 && (
        <ul style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(220px, 100%), 1fr))', gap: '8px 20px', margin: '16px 0 0', padding: '14px 0 0 18px', borderTop: '1px solid var(--border-subtle)', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: 11, lineHeight: 1.5 }}>
          {report.evidence.slice(0, 3).map(item => (
            <li key={item} style={{ paddingLeft: 2, overflowWrap: 'anywhere' }}>{item}</li>
          ))}
        </ul>
      )}
    </section>
  )
}

function MarketOverviewPanel({ overview, unavailable }: { overview: MarketOverview | null; unavailable: boolean }) {
  if (unavailable) {
    return (
      <section aria-label="Market Overview" className="surface" style={{ padding: 20, marginBottom: 24 }}>
        <div style={{ fontFamily: 'var(--font-display)', fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>
          Market Overview
        </div>
        <div style={{ marginTop: 8, color: 'var(--text-muted)', fontSize: 13 }}>Market overview unavailable.</div>
      </section>
    )
  }

  if (!overview) return null

  const strongestIndex = overview.indexes[0]
  const topMover = overview.top_movers[0]
  const signalCount = overview.signal_summary.reduce((total, row) => total + row.count, 0)
  const sentiment = formatMarketLabel(overview.market_sentiment)
  const confidence = `${formatMarketLabel(overview.confidence_label)} confidence`

  return (
    <section aria-label="Market Overview" className="surface" style={{ padding: 20, marginBottom: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'flex-start', flexWrap: 'wrap', marginBottom: 18 }}>
        <div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 0, marginBottom: 6 }}>
            Market Overview
          </div>
          <div style={{ fontFamily: 'var(--font-display)', fontSize: 24, fontWeight: 700, color: 'var(--text-primary)' }}>
            {sentiment}
          </div>
        </div>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)', paddingTop: 4 }}>
          {confidence}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12, marginBottom: 16 }}>
        <MarketOverviewMetric
          label="Strongest market"
          primary={strongestIndex?.label ?? 'No comparable market'}
          secondary={strongestIndex ? formatMarketPercent(strongestIndex.change_pct) : 'Insufficient raw series'}
          tone={strongestIndex?.direction}
        />
        <MarketOverviewMetric
          label="Top mover"
          primary={topMover?.name ?? 'No comparable mover'}
          secondary={topMover ? formatMarketPercent(topMover.percent_change) : 'Insufficient raw series'}
          tone={topMover?.direction}
        />
        <MarketOverviewMetric
          label="Signals"
          primary={`${signalCount} signals`}
          secondary={`${overview.signal_summary.length} active label${overview.signal_summary.length === 1 ? '' : 's'}`}
        />
      </div>

      <p style={{ margin: 0, color: 'var(--text-secondary)', fontSize: 13, lineHeight: 1.6 }}>
        {overview.commentary}
      </p>
      {overview.evidence.length > 0 && (
        <div style={{ marginTop: 12, color: 'var(--text-muted)', fontSize: 11, fontFamily: 'var(--font-mono)' }}>
          Evidence: {overview.evidence.slice(0, 2).join(' | ')}
        </div>
      )}
    </section>
  )
}

function MarketOverviewMetric({
  label,
  primary,
  secondary,
  tone,
}: {
  label: string
  primary: string
  secondary: string
  tone?: 'up' | 'down' | 'flat'
}) {
  const toneColor = tone === 'up' ? 'var(--up)' : tone === 'down' ? 'var(--down)' : 'var(--text-secondary)'

  return (
    <div style={{ border: '1px solid var(--border-subtle)', borderRadius: 8, padding: '12px 14px', minHeight: 82 }}>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 8 }}>{label}</div>
      <div style={{ fontFamily: 'var(--font-display)', fontSize: 15, color: 'var(--text-primary)', fontWeight: 700, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
        {primary}
      </div>
      <div style={{ marginTop: 6, color: toneColor, fontFamily: 'var(--font-mono)', fontSize: 13 }}>
        {secondary}
      </div>
    </div>
  )
}

function Chip({ label, onRemove }: { label: string; onRemove: () => void }) {
  return (
    <span className="badge-gold-chip">
      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{label}</span>
      <button onClick={onRemove} style={{ background: 'none', border: 'none', color: 'var(--gold)', cursor: 'pointer', padding: '4px', fontSize: 16, lineHeight: 1, flexShrink: 0 }}>×</button>
    </span>
  )
}
