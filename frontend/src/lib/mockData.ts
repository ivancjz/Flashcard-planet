// frontend/src/lib/mockData.ts
import type { MarketStats, TickerItem, CardSummary, PricePoint, AlertEvent } from '../types/api'

export const MOCK_STATS: MarketStats = {
  total_assets: 2897,
  signal_counts: { BREAKOUT: 45, MOVE: 296, WATCH: 96, IDLE: 121, INSUFFICIENT_DATA: 1965 },
  last_ingest_utc: '2026-04-19T09:14:07+00:00',
  next_ingest_utc: null,
  sources_active: ['pokemon_tcg_api', 'ebay_sold'],
}

export const MOCK_TICKER: TickerItem[] = [
  { asset_id: 'mock-0001', name: 'Charizard ex', price_delta_pct: 12.4, signal: 'BREAKOUT', current_price: 42.50 },
  { asset_id: 'mock-0002', name: 'Umbreon VMAX', price_delta_pct: 5.2, signal: 'WATCH', current_price: 89.99 },
  { asset_id: 'mock-0003', name: 'Rayquaza VMAX', price_delta_pct: -8.1, signal: 'MOVE', current_price: 55.00 },
  { asset_id: 'mock-0004', name: 'Pikachu VMAX', price_delta_pct: 18.7, signal: 'BREAKOUT', current_price: 32.00 },
  { asset_id: 'mock-0005', name: 'Giratina VSTAR', price_delta_pct: 2.1, signal: 'WATCH', current_price: 28.50 },
  { asset_id: 'mock-0006', name: 'Lugia VSTAR', price_delta_pct: -0.5, signal: 'IDLE', current_price: 35.00 },
]

export const MOCK_CARDS: CardSummary[] = [
  { asset_id: 'mock-0001', name: 'Charizard ex', set_name: 'Obsidian Flames', rarity: 'ultra', card_type: 'Fire', tcg_price: 42.50, ebay_price: 38.00, signal: 'BREAKOUT', price_delta_pct: 12.4, liquidity_score: 98, volume_24h: 847, image_url: null },
  { asset_id: 'mock-0002', name: 'Umbreon VMAX', set_name: 'Evolving Skies', rarity: 'secret', card_type: 'Dark', tcg_price: 89.99, ebay_price: 95.00, signal: 'WATCH', price_delta_pct: 5.2, liquidity_score: 72, volume_24h: 312, image_url: null },
  { asset_id: 'mock-0003', name: 'Rayquaza VMAX', set_name: 'Evolving Skies', rarity: 'ultra', card_type: 'Dragon', tcg_price: 55.00, ebay_price: 48.00, signal: 'MOVE', price_delta_pct: -8.1, liquidity_score: 81, volume_24h: 521, image_url: null },
  { asset_id: 'mock-0004', name: 'Pikachu VMAX', set_name: 'Hidden Fates', rarity: 'ultra', card_type: 'Electric', tcg_price: 32.00, ebay_price: 29.00, signal: 'BREAKOUT', price_delta_pct: 18.7, liquidity_score: 95, volume_24h: 1203, image_url: null },
  { asset_id: 'mock-0005', name: 'Giratina VSTAR', set_name: 'Lost Origin', rarity: 'holo', card_type: 'Dragon', tcg_price: 28.50, ebay_price: 31.00, signal: 'WATCH', price_delta_pct: 2.1, liquidity_score: 60, volume_24h: 444, image_url: null },
  { asset_id: 'mock-0006', name: 'Lugia VSTAR', set_name: 'Silver Tempest', rarity: 'ultra', card_type: 'Colorless', tcg_price: 35.00, ebay_price: 33.00, signal: 'IDLE', price_delta_pct: -0.5, liquidity_score: 44, volume_24h: 267, image_url: null },
  { asset_id: 'mock-0007', name: 'Mewtwo V-UNION', set_name: 'Celebrations', rarity: 'rare', card_type: 'Psychic', tcg_price: null, ebay_price: null, signal: 'INSUFFICIENT_DATA', price_delta_pct: null, liquidity_score: null, volume_24h: null, image_url: null },
]

export const MOCK_PRICE_HISTORY: PricePoint[] = Array.from({ length: 14 }, (_, i) => {
  const date = new Date('2026-04-05')
  date.setDate(date.getDate() + i)
  const base = 38 + Math.sin(i * 0.6) * 4
  return {
    date: date.toISOString().slice(0, 10),
    tcg_price: +(base + 4).toFixed(2),
    ebay_price: +(base).toFixed(2),
  }
})

export const MOCK_ALERTS: AlertEvent[] = [
  { id: 'alert-0001', asset_id: 'mock-0001', card_name: 'Charizard ex', previous_signal: 'WATCH', current_signal: 'BREAKOUT', price_delta_pct: 12.4, created_at: new Date(Date.now() - 3 * 60000).toISOString(), severity: 'high' },
  { id: 'alert-0002', asset_id: 'mock-0003', card_name: 'Rayquaza VMAX', previous_signal: 'IDLE', current_signal: 'MOVE', price_delta_pct: -8.1, created_at: new Date(Date.now() - 47 * 60000).toISOString(), severity: 'medium' },
  { id: 'alert-0003', asset_id: 'mock-0005', card_name: 'Giratina VSTAR', previous_signal: 'IDLE', current_signal: 'WATCH', price_delta_pct: 2.1, created_at: new Date(Date.now() - 3 * 3600000).toISOString(), severity: 'low' },
  { id: 'alert-0004', asset_id: 'mock-0004', card_name: 'Pikachu VMAX', previous_signal: 'MOVE', current_signal: 'BREAKOUT', price_delta_pct: 18.7, created_at: new Date(Date.now() - 26 * 3600000).toISOString(), severity: 'high' },
]
