import { useEffect, useRef, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { getReadAlertIds } from '../lib/utils'
import { tierBadge } from '../lib/tierBadge'
import { fetchAlerts } from '../api/api'
import { useWatchlist } from '../hooks/useWatchlist'
import { useUser } from '../hooks/useUser'

// Makes a non-<a> element that navigates keyboard-accessible.
// role="link" + Enter: WCAG 4.1.2 (correct role for navigation) + WCAG 2.1.1.
// Space is intentionally excluded — links activate on Enter only per ARIA spec.
const activate = (handler: () => void) => ({
  role: 'link' as const,
  tabIndex: 0,
  onClick: handler,
  onKeyDown: (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      handler()
    }
  },
})

function truncateEmail(email: string): string {
  if (email.length <= 24) return email
  const [local, domain] = email.split('@')
  if (!domain) return email.slice(0, 22) + '…'
  return local.slice(0, 8) + '…@' + domain
}

export default function NavBar() {
  const nav = useNavigate()
  const { pathname } = useLocation()
  const [unreadCount, setUnreadCount] = useState(0)
  const { count: watchlistCount } = useWatchlist()
  const { email, tier, loading } = useUser()
  const badge = tierBadge(tier)
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    fetchAlerts({ limit: 50 }).then(r => {
      const readIds = getReadAlertIds()
      setUnreadCount(r.alerts.filter(a => !readIds.has(a.id)).length)
    }).catch(() => {})
  }, [pathname])

  // Close dropdown on click-outside
  useEffect(() => {
    if (!menuOpen) return
    function handleClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [menuOpen])

  // Close dropdown on Escape
  useEffect(() => {
    if (!menuOpen) return
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') setMenuOpen(false)
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [menuOpen])

  const link = (path: string, label: string, extra?: React.ReactNode) => (
    <span
      className={`nav-link${pathname === path || pathname.startsWith(path + '/') ? ' active' : ''}`}
      {...activate(() => nav(path))}
      style={{ position: 'relative' }}
    >
      {label}
      {extra}
    </span>
  )

  return (
    <nav className="nav">
      <div className="nav-logo" {...activate(() => nav('/'))}>
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
          <polygon points="10,1 12.9,7 19.5,7.6 14.8,11.8 16.2,18.2 10,15 3.8,18.2 5.2,11.8 0.5,7.6 7.1,7" fill="#f0b429" />
        </svg>
        Flashcard Planet
        <span className="nav-logo-sub">闪卡星球</span>
      </div>

      {/* Primary nav links: Market · Sealed · Watchlist · Alerts */}
      <div className="nav-links" style={{ justifyContent: 'flex-start' }}>
        {link('/market', '🎴 Market')}
        {link('/reports', 'Daily')}
        {link('/sealed', '📦 Sealed')}
        {link('/watchlist', '⭐ Watchlist',
          watchlistCount > 0 && (
            <span style={{
              marginLeft: 6,
              background: 'var(--gold)',
              color: 'var(--text-inverse, #0c0c10)',
              fontSize: 10, fontWeight: 700,
              padding: '1px 6px', borderRadius: 10,
              lineHeight: '16px',
            }}>
              {watchlistCount}
            </span>
          )
        )}
        {link('/alerts', 'Alerts',
          unreadCount > 0 && (
            <span
              aria-live="polite"
              aria-label={`${unreadCount} unread alert${unreadCount === 1 ? '' : 's'}`}
              style={{
                position: 'absolute', top: 2, right: 2,
                background: '#ef4444', color: 'white',
                fontFamily: 'var(--font-mono)', fontSize: 9,
                padding: '1px 4px', borderRadius: 8,
                minWidth: 16, textAlign: 'center',
                lineHeight: '14px',
              }}
            >
              {unreadCount > 99 ? '99+' : unreadCount}
            </span>
          )
        )}
      </div>

      {/* Right side: PRO badge · Avatar dropdown (sits right because nav-links has flex:1) */}
      <div style={{ flexShrink: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
        {/* Auth state — show nothing while loading */}
        {!loading && (
          email ? (
            <>
              {/* PRO/PLUS tier badge */}
              {badge && (
                <span className={badge.className}>{badge.label}</span>
              )}

              {/* Upgrade CTA for free-tier users */}
              {tier === 'free' && (
                <a
                  href="/pricing"
                  className="btn btn-gold-soft btn-sm"
                  style={{ textDecoration: 'none', padding: '4px 12px', fontSize: 12 }}
                >
                  Upgrade
                </a>
              )}

              {/* Avatar / email dropdown */}
              <div ref={menuRef} style={{ position: 'relative' }}>
                <button
                  onClick={() => setMenuOpen(prev => !prev)}
                  aria-haspopup="true"
                  aria-expanded={menuOpen}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 6,
                    padding: '5px 10px', borderRadius: 6,
                    background: menuOpen ? 'var(--bg-elevated)' : 'transparent',
                    color: 'var(--text-secondary)', cursor: 'pointer',
                    fontSize: 12, border: '1px solid transparent',
                    transition: 'background 0.15s, border-color 0.15s',
                  }}
                >
                  <span>{truncateEmail(email)}</span>
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="none" style={{ transition: 'transform 0.15s', transform: menuOpen ? 'rotate(180deg)' : 'rotate(0deg)' }}>
                    <path d="M2 4l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </button>

                {menuOpen && (
                  <div
                    role="menu"
                    style={{
                      position: 'absolute', top: 'calc(100% + 6px)', right: 0,
                      background: 'var(--bg-elevated)',
                      border: '1px solid var(--border-default)',
                      borderRadius: 8, minWidth: 192, padding: 6,
                      boxShadow: '0 12px 32px rgba(0,0,0,0.6)',
                      zIndex: 50,
                    }}
                  >
                    <div style={{ padding: '8px 12px 6px', fontSize: 11, color: 'var(--text-muted)', borderBottom: '1px solid var(--border-subtle)', marginBottom: 4 }}>
                      {email}
                    </div>
                    <button
                      role="menuitem"
                      onClick={() => { setMenuOpen(false); nav('/account') }}
                      style={{
                        width: '100%', textAlign: 'left',
                        padding: '7px 12px', borderRadius: 4, fontSize: 13,
                        color: 'var(--text-secondary)', cursor: 'pointer',
                        background: 'transparent',
                        transition: 'background 0.1s, color 0.1s',
                      }}
                      onMouseEnter={e => { (e.target as HTMLElement).style.background = 'var(--bg-floating)'; (e.target as HTMLElement).style.color = 'var(--text-primary)' }}
                      onMouseLeave={e => { (e.target as HTMLElement).style.background = 'transparent'; (e.target as HTMLElement).style.color = 'var(--text-secondary)' }}
                    >
                      Account
                    </button>
                    <button
                      role="menuitem"
                      onClick={() => { window.location.href = '/auth/logout' }}
                      style={{
                        width: '100%', textAlign: 'left',
                        padding: '7px 12px', borderRadius: 4, fontSize: 13,
                        color: 'var(--text-secondary)', cursor: 'pointer',
                        background: 'transparent',
                        transition: 'background 0.1s, color 0.1s',
                      }}
                      onMouseEnter={e => { (e.target as HTMLElement).style.background = 'var(--bg-floating)'; (e.target as HTMLElement).style.color = 'var(--text-primary)' }}
                      onMouseLeave={e => { (e.target as HTMLElement).style.background = 'transparent'; (e.target as HTMLElement).style.color = 'var(--text-secondary)' }}
                    >
                      Sign out
                    </button>
                  </div>
                )}
              </div>
            </>
          ) : (
            <span
              className="nav-link"
              {...activate(() => { window.location.href = '/login' })}
              style={{ fontSize: 13 }}
            >
              Sign in
            </span>
          )
        )}
      </div>
    </nav>
  )
}
