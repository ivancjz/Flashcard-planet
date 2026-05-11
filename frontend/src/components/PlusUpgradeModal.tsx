import { useFocusTrap } from '../hooks/useFocusTrap'

interface Props {
  onClose: () => void
}

export default function PlusUpgradeModal({ onClose }: Props) {
  // Component only renders when shown — open is always true at mount
  const trapRef = useFocusTrap<HTMLDivElement>(true, onClose)
  return (
    <div
      className="modal-backdrop"
      style={{
        zIndex: 1000,
        backdropFilter: 'blur(4px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 'var(--space-4)',
      }}
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div
        ref={trapRef}
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="plus-upgrade-title"
        style={{
          maxWidth: 420,
          borderRadius: 'var(--radius-lg)',     // class default --radius-md (8px); preserve 12px
          background: 'var(--bg-surface)',       // class default --bg-elevated; preserve surface
          border: '1px solid var(--border-gold-soft)',
          boxShadow: 'var(--shadow-glow-gold)',
          padding: 32,
        }}
      >
        <div style={{ fontSize: 28, marginBottom: 12 }}>⭐</div>
        <h2
          id="plus-upgrade-title"
          style={{
            fontFamily: 'var(--font-display)', fontSize: 20, fontWeight: 700,
            marginBottom: 8, color: 'var(--text-primary)', margin: '0 0 8px',
          }}
        >
          Upgrade to Plus for unlimited watchlist
        </h2>
        <p style={{ fontSize: 14, color: 'var(--text-secondary)', marginBottom: 24, lineHeight: 1.6 }}>
          $9.99/mo. Cross-game watchlist + daily digest + smart alerts. Free tier is limited to 5 cards.
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <a
            href="/#plus"
            className="btn btn-gold-soft"
            style={{
              display: 'block', textAlign: 'center', padding: '11px 20px',
              borderRadius: 6, fontFamily: 'var(--font-display)', fontWeight: 700,
              fontSize: 14, textDecoration: 'none',
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
