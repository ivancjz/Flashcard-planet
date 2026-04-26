import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import NavBar from '../components/NavBar'
import CardArt from '../components/CardArt'
import SignalBadge from '../components/SignalBadge'
import AIAnalysisSection from '../components/AIAnalysisSection'
import SignalTimeline from '../components/SignalTimeline'
import { fetchCard } from '../api/api'
import { signalToMeta, formatDelta } from '../lib/utils'
import { useWatchlist } from '../hooks/useWatchlist'
import { splitIntoSegments, findContinuousStart } from '../lib/chartUtils'
import type { CardDetail, PricePoint } from '../types/api'

const SIGNAL_DESCRIPTION: Record<string, string> = {
  BREAKOUT: 'Price has jumped significantly above baseline. High sales volume confirms buyer demand. Consider acting before the market adjusts.',
  MOVE: 'Price is shifting directionally with above-average volume. Momentum is building — watch closely.',
  WATCH: 'Early signals of price movement detected. Not yet confirmed — monitor the next 24–48h.',
  IDLE: 'No significant price movement. Market is stable for this card.',
  INSUFFICIENT_DATA: 'Not enough recent sales data to compute a reliable signal.',
}

interface ExtPoint {
  time: number
  pct: number
  raw: number
  date: string
}

function buildExtPoints(data: PricePoint[], priceKey: 'tcg_price' | 'ebay_price'): ExtPoint[] {
  const filtered = data.filter(d => d[priceKey] != null && (d[priceKey] as number) > 0)
  if (filtered.length === 0) return []
  const baseline = filtered[0][priceKey] as number
  return filtered.map(d => ({
    time: new Date(d.date).getTime(),
    raw: d[priceKey] as number,
    pct: ((d[priceKey] as number - baseline) / baseline) * 100,
    date: d.date,
  }))
}

function buildAreaPath(points: ExtPoint[], xScale: (t: number) => number, yOf: (p: number) => number, zeroY: number): string {
  if (points.length < 2) return ''
  const xs = points.map(p => xScale(p.time))
  const ys = points.map(p => yOf(p.pct))
  return `M ${xs[0]},${zeroY} ${points.map((_, i) => `L ${xs[i]},${ys[i]}`).join(' ')} L ${xs[xs.length - 1]},${zeroY} Z`
}

