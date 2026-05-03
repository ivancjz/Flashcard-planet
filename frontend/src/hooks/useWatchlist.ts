import { useState, useEffect, useCallback } from 'react'
import {
  getWatchlist, isWatched, addToWatchlist, removeFromWatchlist, clearWatchlist,
} from '../lib/watchlist'
import { WATCHLIST_CHANGED_EVENT } from '../types/watchlist'
import type { WatchlistEntry } from '../types/watchlist'
import { useUser } from '../contexts/UserContext'

export function useWatchlist() {
  const [entries, setEntries] = useState<WatchlistEntry[]>(() => getWatchlist())
  const { tier } = useUser()

  useEffect(() => {
    const sync = () => setEntries(getWatchlist())
    window.addEventListener('storage', sync)
    window.addEventListener(WATCHLIST_CHANGED_EVENT, sync)
    return () => {
      window.removeEventListener('storage', sync)
      window.removeEventListener(WATCHLIST_CHANGED_EVENT, sync)
    }
  }, [])

  const toggle = useCallback((assetId: string): { ok: boolean; reason?: string } => {
    if (isWatched(assetId)) {
      removeFromWatchlist(assetId)
      return { ok: true }
    } else {
      const result = addToWatchlist(assetId, tier)
      return result.ok ? { ok: true } : { ok: false, reason: result.reason }
    }
  }, [tier])

  const remove = useCallback((assetId: string) => {
    removeFromWatchlist(assetId)
  }, [])

  const clear = useCallback(() => {
    clearWatchlist()
  }, [])

  return {
    entries,
    count: entries.length,
    isWatched: useCallback((id: string) => entries.some(e => e.asset_id === id), [entries]),
    toggle,
    remove,
    clear,
  }
}
