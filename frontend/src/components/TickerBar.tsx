import { useEffect, useState } from 'react'
import { signalToMeta, formatDelta } from '../lib/utils'
import type { TickerItem } from '../types/api'

function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(() =>
    typeof window !== 'undefined'
      ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
      : false
  )

  useEffect(() => {
    const mql = window.matchMedia('(prefers-reduced-motion: reduce)')
    const handler = (e: MediaQueryListEvent) => setReduced(e.matches)
    mql.addEventListener('change', handler)
    return () => mql.removeEventListener('change', handler)
  }, [])

  return reduced
}

function TickerItem({ item }: { item: TickerItem }) {
  const up = item.price_delta_pct >= 0
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--text-secondary)' }}>
      <span style={{ color: signalToMeta(item.signal).color, fontSize: 10 }}>●</span>
      <span style={{ fontFamily: 'var(--font-body)', fontWeight: 500 }}>{item.name}</span>
      <span className={up ? 'up' : 'down'}>{formatDelta(item.price_delta_pct)}</span>
    </span>
  )
}

export default function TickerBar({ items }: { items: TickerItem[] }) {
  const reducedMotion = useReducedMotion()

  if (reducedMotion) {
    // Static fallback: show first 8 items in a non-scrolling row
    return (
      <div className="ticker-bar" style={{ overflow: 'hidden' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 40, padding: '0 40px' }}>
          {items.slice(0, 8).map((item, i) => (
            <TickerItem key={i} item={item} />
          ))}
        </div>
      </div>
    )
  }

  const doubled = [...items, ...items]
  return (
    <div className="ticker-bar">
      <div className="ticker-inner">
        {doubled.map((item, i) => (
          <TickerItem key={i} item={item} />
        ))}
      </div>
    </div>
  )
}