function NormalizedChart({ data }: { data: PricePoint[] }) {
  const [hoveredTime, setHoveredTime] = useState<number | null>(null)
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 })
  const containerRef = useRef<HTMLDivElement>(null)

  const W = 560, H = 180
  const PAD = { top: 16, right: 16, bottom: 28, left: 52 }
  const IW = W - PAD.left - PAD.right
  const IH = H - PAD.top - PAD.bottom

  const tcgPoints = buildExtPoints(data, 'tcg_price')
  const ebayPoints = buildExtPoints(data, 'ebay_price')
  const tcgValid = tcgPoints.length >= 2
  const ebayValid = ebayPoints.length >= 2

  if (!tcgValid && !ebayValid) {
    return (
      <div style={{ height: H, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: 13 }}>
        No price history available
      </div>
    )
  }

  const allPoints = [...tcgPoints, ...ebayPoints]
  const timeMin = Math.min(...allPoints.map(p => p.time))
  const timeMax = Math.max(...allPoints.map(p => p.time))
  const timeRange = timeMax - timeMin || 1
  const xScale = (t: number) => ((t - timeMin) / timeRange) * IW

  const allPcts = allPoints.map(p => p.pct)
  const minY = Math.min(0, ...allPcts)
  const maxY = Math.max(0, ...allPcts)
  const rangeY = maxY - minY || 1
  const yOf = (pct: number) => IH - ((pct - minY) / rangeY) * IH
  const zeroY = Math.min(IH, Math.max(0, yOf(0)))

  const rawStep = (maxY - minY) / 4
  const mag = Math.pow(10, Math.floor(Math.log10(rawStep || 1)))
  const tickStep = Math.ceil(rawStep / mag) * mag || 5
  const ticks = new Set<number>([0])
  for (let t = Math.floor(minY / tickStep) * tickStep; t <= maxY + tickStep; t += tickStep) ticks.add(Math.round(t))
  const sortedTicks = [...ticks].filter(t => t >= minY - tickStep * 0.1 && t <= maxY + tickStep * 0.1).sort((a, b) => a - b)

  const tcgSegments = splitIntoSegments(tcgPoints)
  const ebaySegments = splitIntoSegments(ebayPoints)

  function findNearest(points: ExtPoint[], time: number): ExtPoint | null {
    if (points.length === 0) return null
    return points.reduce((best, p) => Math.abs(p.time - time) < Math.abs(best.time - time) ? p : best)
  }

  function handleMouseMove(e: React.MouseEvent<HTMLDivElement>) {
    const container = containerRef.current
    if (!container) return
    const rect = container.getBoundingClientRect()
    const innerX = (e.clientX - rect.left) * (W / rect.width) - PAD.left
    setHoveredTime(timeMin + (innerX / IW) * timeRange)
    setMousePos({ x: e.clientX - rect.left, y: e.clientY - rect.top })
  }

  const hTcg = hoveredTime != null ? findNearest(tcgPoints, hoveredTime) : null
  const hEbay = hoveredTime != null ? findNearest(ebayPoints, hoveredTime) : null
  const showTooltip = hoveredTime != null && (hTcg != null || hEbay != null)

  // Use the nearest point's actual x-position for the vertical rule
  const ruleX = hTcg != null ? xScale(hTcg.time) : hEbay != null ? xScale(hEbay.time) : null

  const fmtPct = (p: number) => (p >= 0 ? `+${p.toFixed(1)}%` : `${p.toFixed(1)}%`)
  const fmtPrice = (p: number) => `$${p.toFixed(2)}`

  const flipLeft = mousePos.x > (containerRef.current?.clientWidth ?? W) * 0.6
  const tooltipLeft = flipLeft ? mousePos.x - 164 : mousePos.x + 14
  const tooltipTop = Math.max(4, mousePos.y - 56)

  // X date labels at first, middle, last of the overall time range
  const dateLabelTimes = [timeMin, (timeMin + timeMax) / 2, timeMax]
  const fmtDateLabel = (t: number) => new Date(t).toISOString().slice(5, 10)

  const continuousStart = findContinuousStart(tcgPoints.length > 0 ? tcgPoints : ebayPoints)

  return (
    <div>
      <div
        ref={containerRef}
        style={{ position: 'relative', cursor: 'crosshair' }}
        onMouseMove={handleMouseMove}
        onMouseLeave={() => setHoveredTime(null)}
      >
        <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: 'block' }}>
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

            {/* eBay area + segmented line */}
            {ebayValid && (
              <>
                <path d={buildAreaPath(ebayPoints, xScale, yOf, zeroY)} fill="url(#ebay-norm-grad)" />
                {ebaySegments.map((seg, i) => {
                  const d = seg.points.map((p, j) => `${j === 0 ? 'M' : 'L'} ${xScale(p.time)},${yOf(p.pct)}`).join(' ')
                  return (
                    <path key={`ebay-${i}`} d={d} fill="none" stroke="var(--breakout)"
                      strokeWidth={1.5} strokeLinecap="round"
                      strokeDasharray={seg.type === 'gap' ? '4,4' : '4 2'}
                      opacity={seg.type === 'gap' ? 0.35 : 0.8}
                    />
                  )
                })}
                {ebayPoints.length > 0 && (() => {
                  const last = ebayPoints[ebayPoints.length - 1]
                  return <circle cx={xScale(last.time)} cy={yOf(last.pct)} r={3} fill="var(--breakout)" stroke="var(--bg-base)" strokeWidth={1.5} />
                })()}
              </>
            )}

            {/* TCG area + segmented line */}
            {tcgValid && (
              <>
                <path d={buildAreaPath(tcgPoints, xScale, yOf, zeroY)} fill="url(#tcg-norm-grad)" />
                {tcgSegments.map((seg, i) => {
                  const d = seg.points.map((p, j) => `${j === 0 ? 'M' : 'L'} ${xScale(p.time)},${yOf(p.pct)}`).join(' ')
                  return (
                    <path key={`tcg-${i}`} d={d} fill="none" stroke="var(--gold)"
                      strokeWidth={2} strokeLinecap="round"
                      strokeDasharray={seg.type === 'gap' ? '4,4' : undefined}
                      opacity={seg.type === 'gap' ? 0.4 : 1}
                    />
                  )
                })}
                {tcgPoints.length > 0 && (() => {
                  const last = tcgPoints[tcgPoints.length - 1]
                  return <circle cx={xScale(last.time)} cy={yOf(last.pct)} r={4} fill="var(--gold)" stroke="var(--bg-base)" strokeWidth={2} />
                })()}
              </>
            )}

            {/* Hover: vertical rule */}
            {ruleX != null && (
              <line x1={ruleX} y1={0} x2={ruleX} y2={IH} stroke="rgba(255,255,255,0.18)" strokeWidth={1} />
            )}

            {/* Hover: data point circles */}
            {hEbay != null && ebayValid && (
              <circle cx={xScale(hEbay.time)} cy={yOf(hEbay.pct)} r={5} fill="var(--breakout)" stroke="var(--bg-base)" strokeWidth={2} />
            )}
            {hTcg != null && tcgValid && (
              <circle cx={xScale(hTcg.time)} cy={yOf(hTcg.pct)} r={5.5} fill="var(--gold)" stroke="var(--bg-base)" strokeWidth={2} />
            )}

            {/* Transparent hit area */}
            <rect x={0} y={0} width={IW} height={IH} fill="transparent" />

            {/* X-axis date labels */}
            {dateLabelTimes.map((t, i) => (
              <text key={i} x={xScale(t)} y={IH + 18} textAnchor="middle" fontSize={9} fontFamily="'Space Mono', monospace" fill="var(--text-muted)">
                {fmtDateLabel(t)}
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
              {hTcg?.date ?? hEbay?.date}
            </div>
            {hTcg != null && (
              <div style={{ color: 'var(--gold)' }}>
                TCG: {fmtPrice(hTcg.raw)}{' '}
                <span style={{ color: 'var(--text-muted)' }}>({fmtPct(hTcg.pct)})</span>
              </div>
            )}
            {hEbay != null && (
              <div style={{ color: 'var(--breakout)' }}>
                eBay: {fmtPrice(hEbay.raw)}{' '}
                <span style={{ color: 'var(--text-muted)' }}>({fmtPct(hEbay.pct)})</span>
              </div>
            )}
          </div>
        )}
      </div>

      {continuousStart && (
        <div style={{
          fontSize: 11,
          color: 'var(--text-muted)',
          fontFamily: 'var(--font-mono)',
          textAlign: 'right',
          marginTop: 8,
        }}>
          Continuous data since {continuousStart.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })}
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
  const { isWatched, toggle } = useWatchlist()

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
              <button
                className="btn btn-ghost"
                style={{ width: '100%', justifyContent: 'center' }}
                onClick={() => {
                  const result = toggle(card.asset_id)
                  if (!result.ok) {
                    if (result.reason === 'cap') alert('Watchlist is full (max 500 cards). Remove some to add more.')
                    else if (result.reason === 'storage') alert('Could not save watchlist. Storage may be disabled.')
                  }
                }}
              >
                {isWatched(card.asset_id) ? '⭐ Watching' : '☆ Add to Watchlist'}
              </button>
              <button
                className="btn btn-ghost"
                style={{ width: '100%', justifyContent: 'center' }}
                onClick={() => nav(`/compare?ids=${card.asset_id}`)}
              >
                📊 Compare with…
              </button>
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

            <div className="surface" style={{ padding: 20 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                <span style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 14 }}>Signal History</span>
                {(() => { const sh = card.signal_history ?? []; return (
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)' }}>
                    Past 30 days · {sh.length} change{sh.length !== 1 ? 's' : ''}
                  </span>
                )})()}
              </div>
              <SignalTimeline events={card.signal_history ?? []} />
            </div>

            <AIAnalysisSection aiAnalysis={card.ai_analysis ?? null} />
          </div>
        </div>
      </div>
    </div>
  )
}
