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
      .sort((a, b) => a.date.localeCompare(b.date))   // ascending date
    if (pts.length < 2) return null
    const baseline = pts[0].price
    return {
      id: card.asset_id,
      name: card.name,
      color: colors[i],
      pts: pts.map(p => ({ date: p.date, pct: ((p.price - baseline) / baseline) * 100 })),
    }
  }).filter((s): s is NonNullable<typeof s> => s !== null)

  if (series.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)', fontSize: 13 }}>
        Not enough price history to chart.
      </div>
    )
  }

  // Union all date strings, sorted
  const allDates = Array.from(new Set(series.flatMap(s => s.pts.map(p => p.date)))).sort()
  const nDates = allDates.length
  if (nDates < 2) return null

  const dateIndex = new Map(allDates.map((d, i) => [d, i]))

  // Global Y range across all series
  const allPcts = series.flatMap(s => s.pts.map(p => p.pct))
  const rawMin = Math.min(...allPcts, 0)
  const rawMax = Math.max(...allPcts, 0)
  const pad = (rawMax - rawMin) * 0.1 || 2   // || 2: protect flat-line case
  const yBot = rawMin - pad
  const yTop = rawMax + pad
  const yRange = yTop - yBot

  const xOf = (i: number) => PAD.left + (i / (nDates - 1)) * IW
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

  // X date labels (4 evenly-spaced)
  const xTickIndices = [0, Math.floor(nDates * 0.33), Math.floor(nDates * 0.66), nDates - 1]

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
        {xTickIndices.map(i => (
          <text
            key={i} x={xOf(i)} y={H - 6}
            fontSize={9} fontFamily="'Space Mono', monospace"
            fill="var(--text-muted)" textAnchor="middle"
          >
            {allDates[i]?.slice(5)}
          </text>
        ))}

        {/* Series paths — M on first point, L thereafter; pen resets on gap */}
        {series.map(s => {
          const ptMap = new Map(s.pts.map(p => [p.date, p.pct]))
          let d = ''
          let pen = false
          allDates.forEach((date, i) => {
            const pct = ptMap.get(date)
            if (pct != null) {
              d += `${pen ? 'L' : 'M'} ${xOf(i)} ${yOf(pct)} `
              pen = true
            } else {
              pen = false
            }
          })
          return (
            <path
              key={s.id}
              d={d}
              fill="none"
              stroke={s.color}
              strokeWidth={2}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          )
        })}

        {/* End-point dots */}
        {series.map(s => {
          const last = s.pts[s.pts.length - 1]
          const i = dateIndex.get(last.date) ?? 0
          return (
            <circle
              key={s.id}
              cx={xOf(i)} cy={yOf(last.pct)}
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
