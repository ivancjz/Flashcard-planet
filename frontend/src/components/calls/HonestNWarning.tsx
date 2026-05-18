interface Props {
  totalResolved: number
  threshold?: number
}

export default function HonestNWarning({ totalResolved, threshold = 30 }: Props) {
  return (
    <div style={{
      padding: '10px 14px',
      background: 'rgba(240,180,41,0.08)',
      border: '1px solid var(--border-gold-soft)',
      borderRadius: 'var(--radius-md)',
      fontSize: 12,
      fontFamily: "'Space Mono', monospace",
      color: 'var(--text-secondary)',
      lineHeight: 1.6,
    }}>
      n={totalResolved}. Statistical significance achieved at n≥{threshold}.{' '}
      {totalResolved < threshold
        ? 'Early calibration is directional only.'
        : 'Calibration is statistically meaningful.'}
    </div>
  )
}
