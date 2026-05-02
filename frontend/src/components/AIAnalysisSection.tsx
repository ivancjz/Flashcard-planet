interface Props {
  aiAnalysis: string | null
}

const PRO_BADGE: React.CSSProperties = {
  fontSize: 9, padding: '3px 8px',
  background: 'var(--gold-glow)',
  color: 'var(--gold)',
  border: '1px solid rgba(240,180,41,0.3)',
  borderRadius: 20,
  fontFamily: 'var(--font-mono)',
  fontWeight: 700,
  letterSpacing: '0.04em',
}

export default function AIAnalysisSection({ aiAnalysis }: Props) {
  if (aiAnalysis) {
    return (
      <div className="surface" style={{ padding: 20 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 14 }}>🤖 AI Analysis</div>
          <span style={PRO_BADGE}>PRO</span>
        </div>
        <p style={{ fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.65, margin: 0 }}>{aiAnalysis}</p>
      </div>
    )
  }

  return (
    <div className="surface" style={{ padding: 20 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 14 }}>🤖 AI Analysis</div>
        <span style={PRO_BADGE}>PRO</span>
      </div>

      <div className="skeleton" style={{ height: 12, width: '90%', marginBottom: 8 }} />
      <div className="skeleton" style={{ height: 12, width: '70%', marginBottom: 8 }} />
      <div className="skeleton" style={{ height: 12, width: '80%', marginBottom: 20 }} />

      <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 14, margin: '0 0 14px' }}>
        AI-powered trend analysis is coming to Pro.
      </p>

      <a
        href="/#pricing"
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 6,
          fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 12,
          color: 'var(--gold)', textDecoration: 'none',
          border: '1px solid rgba(240,180,41,0.3)', borderRadius: 6,
          padding: '7px 16px', background: 'var(--gold-glow)',
          transition: 'opacity 0.15s',
        }}
      >
        Join the waitlist →
      </a>
    </div>
  )
}
