import { useEffect, useState, useCallback } from 'react'
import NavBar from '../components/NavBar'
import SignalBadge from '../components/SignalBadge'
import { fetchAlerts } from '../api/api'
import { getReadAlertIds, markAlertRead, markAllAlertsRead, relativeTime, signalToMeta } from '../lib/utils'
import type { AlertEvent } from '../types/api'

type Filter = 'ALL' | 'UNREAD' | 'HIGH'

const SEVERITY_COLOR: Record<string, string> = {
  high: 'var(--breakout)',
  medium: 'var(--move)',
  low: 'var(--watch)',
}

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<AlertEvent[]>([])
  const [filter, setFilter] = useState<Filter>('ALL')
  const [readIds, setReadIds] = useState<Set<string>>(getReadAlertIds)

  const load = useCallback(() => {
    fetchAlerts({ filter }).then(r => setAlerts(r.alerts))
  }, [filter])

  useEffect(() => { load() }, [load])

  const handleRead = (id: string) => {
    markAlertRead(id)
    setReadIds(new Set([...readIds, id]))
  }

  const handleReadAll = () => {
    const ids = alerts.map(a => a.id)
    markAllAlertsRead(ids)
    setReadIds(new Set(ids))
  }

  const unreadCount = alerts.filter(a => !readIds.has(a.id)).length

  return (
    <div>
      <NavBar />
      <div className="page-content">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24 }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <h1 className="page-title">Price Alerts</h1>
              {unreadCount > 0 && (
                <span style={{ background: '#ef4444', color: 'white', fontSize: 11, fontFamily: 'var(--font-mono)', padding: '2px 8px', borderRadius: 10 }}>
                  {unreadCount} new
                </span>
              )}
            </div>
            <p className="page-subtitle">Signal change events</p>
          </div>
          {unreadCount > 0 && (
            <button className="btn btn-ghost btn-sm" onClick={handleReadAll}>Mark all read</button>
          )}
        </div>

        <div className="surface" style={{ padding: '10px 16px', marginBottom: 20, display: 'flex', alignItems: 'center', gap: 16 }}>
          <span className="pulse-dot" style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--breakout)', display: 'inline-block' }} />
          <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>Live signal events</span>
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
            {['Next ingest: 24h', 'Signal sweep: OK', 'eBay: active'].map(chip => (
              <span key={chip} style={{ fontSize: 11, background: 'var(--bg-elevated)', padding: '3px 10px', borderRadius: 4, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>{chip}</span>
            ))}
          </div>
        </div>

        <div style={{ display: 'flex', gap: 4, marginBottom: 16 }}>
          {(['ALL', 'UNREAD', 'HIGH'] as Filter[]).map(f => (
            <button key={f} className="btn btn-ghost btn-sm" onClick={() => setFilter(f)}
              style={filter === f ? { background: 'var(--bg-elevated)', color: 'var(--text-primary)', borderColor: 'var(--border-strong)' } : {}}>
              {f === 'ALL' ? 'All' : f === 'UNREAD' ? 'Unread' : 'High Priority'}
            </button>
          ))}
        </div>

        <div className="surface">
          {alerts.length === 0 && (
            <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>No alerts match this filter.</div>
          )}
          {alerts.map((alert, i) => {
            const isRead = readIds.has(alert.id)
            const meta = signalToMeta(alert.current_signal)
            const prevMeta = alert.previous_signal ? signalToMeta(alert.previous_signal) : null
            return (
              <div
                key={alert.id}
                onClick={() => handleRead(alert.id)}
                style={{
                  padding: '14px 20px',
                  borderBottom: i < alerts.length - 1 ? '1px solid var(--border-subtle)' : 'none',
                  display: 'flex', alignItems: 'center', gap: 14,
                  cursor: 'pointer',
                  borderLeft: isRead ? '3px solid transparent' : `3px solid ${SEVERITY_COLOR[alert.severity]}`,
                  background: isRead ? 'transparent' : `${SEVERITY_COLOR[alert.severity]}08`,
                  transition: 'background 0.15s',
                }}
              >
                <div style={{ width: 8, height: 8, borderRadius: '50%', flexShrink: 0, background: isRead ? 'transparent' : SEVERITY_COLOR[alert.severity] }} />
                <div style={{ fontSize: 18, flexShrink: 0 }}>
                  {alert.severity === 'high' ? '🔥' : alert.severity === 'medium' ? '📊' : '👁️'}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                    <span style={{ fontWeight: 600, fontSize: 14 }}>{alert.card_name}</span>
                    <SignalBadge signal={alert.current_signal} />
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                    {prevMeta ? (
                      <>
                        <span style={{ color: 'var(--text-muted)' }}>{prevMeta.label}</span>
                        {' → '}
                        <span style={{ color: meta.color, fontWeight: 600 }}>{meta.label}</span>
                      </>
                    ) : (
                      <span style={{ color: meta.color }}>{meta.label}</span>
                    )}
                    {alert.price_delta_pct != null && (
                      <span style={{ marginLeft: 8 }} className={alert.price_delta_pct >= 0 ? 'up' : 'down'}>
                        {alert.price_delta_pct >= 0 ? '+' : ''}{alert.price_delta_pct.toFixed(1)}%
                      </span>
                    )}
                  </div>
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', flexShrink: 0 }}>
                  {relativeTime(alert.created_at)}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
