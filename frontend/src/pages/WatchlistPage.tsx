import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { fetchCardsById } from '../api/api'
import { useWatchlist } from '../hooks/useWatchlist'
import NavBar from '../components/NavBar'
import CardGrid from '../components/CardGrid'
import type { CardSummary } from '../types/api'

type WatchlistSort = 'recently_added' | 'change' | 'price' | 'volume'

export default function WatchlistPage() {
  const navigate = useNavigate()
  const { entries, count } = useWatchlist()
  const [cards, setCards] = useState<CardSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [sort, setSort] = useState<WatchlistSort>('recently_added')
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const searchRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 300)
    return () => clearTimeout(t)
  }, [search])

  useEffect(() => {
    if (entries.length === 0) {
      setCards([])
      setLoading(false)
      return
    }

    const controller = new AbortController()
    setLoading(true)
    const serverSort = sort === 'recently_added' ? 'change' : sort

    fetchCardsById({
      asset_ids: entries.map(e => e.asset_id),
      sort: serverSort,
      search: debouncedSearch || undefined,
      limit: 500,
      signal: controller.signal,  // AbortSignal to cancel stale requests
    }).then(response => {
      let result = response.cards

      if (sort === 'recently_added') {
        // entries are stored oldest-first; reverse index = most recent first
        const orderMap = new Map(entries.map((e, i) => [e.asset_id, i]))
        result = [...result].sort((a, b) => {
          const ai = orderMap.get(a.asset_id) ?? 0
          const bi = orderMap.get(b.asset_id) ?? 0
          return bi - ai
        })
      }

      setCards(result)
      setLoading(false)
    }).catch(err => {
      if ((err as Error).name === 'AbortError') return
      console.error('Failed to load watchlist:', err)
      setLoading(false)
    })

    return () => controller.abort()
  }, [entries, sort, debouncedSearch])

  const searchStyle: React.CSSProperties = {
    width: '100%', boxSizing: 'border-box',
    padding: '9px 36px 9px 12px',
    background: 'var(--bg-surface)',
    border: '1px solid var(--border-subtle)',
    borderRadius: 'var(--radius-sm)',
    color: 'var(--text-primary)',
    fontFamily: 'var(--font-body)',
    fontSize: 14,
    outline: 'none',
    transition: 'border-color 0.15s',
  }

  const selectStyle: React.CSSProperties = {
    padding: '9px 12px',
    background: 'var(--bg-surface)',
    border: '1px solid var(--border-subtle)',
    borderRadius: 'var(--radius-sm)',
    color: 'var(--text-primary)',
    fontFamily: 'var(--font-body)',
    fontSize: 14,
    outline: 'none',
    cursor: 'pointer',
    flexShrink: 0,
  }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-base)' }}>
      <NavBar />
      <div className="page-content">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 24 }}>
          <div>
            <div style={{ fontFamily: 'var(--font-display)', fontSize: 22, fontWeight: 700, color: 'var(--text-primary)' }}>⭐ Watchlist</div>
            <div style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 4 }}>{count} card{count !== 1 ? 's' : ''} watched</div>
          </div>
        </div>

        {count === 0 ? (
          <div style={{ textAlign: 'center', padding: '80px 0' }}>
            <div style={{ fontSize: 48, marginBottom: 16 }}>☆</div>
            <div style={{ fontFamily: 'var(--font-display)', fontSize: 18, marginBottom: 8, color: 'var(--text-primary)' }}>
              Your watchlist is empty
            </div>
            <div style={{ color: 'var(--text-muted)', marginBottom: 24, fontSize: 14 }}>
              Star cards on the market to track them here
            </div>
            <button className="btn btn-primary" onClick={() => navigate('/market')}>
              Browse the market
            </button>
          </div>
        ) : (
          <>
            <div style={{ display: 'flex', gap: 12, marginBottom: 16, alignItems: 'center' }}>
              <div style={{ position: 'relative', flex: 1 }}>
                <input
                  ref={searchRef}
                  type="search"
                  placeholder="Search watchlist…"
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  style={searchStyle}
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
              <select
                value={sort}
                onChange={e => setSort(e.target.value as WatchlistSort)}
                style={selectStyle}
              >
                <option value="recently_added">Recently added</option>
                <option value="change">Change</option>
                <option value="price">Price</option>
                <option value="volume">Volume</option>
              </select>
            </div>

            <CardGrid
              cards={cards}
              loading={loading}
              onCardClick={id => navigate(`/market/${id}`)}
              emptyState={
                <div style={{ textAlign: 'center', padding: 48, color: 'var(--text-muted)' }}>
                  {debouncedSearch
                    ? `No watched cards match "${debouncedSearch}"`
                    : 'No cards in watchlist'}
                </div>
              }
            />
          </>
        )}
      </div>
    </div>
  )
}
