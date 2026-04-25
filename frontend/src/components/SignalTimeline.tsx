import type { SignalHistoryEvent } from '../types/api'
import { signalToMeta, relativeTime } from '../lib/utils'

interface Props {
  events: SignalHistoryEvent[]
}

export default function SignalTimeline({ events }: Props) {
  if (events.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: '24px 16px', color: 'var(--text-muted)', fontSize: 13 }}>
        No signal changes in the past 30 days.
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
      {events.map((event, i) => (
        <TimelineRow
          key={event.id}
          event={event}
          isLast={i === events.length - 1}
        />
      ))}
    </div>
  )
}

function TimelineRow({ event, isLast }: { event: SignalHistoryEvent; isLast: boolean }) {
  const fromMeta = event.previous_label ? signalToMeta(event.previous_label) : null
  const toMeta = signalToMeta(event.current_label)
  const accentColor = toMeta.color

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: '24px 1fr auto',
      gap: 14,
      padding: '12px 0',
      borderBottom: isLast ? 'none' : '1px solid var(--border-subtle)',
      alignItems: 'flex-start',
    }}>
      {/* Timeline rail + dot */}
      <div style={{ position: 'relative', width: 24, alignSelf: 'stretch' }}>
        {!isLast && (
          <div style={{
            position: 'absolute', left: 11, top: 14,
            width: 2, bottom: -12,
            background: 'var(--border-default)',
          }} />
        )}
        <div style={{
          position: 'absolute', left: 8, top: 4,
          width: 8, height: 8, borderRadius: '50%',
          background: accentColor,
          border: '2px solid var(--bg-base)',
        }} />
      </div>

      {/* Transition + price */}
      <div style={{ minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4, flexWrap: 'wrap' }}>
          {fromMeta ? (
            <span className={`badge ${fromMeta.badgeClass}`} style={{ opacity: 0.6 }}>
              {fromMeta.label}
            </span>
          ) : (
            <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>—</span>
          )}
          <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>→</span>
          <span className={`badge ${toMeta.badgeClass}`}>{toMeta.label}</span>
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-secondary)', display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          {event.price_at_event != null && (
            <span>at <strong style={{ color: 'var(--text-primary)' }}>${event.price_at_event.toFixed(2)}</strong></span>
          )}
          {event.price_delta_pct != null && (
            <span className={event.price_delta_pct >= 0 ? 'up' : 'down'}>
              {event.price_delta_pct >= 0 ? '+' : ''}{event.price_delta_pct.toFixed(1)}%
            </span>
          )}
        </div>
      </div>

      {/* Relative time */}
      <div style={{
        fontFamily: 'var(--font-mono)',
        fontSize: 11,
        color: 'var(--text-muted)',
        textAlign: 'right',
        whiteSpace: 'nowrap',
        paddingTop: 4,
      }}>
        {relativeTime(event.computed_at)}
      </div>
    </div>
  )
}
