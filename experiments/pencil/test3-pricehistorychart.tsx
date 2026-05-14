// PriceHistoryChart — generated from Pencil design DlfGK (pencil-new.pen)
// Layout constants extracted from design; SVG logic follows existing codebase
// conventions from CardDetailPage.tsx / ComparisonChart.tsx / chartUtils.ts

import React from 'react'
import { splitIntoSegments } from '../../frontend/src/lib/chartUtils'
import type { ChartPoint } from '../../frontend/src/lib/chartUtils'

// ── Layout constants (from Pencil design DlfGK) ───────────────────────────────
const W   = 448
const H   = 280
const PAD = { top: 16, right: 80, bottom: 28, left: 52 }
const IW  = W - PAD.left - PAD.right  // 316
const IH  = H - PAD.top - PAD.bottom  // 236

// ── Gradient IDs ──────────────────────────────────────────────────────────────
const TCG_GRAD  = 'phc-tcg-grad'
const EBAY_GRAD = 'phc-ebay-grad'

// ── color-mix helper (Test 1 v2 convention — no rgba()) ───────────────────────
const cm = (token: string, pct: number) =>
  `color-mix(in srgb, ${token} ${pct}%, transparent)`

// ── Types ─────────────────────────────────────────────────────────────────────

interface PricePoint {
  time:  number  // ms timestamp
  price: number  // raw USD price
}

export interface PriceHistoryChartProps {
  tcgPoints?:  PricePoint[]
  ebayPoints?: PricePoint[]
}

// ── buildExtPoints — raw price series → normalised ChartPoint[] ───────────────
// Mirrors buildExtPoints in CardDetailPage.tsx (line 31). Signature differs:
// takes a pre-split {time,price}[] instead of PricePoint[]+priceKey because
// callers already own the split. Required transform before any SVG math.
function buildExtPoints(pts: PricePoint[]): ChartPoint[] {
  if (pts.length === 0) return []
  const baseline = pts[0].price
  return pts.map(p => ({
    time: p.time,
    pct:  ((p.price - baseline) / baseline) * 100,
  }))
}

