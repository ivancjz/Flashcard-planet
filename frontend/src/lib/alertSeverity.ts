import type { AlertEvent } from '../types/api'

export type Severity = AlertEvent['severity']  // 'high' | 'medium' | 'low'

export interface AlertSeverityStyles {
  /** Solid colour — used for border-left accent and the unread-status dot. */
  accent: string
  /** Low-alpha row wash — used as background-color on unread rows. */
  tint: string
}

/**
 * Map an alert severity to its visual treatment.
 *
 * Decoupled from the signal palette (--breakout, --move, --watch) per the
 * 2026-05-07 audit decision: alert severity and signal label are distinct
 * concepts, and reusing the signal greens / oranges for alerts produces
 * "high-severity reads as good-news colour" semantic clash.
 *
 * Regression guard: the previous AlertsPage implementation concatenated
 * `var(--breakout)` with `08` at runtime to produce a row tint, which
 * is invalid CSS — the background declaration was silently dropped.
 * Returning fully-formed token references here makes that class of bug
 * structurally impossible.
 */
export function alertSeverityStyles(severity: Severity): AlertSeverityStyles {
  if (severity === 'high') {
    return { accent: 'var(--severity-high)', tint: 'var(--tint-danger)' }
  }
  if (severity === 'medium') {
    return { accent: 'var(--severity-med)', tint: 'var(--tint-severity-med)' }
  }
  return { accent: 'var(--severity-low)', tint: 'var(--tint-severity-low)' }
}
