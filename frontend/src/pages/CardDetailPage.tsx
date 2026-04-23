import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import NavBar from '../components/NavBar'
import CardArt from '../components/CardArt'
import SignalBadge from '../components/SignalBadge'
import AIAnalysisSection from '../components/AIAnalysisSection'
import { fetchCard } from '../api/api'
import { signalToMeta, formatDelta } from '../lib/utils'
import type { CardDetail, PricePoint } from '../types/api'

const SIGNAL_DESCRIPTION: Record<string, string> = {
  BREAKOUT: 'Price has jumped significantly above baseline. High sales volume confirms buyer demand. Consider acting before the market adjusts.',
  MOVE: 'Price is shifting directionally with above-average volume. Momentum is building — watch closely.',
  WATCH: 'Early signals of price movement detected. Not yet confirmed — monitor the next 24–48h.',
  IDLE: 'No significant price movement. Market is stable for this card.',
  INSUFFICIENT_DATA: 'Not enough recent sales data to compute a reliable signal.',
}

function AreaChart({ data }: { data: PricePoint[] }) {
  const W = 560, H = 160
  const PAD = { top: 12, right: 12, bottom: 28, left: 48 }
  const IW = W - PAD.left - PAD.right
  const IH = H - PAD.top - PAD.bottom

  const allPrices = data.flatMap(d => [d.tcg_price, d.ebay_price]).filter((v): v is number => v != null)
  if (allPrices.length === 0) return <div style={{ color: 'var(--text-muted)', padding: 20 }}>No price history available.</div>

  const minP = Math.min(...allPrices)
  const maxP = Math.max(...allPrices)
  const range = maxP - minP || 1
  const xOf = (i: number) => (i / Math.max(data.length - 1, 1)) * IW
  const yOf = (p: number) => IH - ((p - minP) / range) * IH

  const linePoints = (prices: (number | null)[]) =>
    prices.map((p, i) => p != null ? `${xOf(i)},${yOf(p)}` : null).filter(Boolean).join(' L ')

  const areaPath = (prices: (number | null)[]) => {
    const pts = prices.map((p, i) => p != null ? [xOf(i), yOf(p)] as [number, number] : null).filter((x): x is [number, number] => x != null)
    if (!pts.length) return ''
    return `M ${pts[0][0]},${IH} L ${pts.map(([x, y]) => `${x},${y}`).join(' L ')} L ${pts[pts.length - 1][0]},${IH} Z`
  }

  const tcgPrices = data.map(d => d.tcg_price)
  const ebayPrices = data.map(d => d.ebay_price)
  const lastIdx = data.length - 1

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: 'block' }}>
      <defs>
        <linearGradient id="tcg-area" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--gold)" stopOpacity="0.3" />
          <stop offset="100%" stopColor="var(--gold)" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="ebay-area" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--breakout)" stopOpacity="0.15" />
          <stop offset="100%" stopColor="var(--breakout)" stopOpacity="0" />
        </linearGradient>
      </defs>
      <g transform={`translate(${PAD.left},${PAD.top})`}>
        {[minP, (minP + maxP) / 2, maxP].map((p, i) => (
          <text key={i} x={-6} y={yOf(p) + 4} textAnchor="end" fontSize={9} fontFamily="'Space Mono', monospace" fill="var(--text-muted)">
            ${p.toFixed(0)}
          </text>
        ))}
        {areaPath(ebayPrices) && <path d={areaPath(ebayPrices)} fill="url(#ebay-area)" />}
        {linePoints(ebayPrices) && <path d={`M ${linePoints(ebayPrices)}`} fill="none" stroke="var(--breakout)" strokeWidth={1.5} strokeDasharray="4 2" opacity={0.7} />}
        {areaPath(tcgPrices) && <path d={areaPath(tcgPrices)} fill="url(#tcg-area)" />}
        {linePoints(tcgPrices) && <path d={`M ${linePoints(tcgPrices)}`} fill="none" stroke="var(--gold)" strokeWidth={2} />}
        {tcgPrices[lastIdx] != null && <circle cx={xOf(lastIdx)} cy={yOf(tcgPrices[lastIdx]!)} r={4} fill="var(--gold)" stroke="var(--bg-base)" strokeWidth={2} />}
        {ebayPrices[lastIdx] != null && <circle cx={xOf(lastIdx)} cy={yOf(ebayPrices[lastIdx]!)} r={3} fill="var(--breakout)" stroke="var(--bg-base)" strokeWidth={1.5} />}
        {[0, Math.floor(data.length / 2), lastIdx].map(i => (
          <text key={i} x={xOf(i)} y={IH + 18} textAnchor="middle" fontSize={9} fontFamily="'Space Mono', monospace" fill="var(--text-muted)">
            {data[i]?.date?.slice(5)}
          </text>
        ))}
      </g>
    </svg>
  )
}

