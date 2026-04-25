import type { WatchlistEntry, WatchlistStorage } from '../types/watchlist'
import { WATCHLIST_CHANGED_EVENT } from '../types/watchlist'

const KEY = 'fp_watchlist'
const MAX_ENTRIES = 500
const CURRENT_VERSION = 1

function readRaw(): WatchlistStorage {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return { version: CURRENT_VERSION, entries: [] }

    const parsed = JSON.parse(raw)

    // Legacy format: string[] of asset_ids
    if (Array.isArray(parsed)) {
      const now = new Date().toISOString()
      return {
        version: CURRENT_VERSION,
        entries: parsed
          .filter((id): id is string => typeof id === 'string' && id.length > 0)
          .map(asset_id => ({ asset_id, added_at: now })),
      }
    }

    // Current format
    if (parsed && typeof parsed === 'object' && Array.isArray(parsed.entries)) {
      const entries = parsed.entries.filter(
        (e: unknown) => e && typeof (e as WatchlistEntry).asset_id === 'string' && typeof (e as WatchlistEntry).added_at === 'string'
      ) as WatchlistEntry[]
      return { version: CURRENT_VERSION, entries }
    }

    return { version: CURRENT_VERSION, entries: [] }
  } catch {
    return { version: CURRENT_VERSION, entries: [] }
  }
}

function writeRaw(state: WatchlistStorage): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(state))
    window.dispatchEvent(new Event(WATCHLIST_CHANGED_EVENT))
  } catch {
    throw new Error('Storage unavailable')
  }
}

export function getWatchlist(): WatchlistEntry[] {
  return readRaw().entries
}

export function isWatched(assetId: string): boolean {
  return getWatchlist().some(e => e.asset_id === assetId)
}

export function getWatchlistCount(): number {
  return getWatchlist().length
}

export function addToWatchlist(assetId: string): { ok: true } | { ok: false; reason: 'duplicate' | 'cap' | 'storage' } {
  const state = readRaw()

  if (state.entries.some(e => e.asset_id === assetId)) {
    return { ok: false, reason: 'duplicate' }
  }

  if (state.entries.length >= MAX_ENTRIES) {
    return { ok: false, reason: 'cap' }
  }

  const updated: WatchlistStorage = {
    version: CURRENT_VERSION,
    entries: [...state.entries, { asset_id: assetId, added_at: new Date().toISOString() }],
  }

  try {
    writeRaw(updated)
    return { ok: true }
  } catch {
    return { ok: false, reason: 'storage' }
  }
}

export function removeFromWatchlist(assetId: string): boolean {
  const state = readRaw()
  const updated: WatchlistStorage = {
    version: CURRENT_VERSION,
    entries: state.entries.filter(e => e.asset_id !== assetId),
  }

  if (updated.entries.length === state.entries.length) return false

  try {
    writeRaw(updated)
    return true
  } catch {
    return false
  }
}

export function clearWatchlist(): void {
  try {
    writeRaw({ version: CURRENT_VERSION, entries: [] })
  } catch {
    // ignore
  }
}

/**
 * Prune deleted asset_ids from watchlist.
 * Only call when fetched without filters/search active — search-miss vs deleted are indistinguishable.
 */
export function pruneWatchlist(existingAssetIds: Set<string>): number {
  const state = readRaw()
  const kept = state.entries.filter(e => existingAssetIds.has(e.asset_id))
  if (kept.length === state.entries.length) return 0

  try {
    writeRaw({ version: CURRENT_VERSION, entries: kept })
    return state.entries.length - kept.length
  } catch {
    return 0
  }
}
