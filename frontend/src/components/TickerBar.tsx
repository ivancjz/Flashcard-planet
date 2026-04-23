import { signalToMeta, formatDelta } from '../lib/utils'
import type { TickerItem } from '../types/api'

export default function TickerBar({ items }: { items: TickerItem[] }) {
  const doubled = [...items, ...items]
  return (
    <div className="ticker-bar">
      <div className="ticker-inner">
        {doubled.map((item, i) => {
          const up = item.price_delta_pct >= 0
          return (
            <span key={i} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--text-secondary)' }}>
              <span style={{ color: signalToMeta(item.signal).color, fontSize: 10 }}>●</span>
              <span style={{ fontFamily: 'var(--font-body)', fontWeight: 500 }}>{item.name}</span>
              <span className={up ? 'up' : 'down'}>{formatDelta(item.price_delta_pct)}</span>
            </span>
          )
        })}
      </div>
    </div>
  )
}
