import { useEffect, useRef, useState } from 'react'
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

function NormalizedChart({ data }: { data: PricePoint[] }) {
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null)
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 })
  const containerRef = useRef<HTMLDivElement>(null)

  const W = 560, H = 180
  const PAD = { top: 16, right: 16, bottom: 28, left: 52 }
  const IW = W - PAD.left - PAD.right
  const IH = H - PAD.top - PAD.bottom

  function normalize(prices: (number | null)[]): (number | null)[] {
    const baseline = prices.find(p => p != null && p > 0)
    if (baseline == null) return prices.map(() => null)
    return prices.map(p => (p != null && p > 0 ? ((p - baseline) / baseline) * 100 : null))
  }

  const tcgRaw = data.map(d => d.tcg_price)
  const ebayRaw = data.map(d => d.ebay_price)
  const tcgPct = normalize(tcgRaw)
  const ebayPct = normalize(ebayRaw)
  const tcgValid = tcgPct.filter(p => p != null).length >= 2
  const ebayValid = ebayPct.filter(p => p != null).length >= 2

  if (!tcgValid && !ebayValid) {
    return (
      <div style={{ height: H, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: 13 }}>
        No price history available
      </div>
    )
  }

  const allPcts = [...tcgPct, ...ebayPct].filter((p): p is number => p != null)
  const minY = Math.min(0, ...allPcts)
  const maxY = Math.max(0, ...allPcts)
  const rangeY = maxY - minY || 1

  const xOf = (i: number) => (i / Math.max(data.length - 1, 1)) * IW
  const yOf = (pct: number) => IH - ((pct - minY) / rangeY) * IH
  const zeroY = Math.min(IH, Math.max(0, yOf(0)))

  function buildLinePath(pcts: (number | null)[]): string {
    const cmds: string[] = []
    let pen = false
    for (let i = 0; i < pcts.length; i++) {
      const p = pcts[i]
      if (p != null) {
        cmds.push(pen ? `L ${xOf(i)},${yOf(p)}` : `M ${xOf(i)},${yOf(p)}`)
        pen = true
      } else {
        pen = false
      }
    }
    return cmds.join(' ')
  }

  function buildAreaPath(pcts: (number | null)[]): string {
    const pts = pcts
      .map((p, i) => (p != null ? ([xOf(i), yOf(p)] as [number, number]) : null))
      .filter((x): x is [number, number] => x != null)
    if (pts.length < 2) return ''
    return `M ${pts[0][0]},${zeroY} L ${pts.map(([x, y]) => `${x},${y}`).join(' L ')} L ${pts[pts.length - 1][0]},${zeroY} Z`
  }

  const range = maxY - minY
  const rawStep = range / 4
  const mag = Math.pow(10, Math.floor(Math.log10(rawStep || 1)))
  const tickStep = Math.ceil(rawStep / mag) * mag || 5
  const ticks = new Set<number>([0])
  for (let t = Math.floor(minY / tickStep) * tickStep; t <= maxY + tickStep; t += tickStep) ticks.add(Math.round(t))
  const sortedTicks = [...ticks].filter(t => t >= minY - tickStep * 0.1 && t <= maxY + tickStep * 0.1).sort((a, b) => a - b)

  const lastIdx = data.length - 1

  function handleMouseMove(e: React.MouseEvent<HTMLDivElement>) {
    const container = containerRef.current
    if (!container || lastIdx < 1) return
    const rect = container.getBoundingClientRect()
    const innerX = (e.clientX - rect.left) * (W / rect.width) - PAD.left
    const idx = Math.max(0, Math.min(lastIdx, Math.round((innerX / IW) * lastIdx)))
    setHoveredIdx(idx)
    setMousePos({ x: e.clientX - rect.left, y: e.clientY - rect.top })
  }

  const hPoint = hoveredIdx != null ? data[hoveredIdx] : null
  const hTcgRaw = hoveredIdx != null ? tcgRaw[hoveredIdx] : null
  const hEbayRaw = hoveredIdx != null ? ebayRaw[hoveredIdx] : null
  const hTcgPct = hoveredIdx != null ? tcgPct[hoveredIdx] : null
  const hEbayPct = hoveredIdx != null ? ebayPct[hoveredIdx] : null
  const showTooltip = hPoint != null && (hTcgPct != null || hEbayPct != null)

  const fmtPct = (p: number) => (p >= 0 ? `+${p.toFixed(1)}%` : `${p.toFixed(1)}%`)
  const fmtPrice = (p: number) => `$${p.toFixed(2)}`

  // Flip tooltip to left side when hovering the right 60% of the chart
  const flipLeft = hoveredIdx != null && hoveredIdx > data.length * 0.6
  const tooltipLeft = flipLeft ? mousePos.x - 164 : mousePos.x + 14
  const tooltipTop = Math.max(4, mousePos.y - 56)

  return (
    <div
      ref={containerRef}
      style={{ position: 'relative', cursor: 'crosshair' }}
      onMouseMove={handleMouseMove}
      onMouseLeave={() => setHoveredIdx(null)}
    >
      <svg
        width="100%"
        viewBox={`0 0 ${W} ${H}`}
        style={{ display: 'block' }}
      >
        <defs>
          <linearGradient id="tcg-norm-grad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--gold)" stopOpacity="0.22" />
            <stop offset="100%" stopColor="var(--gold)" stopOpacity="0" />
          </linearGradient>
          <linearGradient id="ebay-norm-grad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--breakout)" stopOpacity="0.12" />
            <stop offset="100%" stopColor="var(--breakout)" stopOpacity="0" />
          </linearGradient>
        </defs>
        <g transform={`translate(${PAD.left},${PAD.top})`}>
          {/* Zero reference line */}
          <line x1={0} y1={zeroY} x2={IW} y2={zeroY} stroke="rgba(255,255,255,0.18)" strokeWidth={1} strokeDasharray="4 3" />

          {/* Y-axis ticks */}
          {sortedTicks.map(t => (
            <text key={t} x={-6} y={yOf(t) + 4} textAnchor="end" fontSize={9} fontFamily="'Space Mono', monospace"
              fill={t === 0 ? 'var(--text-secondary)' : 'var(--text-muted)'}>
              {t >= 0 ? `+${t}%` : `${t}%`}
            </text>
          ))}

          {/* eBay series */}
          {ebayValid && (() => {
            const area = buildAreaPath(ebayPct)
            const line = buildLinePath(ebayPct)
            const last = ebayPct[lastIdx]
            return (
              <>
                {area && <path d={area} fill="url(#ebay-norm-grad)" />}
                {line && <path d={line} fill="none" stroke="var(--breakout)" strokeWidth={1.5} strokeDasharray="4 2" opacity={0.8} />}
                {last != null && <circle cx={xOf(lastIdx)} cy={yOf(last)} r={3} fill="var(--breakout)" stroke="var(--bg-base)" strokeWidth={1.5} />}
              </>
            )
          })()}

          {/* TCG series */}
          {tcgValid && (() => {
            const area = buildAreaPath(tcgPct)
            const line = buildLinePath(tcgPct)
            const last = tcgPct[lastIdx]
            return (
              <>
                {area && <path d={area} fill="url(#tcg-norm-grad)" />}
                {line && <path d={line} fill="none" stroke="var(--gold)" strokeWidth={2} />}
                {last != null && <circle cx={xOf(lastIdx)} cy={yOf(last)} r={4} fill="var(--gold)" stroke="var(--bg-base)" strokeWidth={2} />}
              </>
            )
          })()}

          {/* Hover: vertical rule */}
          {hoveredIdx != null && (
            <line x1={xOf(hoveredIdx)} y1={0} x2={xOf(hoveredIdx)} y2={IH}
              stroke="rgba(255,255,255,0.18)" strokeWidth={1} />
          )}

          {/* Hover: enlarged data point circles (rendered above series) */}
          {hoveredIdx != null && hEbayPct != null && ebayValid && (
            <circle cx={xOf(hoveredIdx)} cy={yOf(hEbayPct)} r={5}
              fill="var(--breakout)" stroke="var(--bg-base)" strokeWidth={2} />
          )}
          {hoveredIdx != null && hTcgPct != null && tcgValid && (
            <circle cx={xOf(hoveredIdx)} cy={yOf(hTcgPct)} r={5.5}
              fill="var(--gold)" stroke="var(--bg-base)" strokeWidth={2} />
          )}

          {/* Transparent hit area — must be last to sit on top of all series */}
          <rect x={0} y={0} width={IW} height={IH} fill="transparent" />

          {/* X-axis date labels */}
          {[0, Math.floor(data.length / 2), lastIdx].map(i => (
            <text key={i} x={xOf(i)} y={IH + 18} textAnchor="middle" fontSize={9} fontFamily="'Space Mono', monospace" fill="var(--text-muted)">
              {data[i]?.date?.slice(5)}
            </text>
          ))}
        </g>
      </svg>

      {showTooltip && (
        <div style={{
          position: 'absolute',
          left: tooltipLeft,
          top: tooltipTop,
          pointerEvents: 'none',
          background: 'var(--bg-elevated)',
          border: '1px solid var(--border-default)',
          borderRadius: 6,
          padding: '7px 10px',
          fontSize: 11,
          fontFamily: "'Space Mono', monospace",
          lineHeight: 1.7,
          whiteSpace: 'nowrap',
          zIndex: 10,
        }}>
          <div style={{ color: 'var(--text-muted)', marginBottom: 2, fontSize: 10 }}>
            {hPoint!.date}
          </div>
          {hTcgRaw != null && hTcgPct != null && (
            <div style={{ color: 'var(--gold)' }}>
              TCG: {fmtPrice(hTcgRaw)}{' '}
              <span style={{ color: 'var(--text-muted)' }}>({fmtPct(hTcgPct)})</span>
            </div>
          )}
          {hEbayRaw != null && hEbayPct != null && (
            <div style={{ color: 'var(--breakout)' }}>
              eBay: {fmtPrice(hEbayRaw)}{' '}
              <span style={{ color: 'var(--text-muted)' }}>({fmtPct(hEbayPct)})</span>
            </div>
          )}
        </div>
      )}
    </div>
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
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                <span style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>Price Trend (% change from first data point)</span>
                <div style={{ display: 'flex', gap: 12 }}>
                  <span style={{ fontSize: 11, color: 'var(--gold)' }}>— TCGPlayer</span>
                  <span style={{ fontSize: 11, color: 'var(--breakout)' }}>-- eBay sold</span>
                </div>
              </div>
              <NormalizedChart data={card.price_history} />
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
