import type { CardSummary } from '../types/api'
import { useWatchlist } from '../hooks/useWatchlist'
import CardArt from './CardArt'
import SignalBadge from './SignalBadge'
import Sparkline from './Sparkline'
import { signalToMeta, formatDelta } from '../lib/utils'

interface CardGridProps {
  cards: CardSummary[]
  onCardClick: (assetId: string) => void
  loading?: boolean
  emptyState?: React.ReactNode
}

function SkeletonCard() {
  return (
    <div className="surface" style={{ padding: 16 }}>
      <div className="skeleton" style={{ height: 168, marginBottom: 12, borderRadius: 8 }} />
      <div className="skeleton" style={{ height: 14, width: '70%', marginBottom: 8 }} />
      <div className="skeleton" style={{ height: 12, width: '50%' }} />
    </div>
  )
}

function CardItem({ card, watched, onClick, onToggleWatch }: {
  card: CardSummary
  watched: boolean
  onClick: () => void
  onToggleWatch: () => void
}) {
  const meta = signalToMeta(card.signal)
  const pct = card.price_delta_pct ?? 0
  const sparkData = [100, 100 + Math.max(-80, Math.min(300, pct))]
  const up = pct >= 0

  return (
    <div
      className="surface"
      onClick={onClick}
      style={{
        padding: 16, cursor: 'pointer', display: 'flex', gap: 12, alignItems: 'flex-start',
        background: `linear-gradient(135deg, ${meta.rowGlow} 0%, var(--bg-surface) 60%)`,
        borderLeft: `3px solid ${meta.color}`,
        position: 'relative',
        transition: 'transform 0.15s, box-shadow 0.15s',
      }}
      onMouseEnter={e => {
        ;(e.currentTarget as HTMLDivElement).style.transform = 'translateY(-2px)'
        ;(e.currentTarget as HTMLDivElement).style.boxShadow = `0 8px 32px ${meta.color}20`
      }}
      onMouseLeave={e => {
        ;(e.currentTarget as HTMLDivElement).style.transform = ''
        ;(e.currentTarget as HTMLDivElement).style.boxShadow = ''
      }}
    >
      <button
        onClick={e => { e.stopPropagation(); onToggleWatch() }}
        style={{
          position: 'absolute', top: 8, right: 8, zIndex: 2,
          background: 'rgba(12,12,16,0.7)', border: 'none', borderRadius: '50%',
          width: 28, height: 28, cursor: 'pointer',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 16, color: watched ? 'var(--gold)' : 'var(--text-muted)',
          transition: 'color 0.15s, transform 0.1s',
        }}
        onMouseEnter={e => (e.currentTarget.style.transform = 'scale(1.15)')}
        onMouseLeave={e => (e.currentTarget.style.transform = 'scale(1)')}
        aria-label={watched ? 'Remove from watchlist' : 'Add to watchlist'}
        title={watched ? 'Remove from watchlist' : 'Add to watchlist'}
      >
        {watched ? '⭐' : '☆'}
      </button>

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
}

export default function CardGrid({ cards, onCardClick, loading, emptyState }: CardGridProps) {
  const { isWatched, toggle } = useWatchlist()

  if (loading) {
    return (
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(330px, 1fr))', gap: 16 }}>
        {Array.from({ length: 6 }, (_, i) => <SkeletonCard key={i} />)}
      </div>
    )
  }

  if (cards.length === 0) {
    return <>{emptyState ?? <div style={{ textAlign: 'center', padding: 80, color: 'var(--text-muted)' }}>No cards</div>}</>
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(330px, 1fr))', gap: 16 }}>
      {cards.map(card => (
        <CardItem
          key={card.asset_id}
          card={card}
          watched={isWatched(card.asset_id)}
          onClick={() => onCardClick(card.asset_id)}
          onToggleWatch={() => {
            const result = toggle(card.asset_id)
            if (!result.ok) {
              if (result.reason === 'cap') {
                alert('Watchlist is full (max 500 cards). Remove some to add more.')
              } else if (result.reason === 'storage') {
                alert('Could not save watchlist. Storage may be disabled.')
              }
            }
          }}
        />
      ))}
    </div>
  )
}
