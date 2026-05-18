import type { ReliabilityBin } from '../../types/calls'

interface Props {
  bins: ReliabilityBin[]
  totalResolved: number
}

export default function ReliabilityDiagram({ bins, totalResolved }: Props) {
  const W = 320
  const H = 320
  const PAD = { top: 24, right: 24, bottom: 48, left: 48 }
  const IW = W - PAD.left - PAD.right
  const IH = H - PAD.top - PAD.bottom

  const xOf = (p: number) => PAD.left + p * IW
  const yOf = (p: number) => PAD.top + (1 - p) * IH

  const ticks = [0, 0.25, 0.5, 0.75, 1.0]
  const isEmpty = totalResolved === 0
  const maxN = Math.max(...bins.map(b => b.n), 1)
  const dotRadius = (n: number) => n === 0 ? 0 : 4 + (n / maxN) * 10

  return (
    <div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        style={{ width: '100%', maxWidth: 320, height: 'auto', display: 'block' }}
        aria-label="Reliability diagram"
      >
        {/* Grid */}
        {ticks.map(t => (
          <g key={t}>
            <line x1={xOf(0)} x2={xOf(1)} y1={yOf(t)} y2={yOf(t)}
              stroke="rgba(255,255,255,0.06)" strokeWidth={1} />
            <line x1={xOf(t)} x2={xOf(t)} y1={yOf(0)} y2={yOf(1)}
              stroke="rgba(255,255,255,0.06)" strokeWidth={1} />
          </g>
        ))}

        {/* Perfect calibration diagonal — always visible */}
        <line x1={xOf(0)} y1={yOf(0)} x2={xOf(1)} y2={yOf(1)}
          stroke="rgba(255,255,255,0.20)" strokeWidth={1.5} strokeDasharray="5 4" />

        {/* Diagonal label */}
        <text
          x={xOf(0.72)} y={yOf(0.82)}
          fontSize={9} fontFamily="'Space Mono', monospace"
          fill="var(--text-muted)"
          transform={`rotate(-45, ${xOf(0.72)}, ${yOf(0.82)})`}
        >
          perfect calibration
        </text>

        {/* Empty state */}
        {isEmpty && (
          <text x={W / 2} y={H / 2 + 20}
            fontSize={11} fontFamily="'Space Mono', monospace"
            fill="var(--text-muted)" textAnchor="middle"
          >
            awaiting first resolution
          </text>
        )}

        {/* CI bars + dots */}
        {!isEmpty && bins.filter(b => b.n > 0).map((b, i) => {
          const cx = xOf((b.prob_bin_low + b.prob_bin_high) / 2)
          const cy = yOf(b.hit_rate)
          const r = dotRadius(b.n)
          return (
            <g key={i}>
              <line x1={cx} x2={cx} y1={yOf(b.ci_high)} y2={yOf(b.ci_low)}
                stroke="var(--gold-dim)" strokeWidth={1.5} />
              <circle cx={cx} cy={cy} r={r} fill="var(--gold)" opacity={0.85} />
            </g>
          )
        })}

        {/* Y axis labels */}
        {ticks.map(t => (
          <text key={t} x={PAD.left - 8} y={yOf(t) + 4}
            fontSize={9} fontFamily="'Space Mono', monospace"
            fill="var(--text-muted)" textAnchor="end"
          >
            {Math.round(t * 100)}%
          </text>
        ))}

        {/* X axis labels */}
        {ticks.map(t => (
          <text key={t} x={xOf(t)} y={H - PAD.bottom + 16}
            fontSize={9} fontFamily="'Space Mono', monospace"
            fill="var(--text-muted)" textAnchor="middle"
          >
            {Math.round(t * 100)}%
          </text>
        ))}

        {/* Axis titles */}
        <text x={W / 2} y={H - 2}
          fontSize={10} fontFamily="'Space Mono', monospace"
          fill="var(--text-secondary)" textAnchor="middle"
        >
          stated probability
        </text>
        <text x={10} y={H / 2}
          fontSize={10} fontFamily="'Space Mono', monospace"
          fill="var(--text-secondary)" textAnchor="middle"
          transform={`rotate(-90, 10, ${H / 2})`}
        >
          actual hit rate
        </text>
      </svg>
    </div>
  )
}
