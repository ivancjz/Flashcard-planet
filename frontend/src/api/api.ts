// frontend/src/api/api.ts
import type { MarketStats, TickerItem, CardsResponse, CardDetail, AlertsResponse, Signal } from '../types/api'
import { MOCK_STATS, MOCK_TICKER, MOCK_CARDS, MOCK_PRICE_HISTORY, MOCK_ALERTS } from '../lib/mockData'
import { getReadAlertIds } from '../lib/utils'

export async function fetchStats(): Promise<MarketStats> {
  return MOCK_STATS
}

export async function fetchTicker(): Promise<TickerItem[]> {
  return MOCK_TICKER
}

export async function fetchCards(params: {
  signal?: Signal | 'ALL'
  sort?: 'change' | 'price' | 'volume'
  limit?: number
  offset?: number
}): Promise<CardsResponse> {
  const { signal = 'ALL', sort = 'change', limit = 50, offset = 0 } = params
  let cards = signal === 'ALL' ? MOCK_CARDS : MOCK_CARDS.filter(c => c.signal === signal)
  if (sort === 'price')  cards = [...cards].sort((a, b) => (b.tcg_price ?? 0) - (a.tcg_price ?? 0))
  if (sort === 'volume') cards = [...cards].sort((a, b) => (b.volume_24h ?? 0) - (a.volume_24h ?? 0))
  if (sort === 'change') cards = [...cards].sort((a, b) => Math.abs(b.price_delta_pct ?? 0) - Math.abs(a.price_delta_pct ?? 0))
  return { cards: cards.slice(offset, offset + limit), total: cards.length, limit, offset }
}

export async function fetchCard(assetId: string): Promise<CardDetail> {
  const found = MOCK_CARDS.find(c => c.asset_id === assetId)
  if (!found) throw new Error(`Card ${assetId} not found`)
  return {
    ...found,
    price_history: MOCK_PRICE_HISTORY,
    spread_pct: found.tcg_price && found.ebay_price
      ? +((found.tcg_price - found.ebay_price) / found.tcg_price * 100).toFixed(1)
      : null,
  }
}

export async function fetchAlerts(params: {
  filter?: 'ALL' | 'HIGH' | 'UNREAD'
  limit?: number
}): Promise<AlertsResponse> {
  const readIds = getReadAlertIds()
  let alerts = MOCK_ALERTS
  if (params.filter === 'HIGH')   alerts = alerts.filter(a => a.severity === 'high')
  if (params.filter === 'UNREAD') alerts = alerts.filter(a => !readIds.has(a.id))
  return { alerts, total: alerts.length }
}
