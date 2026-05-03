import { createContext, useState, useEffect, useContext } from 'react'
import type { ReactNode } from 'react'
import { setCachedTier } from '../api/api'

export type Tier = 'free' | 'plus' | 'pro'

const STORAGE_KEY = 'fcp_dev_tier_override'

// Exported for testing. Maps any raw tier string to a typed Tier value.
// Any unrecognised value coerces to 'free' — fail-safe for future enum additions.
export function parseTier(raw: string | null | undefined): Tier {
  if (raw === 'pro' || raw === 'plus') return raw
  return 'free'
}

interface UserContextValue {
  tier: Tier
  email: string | null
  loading: boolean
  setDevTier: (t: Tier | null) => void   // dev-only override
}

const UserContext = createContext<UserContextValue>({
  tier: 'free',
  email: null,
  loading: true,
  setDevTier: () => {},
})

export function UserProvider({ children }: { children: ReactNode }) {
  const [tier, setTier] = useState<Tier>('free')
  const [email, setEmail] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Fetch real tier from server session
    fetch('/api/v1/auth/me')
      .then(r => {
        if (!r.ok) throw new Error('not_authenticated')
        return r.json()
      })
      .then(data => {
        setEmail(data.email ?? null)
        const t = parseTier(data.tier)
        setTier(t)
        setCachedTier(t)  // keep X-Dev-Tier header in sync
      })
      .catch(() => {
        // Not logged in — fall back to localStorage dev override (dev/testing only)
        const stored = localStorage.getItem(STORAGE_KEY)
        const t = parseTier(stored)
        setTier(t)
        setCachedTier(t)
      })
      .finally(() => setLoading(false))
  }, [])

  const setDevTier = (t: Tier | null) => {
    // Only usable when not authenticated (for local testing)
    if (email) return  // real session takes precedence
    if (t === null) localStorage.removeItem(STORAGE_KEY)
    else localStorage.setItem(STORAGE_KEY, t)
    setTier(t ?? 'free')
  }

  return (
    <UserContext.Provider value={{ tier, email, loading, setDevTier }}>
      {children}
    </UserContext.Provider>
  )
}

export function useUser(): UserContextValue {
  return useContext(UserContext)
}
