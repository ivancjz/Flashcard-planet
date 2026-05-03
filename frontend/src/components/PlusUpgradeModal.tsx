interface Props {
  onClose: () => void
}

export default function PlusUpgradeModal({ onClose }: Props) {
  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 1000,
        background: 'rgba(0,0,0,0.65)', backdropFilter: 'blur(4px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 16,
      }}
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div
        className="surface"
        style={{
          maxWidth: 420, width: '100%', padding: 32,
          border: '1px solid rgba(240,180,41,0.3)',
          boxShadow: '0 0 48px rgba(240,180,41,0.12)',
        }}
      >
        <div style={{ fontSize: 28, marginBottom: 12 }}>⭐</div>
        <h2 style={{
          fontFamily: 'var(--font-display)', fontSize: 20, fontWeight: 700,
          marginBottom: 8, color: 'var(--text-primary)',
        }}>
          Upgrade to Plus for unlimited watchlist
        </h2>
        <p style={{ fontSize: 14, color: 'var(--text-secondary)', marginBottom: 24, lineHeight: 1.6 }}>
          $9.99/mo. Cross-game watchlist + daily digest + smart alerts. Free tier is limited to 5 cards.
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <a
            href="/#plus"
            style={{
              display: 'block', textAlign: 'center', padding: '11px 20px',
              borderRadius: 6, fontFamily: 'var(--font-display)', fontWeight: 700,
              fontSize: 14, textDecoration: 'none',
              background: 'var(--gold-glow)', border: '1px solid rgba(240,180,41,0.4)',
              color: 'var(--gold)',
            }}
          >
            View Plus plans →
          </a>
          <button
            onClick={onClose}
            className="btn btn-ghost"
            style={{ width: '100%', justifyContent: 'center' }}
          >
            Maybe later
          </button>
        </div>
      </div>
    </div>
  )
}