export default function CardDetailPage() {
  const { assetId } = useParams<{ assetId: string }>()
  const nav = useNavigate()
  const [card, setCard] = useState<CardDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!assetId) return
    setLoading(true)
    fetchCard(assetId)
      .then(setCard)
      .catch(() => setError('Card not found.'))
      .finally(() => setLoading(false))
  }, [assetId])

  if (loading) return (
    <div>
      <NavBar />
      <div className="page-content">
        <div className="detail-grid">
          <div className="skeleton" style={{ height: 336 }} />
          <div>
            <div className="skeleton" style={{ height: 160, marginBottom: 16 }} />
            <div className="skeleton" style={{ height: 200 }} />
          </div>
        </div>
      </div>
    </div>
  )

  if (error || !card) return (
    <div><NavBar /><div className="page-content" style={{ color: '#ef4444' }}>{error ?? 'Card not found.'}</div></div>
  )

  const meta = signalToMeta(card.signal)
  const up = (card.price_delta_pct ?? 0) >= 0

  return (
    <div>
      <NavBar />
      <div className="page-content">
        <button className="btn btn-ghost btn-sm" onClick={() => nav('/market')} style={{ marginBottom: 24 }}>← Back to Market</button>

        <div className="detail-grid">
          <div>
            <div className="holo float" style={{ marginBottom: 20 }}>
              <CardArt name={card.name} type={card.card_type} rarity={card.rarity} imageUrl={card.image_url} size="lg" />
            </div>
            <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 20, fontWeight: 700, marginBottom: 4 }}>{card.name}</h2>
            <div style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 16 }}>{card.set_name}</div>
            <table style={{ fontSize: 12, width: '100%', borderCollapse: 'collapse' }}>
              {[
                ['Signal', <SignalBadge signal={card.signal} />],
                ['Type', card.card_type ?? '—'],
                ['Rarity', card.rarity ?? '—'],
                ['Liquidity', card.liquidity_score != null ? `${card.liquidity_score}/100` : '—'],
              ].map(([label, value]) => (
                <tr key={String(label)} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                  <td style={{ padding: '8px 0', color: 'var(--text-muted)' }}>{label}</td>
                  <td style={{ padding: '8px 0', textAlign: 'right' }}>{value}</td>
                </tr>
              ))}
            </table>
            <div style={{ marginTop: 20, display: 'flex', flexDirection: 'column', gap: 10 }}>
              <button className="btn btn-primary" style={{ width: '100%', justifyContent: 'center' }}>Set Alert</button>
              <button className="btn btn-ghost" style={{ width: '100%', justifyContent: 'center' }}>Add to Watchlist</button>
            </div>
          </div>

          <div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 20 }}>
              {[
                { label: 'TCGPlayer', value: card.tcg_price != null ? `$${card.tcg_price.toFixed(2)}` : '—', color: 'var(--gold)' },
                { label: 'eBay sold', value: card.ebay_price != null ? `$${card.ebay_price.toFixed(2)}` : '—', color: 'var(--breakout)' },
                { label: 'Spread', value: card.spread_pct != null ? `${card.spread_pct > 0 ? '+' : ''}${card.spread_pct.toFixed(1)}%` : '—', color: 'var(--text-secondary)' },
              ].map(tile => (
                <div key={tile.label} className="surface" style={{ padding: '16px 20px' }}>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 6 }}>{tile.label}</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 22, fontWeight: 700, color: tile.color }}>{tile.value}</div>
                </div>
              ))}
            </div>

            <div className="surface" style={{ padding: '12px 20px', marginBottom: 20, display: 'flex', alignItems: 'center', gap: 12 }}>
              <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>24h change</span>
              <span className={up ? 'up' : 'down'} style={{ fontSize: 16, fontWeight: 700 }}>
                {formatDelta(card.price_delta_pct)}
              </span>
            </div>

            <div className="surface" style={{ padding: 20, marginBottom: 20 }}>
              <div style={{ display: 'flex', gap: 16, marginBottom: 12 }}>
                <span style={{ fontSize: 12, color: 'var(--gold)' }}>— TCGPlayer</span>
                <span style={{ fontSize: 12, color: 'var(--breakout)' }}>-- eBay sold</span>
              </div>
              <AreaChart data={card.price_history} />
            </div>

            <div className="surface" style={{ padding: 20, borderLeft: `4px solid ${meta.color}` }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
                <SignalBadge signal={card.signal} />
                <span style={{ fontSize: 13, fontWeight: 600, color: meta.color }}>Signal Analysis</span>
              </div>
              <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
                {SIGNAL_DESCRIPTION[card.signal]}
              </p>
            </div>

            <AIAnalysisSection aiAnalysis={card.ai_analysis ?? null} />
          </div>
        </div>
      </div>
    </div>
  )
}
