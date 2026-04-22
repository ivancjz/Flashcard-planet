import { signalToMeta } from '../lib/utils'
import type { Signal } from '../types/api'

export default function SignalBadge({ signal }: { signal: Signal }) {
  const { label, badgeClass } = signalToMeta(signal)
  return <span className={`badge ${badgeClass}`}>{label}</span>
}
