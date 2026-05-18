import { Link, Outlet } from 'react-router-dom'

export default function PublicCallsLayout() {
  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-base)', color: 'var(--text-primary)' }}>
      <header style={{
        borderBottom: '1px solid var(--border-subtle)',
        padding: '0 24px',
        height: 52,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        background: 'var(--bg-surface)',
      }}>
        <span style={{
          fontFamily: 'Syne, sans-serif',
          fontWeight: 700,
          fontSize: 16,
          color: 'var(--gold)',
          letterSpacing: '-0.3px',
        }}>
          Flashcard Planet
        </span>
        <Link
          to="/market"
          style={{ fontSize: 12, fontFamily: "'Space Mono', monospace", color: 'var(--text-muted)' }}
        >
          ← Back to signals
        </Link>
      </header>
      <Outlet />
    </div>
  )
}
