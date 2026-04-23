interface Props {
  children: React.ReactNode
  locked?: boolean
  feature?: string
  reason?: string
}

export default function ProGate({ children, locked = false, feature, reason }: Props) {
  if (!locked) return <>{children}</>

  return (
    <div style={{ position: 'relative', display: 'inline-block' }}>
      <div style={{ filter: 'blur(2px)', pointerEvents: 'none', userSelect: 'none', opacity: 0.5 }}>
        {children}
      </div>
      <div style={{
        position: 'absolute', inset: 0,
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
        background: 'rgba(12,12,16,0.75)',
        borderRadius: 8, gap: 4, padding: '6px 10px',
      }}>
        <div style={{ fontSize: 14 }}>🔒</div>
        <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 11, color: 'var(--text-primary)', textAlign: 'center', whiteSpace: 'nowrap' }}>
          {feature ?? 'Pro feature'}
        </div>
        <div style={{ fontSize: 10, color: 'var(--text-muted)', textAlign: 'center', whiteSpace: 'nowrap' }}>
          {reason ?? 'Available on Pro plan'}
        </div>
        <a
          href="mailto:hello@flashcardplanet.com"
          onClick={e => e.stopPropagation()}
          style={{
            fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 10,
            color: 'var(--gold)', textDecoration: 'none',
            border: '1px solid rgba(240,180,41,0.3)', borderRadius: 4,
            padding: '3px 8px', background: 'var(--gold-glow)',
            marginTop: 2, whiteSpace: 'nowrap',
          }}
        >
          Get Pro →
        </a>
      </div>
    </div>
  )
}
