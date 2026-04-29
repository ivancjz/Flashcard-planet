import { useUser } from '../hooks/useUser'

interface Props {
  children: React.ReactNode
  feature: string
  locked?: boolean
  reason?: string
}

export default function ProGate({ children, feature, locked, reason }: Props) {
  const { tier } = useUser()
  const isLocked = locked ?? (tier !== 'pro')
  if (!isLocked) return <>{children}</>

  return (
    <div style={{ position: 'relative', display: 'inline-block', overflow: 'hidden' }}>
      <div style={{ filter: 'blur(2px)', pointerEvents: 'none', userSelect: 'none', opacity: 0.5 }}>
        {children}
      </div>
      <div
        style={{
          position: 'absolute', top: 0, right: 0, bottom: 0, left: 0,
          display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5,
          background: 'rgba(12,12,16,0.88)',
          borderRadius: 8, cursor: 'not-allowed',
        }}
        title={`${feature ?? 'Pro feature'} — ${reason ?? 'Available on Pro plan'}`}
      >
        <span style={{ fontSize: 12 }}>🔒</span>
        <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 11, color: 'var(--gold)', whiteSpace: 'nowrap' }}>
          Pro
        </span>
      </div>
    </div>
  )
}
