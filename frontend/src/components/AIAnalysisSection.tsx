interface Props {
  aiAnalysis: string | null
}

export default function AIAnalysisSection({ aiAnalysis }: Props) {
  if (aiAnalysis) {
    return (
      <div className="surface" style={{ padding: 20 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 14 }}>🤖 AI Analysis</div>
          <span className="badge-gold" style={{ fontSize: 9 }}>PRO</span>
        </div>
        <p style={{ fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.65, margin: 0 }}>{aiAnalysis}</p>
      </div>
    )
  }

  return (
    <div className="surface" style={{ padding: 20 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 14 }}>🤖 AI Analysis</div>
        <span className="badge-gold" style={{ fontSize: 9 }}>PRO</span>
      </div>

      <div className="skeleton" style={{ height: 12, width: '90%', marginBottom: 8 }} />
      <div className="skeleton" style={{ height: 12, width: '70%', marginBottom: 8 }} />
      <div className="skeleton" style={{ height: 12, width: '80%', marginBottom: 20 }} />

      <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 14, margin: '0 0 14px' }}>
        AI-powered trend analysis is coming to Pro.
      </p>

      <a
        href="/#pricing"
        className="btn btn-gold-soft"
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 6,
          fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 12,
          textDecoration: 'none', borderRadius: 6, padding: '7px 16px',
          transition: 'opacity 0.15s',
        }}
      >
        Join the waitlist →
      </a>
    </div>
  )
}