// ── buildAreaPath — gradient fill path under a solid segment ──────────────────
// Verbatim from CardDetailPage.tsx:43–48. NOT renamed, NOT modified.
function buildAreaPath(
  points: ChartPoint[],
  xScale: (t: number) => number,
  yOf:    (p: number) => number,
  zeroY:  number,
): string {
  if (points.length < 2) return ''
  const xs = points.map(p => xScale(p.time))
  const ys = points.map(p => yOf(p.pct))
  return `M ${xs[0]},${zeroY} ${points.map((_, i) => `L ${xs[i]},${ys[i]}`).join(' ')} L ${xs[xs.length - 1]},${zeroY} Z`
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function PriceHistoryChart({
  tcgPoints  = [],
  ebayPoints = [],
}: PriceHistoryChartProps) {
  const tcgNorm  = buildExtPoints(tcgPoints)
  const ebayNorm = buildExtPoints(ebayPoints)
  const tcgValid  = tcgNorm.length  >= 2
  const ebayValid = ebayNorm.length >= 2

  if (!tcgValid && !ebayValid) {
    return (
      <div style={{
        width: W, height: H,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: 'var(--bg-base)',
        color: 'var(--text-secondary)',
        fontFamily: "'Space Mono', monospace",
        fontSize: 10,
      }}>
        No price history available
      </div>
    )
  }

  // Shared time range
  const allPts    = [...tcgNorm, ...ebayNorm]
  const timeMin   = Math.min(...allPts.map(p => p.time))
  const timeMax   = Math.max(...allPts.map(p => p.time))
  const timeRange = timeMax - timeMin || 1

  // xScale — time → inner-area x pixel (CardDetailPage.tsx:77)
  const xScale = (t: number) => ((t - timeMin) / timeRange) * IW

  // yOf / zeroY — pct → inner-area y pixel (CardDetailPage.tsx:83–84)
  const allPcts = allPts.map(p => p.pct)
  const minY    = Math.min(0, ...allPcts)
  const maxY    = Math.max(0, ...allPcts)
  const rangeY  = maxY - minY || 1
  const yOf     = (pct: number) => IH - ((pct - minY) / rangeY) * IH
  const zeroY   = Math.min(IH, Math.max(0, yOf(0)))

  // Y-axis ticks (CardDetailPage.tsx:86–91)
  const rawStep  = (maxY - minY) / 4
  const mag      = Math.pow(10, Math.floor(Math.log10(rawStep || 1)))
  const tickStep = Math.ceil(rawStep / mag) * mag || 5
  const tickSet  = new Set<number>([0])
  for (let t = Math.floor(minY / tickStep) * tickStep; t <= maxY + tickStep; t += tickStep) {
    tickSet.add(Math.round(t))
  }
  const sortedTicks = [...tickSet]
    .filter(t => t >= minY - tickStep * 0.1 && t <= maxY + tickStep * 0.1)
    .sort((a, b) => a - b)

  // Segments (splitIntoSegments from chartUtils.ts — splits on >24h gaps)
  const tcgSegs  = tcgValid  ? splitIntoSegments(tcgNorm)  : []
  const ebaySegs = ebayValid ? splitIntoSegments(ebayNorm) : []

  // X-axis date labels at start / mid / end (CardDetailPage.tsx:125–126)
  const dateLabelTimes = [timeMin, (timeMin + timeMax) / 2, timeMax]
  const fmtDate = (t: number) => new Date(t).toISOString().slice(5, 10)

  return (
    <svg
      width={W}
      height={H}
      viewBox={`0 0 ${W} ${H}`}
      style={{ display: 'block', background: 'var(--bg-base)' }}
    >
      <defs>
        {/* Gradient convention matches CardDetailPage.tsx:139–148.
            stopOpacity is the ONLY SVG numeric exempted from color-mix(). */}
        <linearGradient id={TCG_GRAD} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"   stopColor="var(--gold)"     stopOpacity="0.22" />
          <stop offset="100%" stopColor="var(--gold)"     stopOpacity="0"    />
        </linearGradient>
        <linearGradient id={EBAY_GRAD} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"   stopColor="var(--breakout)" stopOpacity="0.12" />
          <stop offset="100%" stopColor="var(--breakout)" stopOpacity="0"    />
        </linearGradient>
      </defs>

      {/* Inner chart area — all coordinates relative to PAD origin */}
      <g transform={`translate(${PAD.left},${PAD.top})`}>

        {/* Zero reference line (CardDetailPage.tsx:151) */}
        <line
          x1={0} y1={zeroY} x2={IW} y2={zeroY}
          stroke={cm('white', 18)} strokeWidth={1} strokeDasharray="4 3"
        />

        {/* Y-axis gridlines + labels */}
        {sortedTicks.map(t => (
          <g key={t}>
            <line
              x1={0} x2={IW} y1={yOf(t)} y2={yOf(t)}
              stroke={cm('white', 6)} strokeWidth={1}
            />
            <text
              x={-6} y={yOf(t) + 4}
              textAnchor="end" fontSize={9}
              fontFamily="'Space Mono', monospace"
              fill="var(--text-secondary)"
            >
              {t >= 0 ? `+${t}%` : `${t}%`}
            </text>
          </g>
        ))}

        {/* eBay area fills — solid segments only (CardDetailPage.tsx:163–166) */}
        {ebayValid && ebaySegs
          .filter(s => s.type === 'solid' && s.points.length >= 2)
          .map((seg, i) => (
            <path
              key={`ebay-area-${i}`}
              d={buildAreaPath(seg.points, xScale, yOf, zeroY)}
              fill={`url(#${EBAY_GRAD})`}
            />
          ))}

        {/* TCG area fills — solid segments only (CardDetailPage.tsx:187–189) */}
        {tcgValid && tcgSegs
          .filter(s => s.type === 'solid' && s.points.length >= 2)
          .map((seg, i) => (
            <path
              key={`tcg-area-${i}`}
              d={buildAreaPath(seg.points, xScale, yOf, zeroY)}
              fill={`url(#${TCG_GRAD})`}
            />
          ))}

        {/* eBay line — always dashed; gap segments use '8,4' (CardDetailPage.tsx:167–175) */}
        {ebayValid && ebaySegs.map((seg, i) => {
          const d = seg.points
            .map((p, j) => `${j === 0 ? 'M' : 'L'} ${xScale(p.time)},${yOf(p.pct)}`)
            .join(' ')
          return (
            <path
              key={`ebay-${i}`}
              d={d} fill="none"
              stroke="var(--breakout)"
              strokeWidth={1.5} strokeLinecap="round"
              strokeDasharray={seg.type === 'gap' ? '8,4' : '4 2'}
              opacity={seg.type === 'gap' ? 0.35 : 0.8}
            />
          )
        })}

        {/* TCG line — solid; gap segments dashed (CardDetailPage.tsx:190–198) */}
        {tcgValid && tcgSegs.map((seg, i) => {
          const d = seg.points
            .map((p, j) => `${j === 0 ? 'M' : 'L'} ${xScale(p.time)},${yOf(p.pct)}`)
            .join(' ')
          return (
            <path
              key={`tcg-${i}`}
              d={d} fill="none"
              stroke="var(--gold)"
              strokeWidth={2} strokeLinecap="round"
              strokeDasharray={seg.type === 'gap' ? '8,4' : undefined}
              opacity={seg.type === 'gap' ? 0.4 : 1}
            />
          )
        })}

        {/* End-point dots (CardDetailPage.tsx:178–180, 200–203) */}
        {tcgValid && (() => {
          const last = tcgNorm[tcgNorm.length - 1]
          return (
            <circle
              cx={xScale(last.time)} cy={yOf(last.pct)}
              r={4} fill="var(--gold)"
              stroke="var(--bg-base)" strokeWidth={2}
            />
          )
        })()}
        {ebayValid && (() => {
          const last = ebayNorm[ebayNorm.length - 1]
          return (
            <circle
              cx={xScale(last.time)} cy={yOf(last.pct)}
              r={3} fill="var(--breakout)"
              stroke="var(--bg-base)" strokeWidth={1.5}
            />
          )
        })()}

        {/* X-axis date labels (CardDetailPage.tsx:224–228) */}
        {dateLabelTimes.map((t, i) => (
          <text
            key={i}
            x={xScale(t)} y={IH + 18}
            textAnchor="middle" fontSize={9}
            fontFamily="'Space Mono', monospace"
            fill="var(--text-secondary)"
          >
            {fmtDate(t)}
          </text>
        ))}

      </g>

      {/* Legend — top-right corner (ComparisonChart.tsx:151–163) */}
      {([
        { label: 'TCG',  color: 'var(--gold)',     dashed: false, dy: 0  },
        { label: 'eBay', color: 'var(--breakout)', dashed: true,  dy: 20 },
      ] as const).map(({ label, color, dashed, dy }) => (
        <g key={label} transform={`translate(${W - PAD.right + 8},${PAD.top + dy})`}>
          <line
            x1={0} y1={5} x2={12} y2={5}
            stroke={color} strokeWidth={2}
            strokeDasharray={dashed ? '4 2' : undefined}
          />
          <circle cx={6} cy={5} r={2.5} fill={color} />
          <text
            x={16} y={9}
            fontSize={10} fontFamily="'Syne', sans-serif"
            fill="var(--text-secondary)"
          >
            {label}
          </text>
        </g>
      ))}
    </svg>
  )
}
