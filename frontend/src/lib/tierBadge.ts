import type { Tier } from '../contexts/UserContext'

export interface TierBadge {
  label: string
  className: string
}

/**
 * Map a Tier to its NavBar badge, or null if no badge should render.
 * Free tier returns null; pro and plus return distinct CSS class badges.
 *
 * Regression guard for Lesson 13: switch over the full Tier enum so any
 * future tier addition that misses this function returns null (safe default)
 * and is caught by the test.
 */
export function tierBadge(tier: Tier): TierBadge | null {
  if (tier === 'pro') {
    return { label: 'PRO', className: 'badge-pro' }
  }
  if (tier === 'plus') {
    return { label: 'PLUS', className: 'badge-plus' }
  }
  return null
}
