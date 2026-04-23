// frontend/src/lib/utils.ts
import type { Signal } from '../types/api'

const READ_KEY = 'fp_read_alerts'

export function getReadAlertIds(): Set<string> {
  try {
    const raw = localStorage.getItem(READ_KEY)
    return raw ? new Set(JSON.parse(raw)) : new Set()
  } catch (_) { return new Set() }
}

export function markAlertRead(id: string): void {
  const ids = getReadAlertIds()
  ids.add(id)
  localStorage.setItem(READ_KEY, JSON.stringify([...ids]))
}

export function markAllAlertsRead(ids: string[]): void {
  localStorage.setItem(READ_KEY, JSON.stringify(ids))
}

export function typeToColor(cardType: string | null): string {
  const map: Record<string, string> = {
    Fire: '#ff6b35', Water: '#3b82f6', Grass: '#22c55e',
    Electric: '#ffcc00', Psychic: '#a855f7', Fighting: '#c2410c',
    Dark: '#4a0080', Dragon: '#1d4ed8', Steel: '#94a3b8',
    Fairy: '#ec4899', Normal: '#78716c', Colorless: '#87ceeb',
  }
  return map[cardType ?? ''] ?? '#6b7280'
}

export function relativeTime(isoString: string): string {
  const diff = Date.now() - new Date(isoString).getTime()
  const m = Math.floor(diff / 60000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

export function formatDelta(pct: number | null): string {
  if (pct == null) return '—'
  const sign = pct >= 0 ? '+' : ''
  const raw = pct.toFixed(1)
  const clean = raw.endsWith('.0') ? raw.slice(0, -2) : raw
  return `${sign}${clean}%`
}

export function signalToMeta(signal: Signal): { label: string; badgeClass: string; color: string; rowGlow: string } {
  switch (signal) {
    case 'BREAKOUT':          return { label: '▲ Breakout', badgeClass: 'badge-breakout', color: 'var(--breakout)', rowGlow: 'rgba(34,197,94,0.05)' }
    case 'MOVE':              return { label: '◆ Move',     badgeClass: 'badge-move',     color: 'var(--move)',     rowGlow: 'rgba(245,158,11,0.05)' }
    case 'WATCH':             return { label: '◆ Watch',    badgeClass: 'badge-watch',    color: 'var(--watch)',    rowGlow: 'rgba(251,146,60,0.05)' }
    case 'IDLE':              return { label: '— Idle',     badgeClass: 'badge-idle',     color: 'var(--idle)',     rowGlow: 'transparent' }
    case 'INSUFFICIENT_DATA': return { label: '· · ·',     badgeClass: 'badge-nodata',   color: 'var(--nodata)',   rowGlow: 'transparent' }
    default:                  return { label: '· · ·',     badgeClass: 'badge-nodata',   color: 'var(--nodata)',   rowGlow: 'transparent' }
  }
}
