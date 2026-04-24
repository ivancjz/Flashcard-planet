// frontend/src/api/api.ts
import type { MarketStats, TickerItem, CardsResponse, CardDetail, AlertsResponse, Signal } from '../types/api'

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
  sort?: 'change' | 'price' | 'volume'
  search?: string
  limit?: number
  offset?: number
}): Promise<CardsResponse> {
  const { game = 'pokemon', signal = 'ALL', sort = 'change', search, limit = 50, offset = 0 } = params
  const qs = new URLSearchParams({ game, signal, sort, limit: String(limit), offset: String(offset) })
  if (search && search.trim()) qs.set('search', search.trim())
  const res = await fetch(`${BASE}/api/v1/web/cards?${qs}`)
  if (!res.ok) throw new Error('cards fetch failed')
  return res.json()
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
