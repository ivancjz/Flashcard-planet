import { useState, useEffect } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { fetchCard } from '../api/api'
import NavBar from '../components/NavBar'
import ComparisonChart from '../components/ComparisonChart'
import SignalBadge from '../components/SignalBadge'
import CardArt from '../components/CardArt'
import { formatDelta } from '../lib/utils'
import type { CardDetail } from '../types/api'

const MAX_COMPARE = 4
const COMPARE_COLORS = [
  'var(--gold)',
  'var(--breakout)',
  'var(--move)',
  'var(--watch)',
]

export default function ComparePage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()

  const rawIds = searchParams.get('ids')?.split(',').filter(Boolean) ?? []
  const ids = Array.from(new Set(rawIds)).slice(0, MAX_COMPARE)
  // Stable string key — prevents array identity re-triggering the effect on every render
  const idsKey = ids.join(',')

  const [cards, setCards] = useState<CardDetail[]>([])
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState(false)

  useEffect(() => {
    if (ids.length === 0) {
      setCards([])
      setLoading(false)
      setLoadError(false)
      return
    }
    let active = true   // stale-result guard
    setLoading(true)
    setLoadError(false)
    Promise.all(ids.map(id => fetchCard(id).catch(() => null)))
      .then(results => {
        if (!active) return
        const valid = results.filter((c): c is CardDetail => c !== null)
        const ordered = ids
          .map(id => valid.find(c => c.asset_id === id))
          .filter((c): c is CardDetail => c !== undefined)
        setCards(ordered)
        // If IDs were provided but none resolved, surface an error state
        setLoadError(ordered.length === 0)
        setLoading(false)
      })
    return () => { active = false }
  }, [idsKey])   // eslint-disable-line react-hooks/exhaustive-deps

  const removeCard = (assetId: string) => {
    const newIds = ids.filter(id => id !== assetId)
    if (newIds.length === 0) {
      setSearchParams({})
    } else {
      setSearchParams({ ids: newIds.join(',') })
    }
  }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-base)' }}>
      <NavBar />
      <div className="page-content">
        <div style={{ marginBottom: 24 }}>
          <div style={{ fontFamily: 'var(--font-display)', fontSize: 22, fontWeight: 700, color: 'var(--text-primary)' }}>
            Compare Cards
          </div>
          <div style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 4 }}>
            {cards.length === 0
              ? 'Select cards from the market to compare'
              : `Comparing ${cards.length} card${cards.length !== 1 ? 's' : ''}`}
          </div>
        </div>

        {/* Empty state — no IDs in URL */}
        {ids.length === 0 && !loading && (
          <div style={{ textAlign: 'center', padding: '80px 20px' }}>
            <div style={{ fontSize: 48, marginBottom: 16 }}>📊</div>
            <div style={{ fontFamily: 'var(--font-display)', fontSize: 18, marginBottom: 8, color: 'var(--text-primary)' }}>
              No cards selected
            </div>
            <div style={{ color: 'var(--text-muted)', marginBottom: 24, fontSize: 14 }}>
              Open any card and tap "Compare with…" to start
            </div>
            <button className="btn btn-primary" onClick={() => navigate('/market')}>
              Browse the market
            </button>
          </div>
        )}

        {/* Error state — IDs provided but none loaded */}
        {ids.length > 0 && !loading && loadError && (
          <div style={{ textAlign: 'center', padding: '80px 20px' }}>
            <div style={{ fontSize: 48, marginBottom: 16 }}>🔍</div>
            <div style={{ fontFamily: 'var(--font-display)', fontSize: 18, marginBottom: 8, color: 'var(--text-primary)' }}>
              Cards not found
            </div>
            <div style={{ color: 'var(--text-muted)', marginBottom: 24, fontSize: 14 }}>
              The selected cards could not be loaded.
            </div>
            <button className="btn btn-ghost" onClick={() => navigate('/market')}>
              Browse the market
            </button>
          </div>
        )}

        {/* Loading skeleton */}
        {loading && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 16, marginBottom: 24 }}>
            {ids.map(id => (
              <div key={id} className="surface" style={{ padding: 16, height: 200 }}>
                <div className="skeleton" style={{ height: '100%', borderRadius: 8 }} />
              </div>
            ))}
          </div>
        )}

        {/* Single-card prompt */}
        {!loading && !loadError && cards.length === 1 && (
          <div style={{
            padding: '12px 16px', marginBottom: 16,
            background: 'var(--bg-elevated)', borderRadius: 'var(--radius-sm)',
            border: '1px dashed var(--border-default)',
            display: 'flex', alignItems: 'center', gap: 12,
            fontSize: 13, color: 'var(--text-muted)',
          }}>
            Add at least one more card to see a comparison.
            <button className="btn btn-ghost btn-sm" onClick={() => navigate('/market')}>
              + Add card
            </button>
          </div>
        )}

        {/* Card grid — responsive, min 260px per card */}
        {!loading && !loadError && cards.length > 0 && (
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
            gap: 16,
            marginBottom: 24,
          }}>
            {cards.map((card, i) => (
              <CompareCard
                key={card.asset_id}
                card={card}
                color={COMPARE_COLORS[i]}
                onRemove={() => removeCard(card.asset_id)}
                onClickName={() => navigate(`/market/${card.asset_id}`)}
              />
            ))}

            {/* Add slot when room remains */}
            {cards.length < MAX_COMPARE && (
              <button
                onClick={() => navigate('/market')}
                style={{
                  border: '2px dashed var(--border-default)',
                  borderRadius: 'var(--radius-md)',
                  background: 'transparent',
                  color: 'var(--text-muted)',
                  cursor: 'pointer',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 8,
                  fontSize: 13,
                  minHeight: 200,
                  padding: 16,
                }}
              >
                <span style={{ fontSize: 24 }}>+</span>
                <span>Add card</span>
              </button>
            )}
          </div>
        )}

        {/* Comparison chart */}
        {!loading && !loadError && cards.length >= 2 && (
          <div className="surface" style={{ padding: 20 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <span style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 14 }}>
                30-Day Price Trend
              </span>
              <span style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                % change from earliest data point · TCGPlayer prices
              </span>
            </div>
            <ComparisonChart cards={cards} colors={COMPARE_COLORS} />
          </div>
        )}
      </div>
    </div>
  )
}

