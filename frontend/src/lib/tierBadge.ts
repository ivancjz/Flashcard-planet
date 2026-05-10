import type { Tier } from '../contexts/UserContext'

export interface TierBadgeStyle {
  label: string
  color: string
  background: string
  borderColor: string
}

/**
 * Map a Tier to its NavBar badge style, or null if no badge should render.
 * Free tier returns null; pro and plus return distinct visual styles.
 *
 * Regression guard for Lesson 13: the original NavBar conditional only
 * checked tier === 'pro'; PLUS users got no badge. Switch over the full
 * Tier enum here — any future tier addition that misses this function
 * will return null (safe fail-safe) and be caught by the test.
 */
export function tierBadge(tier: Tier): TierBadgeStyle | null {
  if (tier === 'pro') {
    return {
      label: 'PRO',
      color: 'var(--gold)',
      background: 'var(--gold-glow)',
      borderColor: 'var(--border-gold-soft)',
    }
  }
  if (tier === 'plus') {
    return {
      label: 'PLUS',
      color: 'var(--plus)',
      background: 'var(--plus-glow)',
      borderColor: 'var(--border-plus-soft)',
    }
  }
  return null
}
