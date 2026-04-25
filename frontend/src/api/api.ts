// frontend/src/api/api.ts
import type { MarketStats, TickerItem, CardsResponse, CardDetail, AlertsResponse, Signal, SetOption, RarityOption } from '../types/api'

const BASE = ''  // same-origin: FastAPI serves both API and SPA

export async function fetchStats(): Promise<MarketStats> {
  const res = await fetch(`${BASE}/api/v1/web/stats`)
  if (!res.ok) throw new Error('stats fetch failed')
  return res.json()
}

export async function fetchTicker(): Promise<TickerItem[]> {
  const res = await fetch(`${BASE}/api/v1/web/ticker`)
  if (!res.ok) throw new Error('ticker fetch failed')
  return res.json()
}

export async function fetchCards(params: {
  game?: string
  signal?: Signal | 'ALL'
  sort?: 'change' | 'price' | 'volume' | 'recent'
  search?: string
  set_id?: string[]
  rarity?: string[]
  price_min?: number
  price_max?: number
  limit?: number
  offset?: number
}): Promise<CardsResponse> {
  const { game = 'pokemon', signal = 'ALL', sort = 'change', search, set_id, rarity, price_min, price_max, limit = 50, offset = 0 } = params
  const qs = new URLSearchParams({ game, signal, sort, limit: String(limit), offset: String(offset) })
  if (search && search.trim()) qs.set('search', search.trim())
  if (set_id?.length) qs.set('set_id', set_id.join(','))
  if (rarity?.length) qs.set('rarity', rarity.join(','))
  if (price_min != null) qs.set('price_min', String(price_min))
  if (price_max != null) qs.set('price_max', String(price_max))
  const res = await fetch(`${BASE}/api/v1/web/cards?${qs}`)
  if (!res.ok) throw new Error('cards fetch failed')
  return res.json()
}

export async function fetchCardsById(params: {
  asset_ids: string[]
  signalFilter?: Signal | 'ALL'
  sort?: 'change' | 'price' | 'volume'
  search?: string
  limit?: number
  signal?: AbortSignal
}): Promise<CardsResponse> {
  const { asset_ids, signalFilter = 'ALL', sort = 'change', search, limit = 200, signal } = params
  const res = await fetch(`${BASE}/api/v1/web/cards/batch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ asset_ids, signal: signalFilter, sort, search: search ?? null, limit }),
    signal,
  })
  if (!res.ok) throw new Error('cards batch fetch failed')
  return res.json()
}

export async function fetchSetOptions(game: string): Promise<SetOption[]> {
  const res = await fetch(`${BASE}/api/v1/web/filters/sets?game=${game}`)
  if (!res.ok) throw new Error('set options fetch failed')
  const data = await res.json()
  return data.sets
}

export async function fetchRarityOptions(game: string): Promise<RarityOption[]> {
  const res = await fetch(`${BASE}/api/v1/web/filters/rarities?game=${game}`)
  if (!res.ok) throw new Error('rarity options fetch failed')
  const data = await res.json()
  return data.rarities
}

export async function fetchCard(assetId: string): Promise<CardDetail> {
  const res = await fetch(`${BASE}/api/v1/web/cards/${assetId}`)
  if (!res.ok) throw new Error('card fetch failed')
  return res.json()
}

export async function fetchAlerts(params: {
  filter?: 'ALL' | 'HIGH' | 'UNREAD'
  limit?: number
}): Promise<AlertsResponse> {
  const qs = new URLSearchParams({
    filter: params.filter ?? 'ALL',
    limit: String(params.limit ?? 50),
  })
  const res = await fetch(`${BASE}/api/v1/web/alerts?${qs}`)
  if (!res.ok) throw new Error('alerts fetch failed')
  return res.json()
}
