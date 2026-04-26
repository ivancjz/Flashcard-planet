import { splitIntoSegments } from '../lib/chartUtils'
import type { CardDetail } from '../types/api'

interface Props {
  cards: CardDetail[]
  colors: string[]
}

export default function ComparisonChart({ cards, colors }: Props) {
  const W = 760
  const H = 260
  const PAD = { top: 20, right: 90, bottom: 30, left: 52 }
  const IW = W - PAD.left - PAD.right
  const IH = H - PAD.top - PAD.bottom

  // Build normalized series — sort by date first to guarantee baseline = earliest
  const series = cards.map((card, i) => {
    const pts = card.price_history
      .filter(p => p.tcg_price != null && p.tcg_price > 0)
      .map(p => ({ date: p.date, price: p.tcg_price as number }))
      .sort((a, b) => a.date.localeCompare(b.date))
    if (pts.length < 2) return null
    const baseline = pts[0].price
    return {
      id: card.asset_id,
      name: card.name,
      color: colors[i],
      pts: pts.map(p => ({
        time: new Date(p.date).getTime(),
        pct: ((p.price - baseline) / baseline) * 100,
        date: p.date,
      })),
    }
  }).filter((s): s is NonNullable<typeof s> => s !== null)

  if (series.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)', fontSize: 13 }}>
        Not enough price history to chart.
      </div>
    )
  }

  // Shared time range across all series
  const allTimes = series.flatMap(s => s.pts.map(p => p.time))
  const timeMin = Math.min(...allTimes)
  const timeMax = Math.max(...allTimes)
  if (timeMax === timeMin) return null

  // Global Y range across all series
  const allPcts = series.flatMap(s => s.pts.map(p => p.pct))
  const rawMin = Math.min(...allPcts, 0)
  const rawMax = Math.max(...allPcts, 0)
  const pad = (rawMax - rawMin) * 0.1 || 2
  const yBot = rawMin - pad
  const yTop = rawMax + pad
  const yRange = yTop - yBot

  const xOf = (t: number) => PAD.left + ((t - timeMin) / (timeMax - timeMin)) * IW
  const yOf = (pct: number) => PAD.top + (1 - (pct - yBot) / yRange) * IH
  const zeroY = yOf(0)

  // Y ticks
  const rawStep = yRange / 4
  const mag = Math.pow(10, Math.floor(Math.log10(rawStep || 1)))
  const step = Math.ceil(rawStep / mag) * mag || 5
  const yTicks: number[] = []
  for (let t = Math.floor(yBot / step) * step; t <= yTop + step * 0.1; t += step) {
    if (t >= yBot - step * 0.1 && t <= yTop + step * 0.1) yTicks.push(Math.round(t * 10) / 10)
  }
  if (!yTicks.includes(0)) yTicks.push(0)

  // X date labels at 4 evenly-spaced time positions
  const xTickTimes = [0, 0.33, 0.66, 1].map(f => timeMin + f * (timeMax - timeMin))
  const fmtDateLabel = (t: number) => new Date(t).toISOString().slice(5, 10)

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: 'auto', display: 'block' }}>
      <g>
        {/* Zero baseline */}
        <line
          x1={PAD.left} x2={W - PAD.right} y1={zeroY} y2={zeroY}
          stroke="rgba(255,255,255,0.2)" strokeWidth={1}
        />

        {/* Y axis ticks */}
        {yTicks.map(t => {
          const y = yOf(t)
          return (
            <g key={t}>
              <line
                x1={PAD.left} x2={W - PAD.right} y1={y} y2={y}
                stroke="rgba(255,255,255,0.06)" strokeWidth={1} strokeDasharray="3 4"
              />
              <text
                x={PAD.left - 6} y={y + 4}
                fontSize={9} fontFamily="'Space Mono', monospace"
                fill="var(--text-muted)" textAnchor="end"
              >
                {t >= 0 ? `+${t.toFixed(0)}%` : `${t.toFixed(0)}%`}
              </text>
            </g>
          )
        })}

        {/* X axis date labels */}
        {xTickTimes.map((t, i) => (
          <text
            key={i} x={xOf(t)} y={H - 6}
            fontSize={9} fontFamily="'Space Mono', monospace"
            fill="var(--text-muted)" textAnchor="middle"
          >
            {fmtDateLabel(t)}
          </text>
        ))}

        {/* Series — segmented paths (solid / dashed gap bridges) */}
        {series.map(s => {
          const segments = splitIntoSegments(s.pts)
          return segments.map((seg, i) => {
            const d = seg.points.map((p, j) => `${j === 0 ? 'M' : 'L'} ${xOf(p.time)} ${yOf(p.pct)}`).join(' ')
            return (
              <path
                key={`${s.id}-${i}`}
                d={d}
                fill="none"
                stroke={s.color}
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeDasharray={seg.type === 'gap' ? '8,4' : undefined}
                opacity={seg.type === 'gap' ? 0.4 : 1}
              />
            )
          })
        })}

        {/* End-point dots */}
        {series.map(s => {
          const last = s.pts[s.pts.length - 1]
          return (
            <circle
              key={s.id}
              cx={xOf(last.time)} cy={yOf(last.pct)}
              r={3.5} fill={s.color} stroke="var(--bg-base)" strokeWidth={1.5}
            />
          )
        })}

        {/* Legend */}
        {series.map((s, i) => (
          <g key={s.id} transform={`translate(${W - PAD.right + 8}, ${PAD.top + i * 20})`}>
            <line x1={0} y1={5} x2={12} y2={5} stroke={s.color} strokeWidth={2} />
            <circle cx={6} cy={5} r={2.5} fill={s.color} />
            <text
              x={16} y={9}
              fontSize={10} fontFamily="'Syne', sans-serif"
              fill="var(--text-secondary)"
            >
              {s.name.length > 14 ? s.name.slice(0, 13) + '…' : s.name}
            </text>
          </g>
        ))}
      </g>
    </svg>
  )
}
