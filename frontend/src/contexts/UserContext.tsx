import { createContext, useState, useContext } from 'react'
import type { ReactNode } from 'react'

export type Tier = 'free' | 'pro'

const STORAGE_KEY = 'fcp_dev_tier_override'

interface UserContextValue {
  tier: Tier
  setDevTier: (t: Tier | null) => void
}

const UserContext = createContext<UserContextValue>({
  tier: 'free',
  setDevTier: () => {},
})

export function UserProvider({ children }: { children: ReactNode }) {
  const [tier, setTier] = useState<Tier>(() => {
    const stored = localStorage.getItem(STORAGE_KEY)
    return stored === 'pro' ? 'pro' : 'free'
  })

  const setDevTier = (t: Tier | null) => {
    if (!import.meta.env.DEV) return
    if (t === null) localStorage.removeItem(STORAGE_KEY)
    else localStorage.setItem(STORAGE_KEY, t)
    setTier(t ?? 'free')
  }

  return <UserContext.Provider value={{ tier, setDevTier }}>{children}</UserContext.Provider>
}

export function useUser(): UserContextValue {
  return useContext(UserContext)
}
