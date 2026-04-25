export interface WatchlistEntry {
  asset_id: string
  added_at: string
}

export interface WatchlistStorage {
  version: 1
  entries: WatchlistEntry[]
}

export const WATCHLIST_CHANGED_EVENT = 'fp-watchlist-changed'
