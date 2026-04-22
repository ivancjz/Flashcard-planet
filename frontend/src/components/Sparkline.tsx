interface SparklineProps {
  data: number[]
  width?: number
  height?: number
  color?: string
}

export default function Sparkline({ data, width = 80, height = 32, color }: SparklineProps) {
  if (data.length < 2) return <svg width={width} height={height} />

  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min || 1

  const xStep = width / (data.length - 1)
  const yOf = (v: number) => height - ((v - min) / range) * (height - 4) - 2
  const pts = data.map((v, i) => `${i * xStep},${yOf(v)}`).join(' ')
  const areaPath = `M 0,${height} L ${pts.split(' ').join(' L ')} L ${(data.length - 1) * xStep},${height} Z`

  const trend = data[data.length - 1] >= data[0]
  const stroke = color ?? (trend ? 'var(--breakout)' : '#ef4444')
  const lastX = (data.length - 1) * xStep
  const lastY = yOf(data[data.length - 1])

  return (
    <svg width={width} height={height} style={{ display: 'block' }}>
      <defs>
        <linearGradient id={`sg-${data.length}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity="0.3" />
          <stop offset="100%" stopColor={stroke} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={areaPath} fill={`url(#sg-${data.length})`} />
      <polyline points={pts} fill="none" stroke={stroke} strokeWidth="1.5" />
      <circle cx={lastX} cy={lastY} r={2.5} fill={stroke} />
    </svg>
  )
}
