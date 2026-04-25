import { describe, it, expect, beforeEach } from 'vitest'
import {
  getWatchlist, addToWatchlist, removeFromWatchlist, isWatched,
  getWatchlistCount, clearWatchlist,
} from './watchlist'

const KEY = 'fp_watchlist'

function setRaw(value: unknown) {
  localStorage.setItem(KEY, JSON.stringify(value))
}

beforeEach(() => {
  localStorage.clear()
})

// ── readRaw: legacy string[] ──────────────────────────────────────────────────

describe('legacy string[] migration', () => {
  it('migrates a valid string[] to versioned format', () => {
    setRaw(['uuid-a', 'uuid-b'])
    const entries = getWatchlist()
    expect(entries).toHaveLength(2)
    expect(entries.map(e => e.asset_id)).toEqual(['uuid-a', 'uuid-b'])
    expect(entries.every(e => typeof e.added_at === 'string')).toBe(true)
  })

  it('filters out null and non-string values in legacy array', () => {
    setRaw([null, 42, 'uuid-a', undefined, '', 'uuid-b'])
    const entries = getWatchlist()
    expect(entries.map(e => e.asset_id)).toEqual(['uuid-a', 'uuid-b'])
  })

  it('deduplicates asset_ids in legacy array', () => {
    setRaw(['uuid-a', 'uuid-b', 'uuid-a'])
    const entries = getWatchlist()
    expect(entries).toHaveLength(2)
    expect(entries.map(e => e.asset_id)).toEqual(['uuid-a', 'uuid-b'])
  })

  it('returns empty entries for empty legacy array', () => {
    setRaw([])
    expect(getWatchlist()).toHaveLength(0)
  })
})

// ── readRaw: current versioned format ─────────────────────────────────────────

describe('current versioned format', () => {
  it('reads well-formed entries', () => {
    setRaw({ version: 1, entries: [
      { asset_id: 'uuid-a', added_at: '2024-01-01T00:00:00.000Z' },
      { asset_id: 'uuid-b', added_at: '2024-01-02T00:00:00.000Z' },
    ]})
    expect(getWatchlist()).toHaveLength(2)
  })

  it('deduplicates entries by asset_id, keeping earliest added_at', () => {
    setRaw({ version: 1, entries: [
      { asset_id: 'uuid-a', added_at: '2024-01-01T00:00:00.000Z' },
      { asset_id: 'uuid-b', added_at: '2024-01-02T00:00:00.000Z' },
      { asset_id: 'uuid-a', added_at: '2024-01-03T00:00:00.000Z' }, // duplicate
    ]})
    const entries = getWatchlist()
    expect(entries).toHaveLength(2)
    const a = entries.find(e => e.asset_id === 'uuid-a')!
    expect(a.added_at).toBe('2024-01-01T00:00:00.000Z') // kept earliest
  })

  it('filters entries missing asset_id or added_at', () => {
    setRaw({ version: 1, entries: [
      { asset_id: 'uuid-a', added_at: '2024-01-01T00:00:00.000Z' },
      { asset_id: 'uuid-b' },          // missing added_at
      { added_at: '2024-01-01T00:00:00.000Z' }, // missing asset_id
      null,
    ]})
    expect(getWatchlist()).toHaveLength(1)
  })
})

// ── readRaw: parse errors ─────────────────────────────────────────────────────

describe('corrupt storage', () => {
  it('returns empty on invalid JSON', () => {
    localStorage.setItem(KEY, 'not-json{{{')
    expect(getWatchlist()).toHaveLength(0)
  })

  it('returns empty when key is absent', () => {
    expect(getWatchlist()).toHaveLength(0)
  })

  it('returns empty for unexpected types (number, string)', () => {
    setRaw(42)
    expect(getWatchlist()).toHaveLength(0)
    setRaw('just a string')
    expect(getWatchlist()).toHaveLength(0)
  })
})

// ── addToWatchlist ────────────────────────────────────────────────────────────

describe('addToWatchlist', () => {
  it('adds a new entry', () => {
    expect(addToWatchlist('uuid-a')).toEqual({ ok: true })
    expect(isWatched('uuid-a')).toBe(true)
    expect(getWatchlistCount()).toBe(1)
  })

  it('rejects duplicates', () => {
    addToWatchlist('uuid-a')
    expect(addToWatchlist('uuid-a')).toEqual({ ok: false, reason: 'duplicate' })
    expect(getWatchlistCount()).toBe(1)
  })

  it('enforces 500-entry cap', () => {
    const entries = Array.from({ length: 500 }, (_, i) => ({
      asset_id: `uuid-${String(i).padStart(4, '0')}`,
      added_at: new Date().toISOString(),
    }))
    setRaw({ version: 1, entries })
    expect(addToWatchlist('uuid-new')).toEqual({ ok: false, reason: 'cap' })
  })
})

// ── removeFromWatchlist ───────────────────────────────────────────────────────

describe('removeFromWatchlist', () => {
  it('removes an existing entry', () => {
    addToWatchlist('uuid-a')
    expect(removeFromWatchlist('uuid-a')).toBe(true)
    expect(isWatched('uuid-a')).toBe(false)
  })

  it('returns false when entry not found', () => {
    expect(removeFromWatchlist('uuid-missing')).toBe(false)
  })
})

// ── clearWatchlist ────────────────────────────────────────────────────────────

describe('clearWatchlist', () => {
  it('empties the watchlist', () => {
    addToWatchlist('uuid-a')
    addToWatchlist('uuid-b')
    clearWatchlist()
    expect(getWatchlistCount()).toBe(0)
  })
})
