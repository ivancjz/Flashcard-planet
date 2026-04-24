import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import NavBar from '../components/NavBar'
import TickerBar from '../components/TickerBar'
import GameSwitcher from '../components/GameSwitcher'
import SignalBadge from '../components/SignalBadge'
import CardArt from '../components/CardArt'
import Sparkline from '../components/Sparkline'
import ProGate from '../components/ProGate'
import { fetchStats, fetchCards, fetchTicker } from '../api/api'
import { signalToMeta, formatDelta } from '../lib/utils'
import type { Signal, CardSummary, MarketStats, TickerItem } from '../types/api'

type SortKey = 'change' | 'price' | 'volume'
const FILTERS: Array<{ value: Signal | 'ALL'; label: string }> = [
  { value: 'ALL', label: 'All' },
  { value: 'BREAKOUT', label: '▲ Breakout' },
  { value: 'MOVE', label: '◆ Move' },
  { value: 'WATCH', label: '◆ Watch' },
  { value: 'IDLE', label: '— Idle' },
]

function SkeletonCard() {
  return (
    <div className="surface" style={{ padding: 16 }}>
      <div className="skeleton" style={{ height: 168, marginBottom: 12, borderRadius: 8 }} />
      <div className="skeleton" style={{ height: 14, width: '70%', marginBottom: 8 }} />
      <div className="skeleton" style={{ height: 12, width: '50%' }} />
    </div>
  )
}

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

  useEffect(() => { fetchStats().then(setStats); fetchTicker().then(setTicker) }, [])

  // Debounce search: wait 300ms after last keystroke before hitting API
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 300)
    return () => clearTimeout(t)
  }, [search])

  const LIVE_GAMES = ['pokemon', 'yugioh']

  useEffect(() => {
    if (!LIVE_GAMES.includes(activeGame)) return
    setLoading(true)
    fetchCards({ game: activeGame, signal, sort, search: debouncedSearch })
      .then(r => { setCards(r.cards); setLoading(false) })
      .catch(() => setLoading(false))
  }, [signal, sort, activeGame, debouncedSearch])

  function handleGameChange(gameId: string) {
    setActiveGame(gameId)
    setSearch('')        // different card namespace — reset search
    setDebouncedSearch('')
  }

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

        {/* Search */}
        <div style={{ position: 'relative', marginBottom: 16 }}>
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
            <ProGate locked feature="Sort by Volume" reason="Advanced sorting on Pro plan">
              <button className="btn btn-ghost btn-sm" onClick={() => setSort('volume')}
                style={sort === 'volume' ? { background: 'var(--bg-elevated)', color: 'var(--gold)', borderColor: 'var(--gold-dim)' } : {}}>
                Volume
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
        ) : loading ? (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(330px, 1fr))', gap: 16 }}>
            {Array.from({ length: 6 }, (_, i) => <SkeletonCard key={i} />)}
          </div>
        ) : cards.length === 0 ? (
          debouncedSearch ? (
            <div style={{ textAlign: 'center', padding: '48px 0', color: 'var(--text-muted)' }}>
              <div style={{ fontSize: 32, marginBottom: 12 }}>🔍</div>
              <div style={{ fontFamily: 'var(--font-display)', fontSize: 16, marginBottom: 8, color: 'var(--text-secondary)' }}>
                No cards match "{debouncedSearch}"
              </div>
              <div style={{ fontSize: 13 }}>Try a different name, or clear the search to see all cards.</div>
            </div>
          ) : (
            <div style={{ textAlign: 'center', padding: 80, color: 'var(--text-muted)' }}>No cards match this filter</div>
          )
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(330px, 1fr))', gap: 16 }}>
            {cards.map(card => {
              const meta = signalToMeta(card.signal)
              // 2-point sparkline derived from delta: direction always matches signal
              const pct = card.price_delta_pct ?? 0
              const sparkData = [100, 100 + Math.max(-80, Math.min(300, pct))]
              const up = pct >= 0
              return (
                <div
                  key={card.asset_id}
                  className="surface"
                  onClick={() => nav(`/market/${card.asset_id}`)}
                  style={{
                    padding: 16, cursor: 'pointer', display: 'flex', gap: 12, alignItems: 'flex-start',
                    background: `linear-gradient(135deg, ${meta.rowGlow} 0%, var(--bg-surface) 60%)`,
                    borderLeft: `3px solid ${meta.color}`,
                    transition: 'transform 0.15s, box-shadow 0.15s',
                  }}
                  onMouseEnter={e => { (e.currentTarget as HTMLDivElement).style.transform = 'translateY(-2px)'; (e.currentTarget as HTMLDivElement).style.boxShadow = `0 8px 32px ${meta.color}20` }}
                  onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.transform = ''; (e.currentTarget as HTMLDivElement).style.boxShadow = '' }}
                >
                  <CardArt name={card.name} type={card.card_type} rarity={card.rarity} imageUrl={card.image_url} size="sm" />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, marginBottom: 4 }}>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 14, color: 'var(--text-primary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{card.name}</div>
                        <div style={{ fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{card.set_name}</div>
                      </div>
                      <SignalBadge signal={card.signal} />
                    </div>
                    <div style={{ display: 'flex', gap: 16, marginTop: 10, marginBottom: 10 }}>
                      <div>
                        <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>TCG</div>
                        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--text-primary)' }}>{card.tcg_price != null ? `$${card.tcg_price.toFixed(2)}` : '—'}</div>
                      </div>
                      <div>
                        <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>eBay</div>
                        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--text-primary)' }}>{card.ebay_price != null ? `$${card.ebay_price.toFixed(2)}` : '—'}</div>
                      </div>
                      <div>
                        <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>24h</div>
                        <div className={up ? 'up' : 'down'}>{formatDelta(card.price_delta_pct)}</div>
                      </div>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Sparkline data={sparkData} width={80} height={28} />
                      <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{card.volume_24h != null ? `${card.volume_24h} sales` : ''}</div>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
