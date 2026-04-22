import { useNavigate, useLocation } from 'react-router-dom'
import { getReadAlertIds } from '../lib/utils'
import { MOCK_ALERTS } from '../lib/mockData'

export default function NavBar() {
  const nav = useNavigate()
  const { pathname } = useLocation()
  const readIds = getReadAlertIds()
  const hasUnread = MOCK_ALERTS.some(a => !readIds.has(a.id))

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
        {link('/market', 'Market')}
        {link('/alerts', 'Alerts',
          hasUnread && (
            <span style={{ position: 'absolute', top: 4, right: 4, width: 6, height: 6, borderRadius: '50%', background: '#ef4444' }} />
          )
        )}
      </div>
    </nav>
  )
}