function CompareCard({ card, color, onRemove, onClickName }: {
  card: CardDetail
  color: string
  onRemove: () => void
  onClickName: () => void
}) {
  const up = (card.price_delta_pct ?? 0) >= 0
  return (
    <div style={{
      padding: 16,
      background: 'var(--bg-surface)',
      border: `2px solid ${color}`,
      borderRadius: 'var(--radius-md)',
      position: 'relative',
    }}>
      <button
        onClick={onRemove}
        aria-label="Remove from comparison"
        style={{
          position: 'absolute', top: 8, right: 8,
          background: 'rgba(12,12,16,0.7)', border: 'none',
          borderRadius: '50%', width: 22, height: 22,
          color: 'var(--text-secondary)', cursor: 'pointer',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 14, lineHeight: 1,
        }}
      >
        ×
      </button>

      <div style={{ display: 'flex', gap: 10, marginBottom: 12 }}>
        <CardArt
          name={card.name}
          type={card.card_type}
          rarity={card.rarity}
          imageUrl={card.image_url}
          size="sm"
        />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            onClick={onClickName}
            style={{
              fontFamily: 'var(--font-display)', fontSize: 13, fontWeight: 600,
              cursor: 'pointer', marginBottom: 2, color: 'var(--text-primary)',
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}
          >
            {card.name}
          </div>
          <div style={{
            color: 'var(--text-muted)', fontSize: 11, marginBottom: 8,
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}>
            {card.set_name}
          </div>
          <SignalBadge signal={card.signal} />
        </div>
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
        <div>
          <div style={{ color: 'var(--text-muted)', fontSize: 10 }}>TCG</div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13 }}>
            {card.tcg_price != null ? `$${card.tcg_price.toFixed(2)}` : '—'}
          </div>
        </div>
        <div>
          <div style={{ color: 'var(--text-muted)', fontSize: 10 }}>eBay</div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13 }}>
            {card.ebay_price != null ? `$${card.ebay_price.toFixed(2)}` : '—'}
          </div>
        </div>
        <div>
          <div style={{ color: 'var(--text-muted)', fontSize: 10 }}>24h</div>
          <div className={up ? 'up' : 'down'}>{formatDelta(card.price_delta_pct)}</div>
        </div>
      </div>
    </div>
  )
}
