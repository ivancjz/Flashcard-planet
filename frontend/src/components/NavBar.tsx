import { useEffect, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { getReadAlertIds } from '../lib/utils'
import { fetchAlerts } from '../api/api'
import { useWatchlist } from '../hooks/useWatchlist'

export default function NavBar() {
  const nav = useNavigate()
  const { pathname } = useLocation()
  const [unreadCount, setUnreadCount] = useState(0)
  const { count: watchlistCount } = useWatchlist()

  useEffect(() => {
    fetchAlerts({ limit: 50 }).then(r => {
      const readIds = getReadAlertIds()
      setUnreadCount(r.alerts.filter(a => !readIds.has(a.id)).length)
    }).catch(() => {})
  }, [pathname])

  const link = (path: string, label: string, extra?: React.ReactNode) => (
    <span
      className={`nav-link${pathname === path || pathname.startsWith(path + '/') ? ' active' : ''}`}
      onClick={() => nav(path)}
      style={{ position: 'relative' }}
    >
      {label}
      {extra}
    </span>
  )

  return (
    <nav className="nav">
      <div className="nav-logo" onClick={() => nav('/')}>
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
          <polygon points="10,1 12.9,7 19.5,7.6 14.8,11.8 16.2,18.2 10,15 3.8,18.2 5.2,11.8 0.5,7.6 7.1,7" fill="#f0b429" />
        </svg>
        Flashcard Planet
        <span className="nav-logo-sub">闪卡星球</span>
      </div>
      <div className="nav-links">
        {link('/market', '🎴 Market')}
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
            <span style={{
              position: 'absolute', top: 2, right: 2,
              background: '#ef4444', color: 'white',
              fontFamily: 'var(--font-mono)', fontSize: 9,
              padding: '1px 4px', borderRadius: 8,
              minWidth: 16, textAlign: 'center',
              lineHeight: '14px',
            }}>
              {unreadCount > 99 ? '99+' : unreadCount}
            </span>
          )
        )}
      </div>
    </nav>
  )
}
