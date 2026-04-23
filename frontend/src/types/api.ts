// frontend/src/types/api.ts
export type Signal = 'BREAKOUT' | 'MOVE' | 'WATCH' | 'IDLE' | 'INSUFFICIENT_DATA'
export type Rarity = 'common' | 'uncommon' | 'rare' | 'holo' | 'ultra' | 'secret'

export interface MarketStats {
  total_assets: number
  signal_counts: Record<Signal, number>
  last_ingest_utc: string | null
  next_ingest_utc: string | null
  sources_active: string[]
}

export interface TickerItem {
  asset_id: string
  name: string
  price_delta_pct: number
  signal: Signal
  current_price: number | null
}

export interface CardSummary {
  asset_id: string
  name: string
  set_name: string | null
  rarity: Rarity | null
  card_type: string | null
  tcg_price: number | null
  ebay_price: number | null
  signal: Signal
  price_delta_pct: number | null
  liquidity_score: number | null
  volume_24h: number | null
  image_url: string | null
}

export interface PricePoint {
  date: string
  tcg_price: number | null
  ebay_price: number | null
}

export interface CardDetail extends CardSummary {
  price_history: PricePoint[]
  spread_pct: number | null
  ai_analysis?: string | null
}

export interface AlertEvent {
  id: string
  asset_id: string
  card_name: string
  previous_signal: Signal | null
  current_signal: Signal
  price_delta_pct: number | null
  created_at: string
  severity: 'high' | 'medium' | 'low'
}

export interface AlertsResponse {
  alerts: AlertEvent[]
  total: number
}

export interface CardsResponse {
  cards: CardSummary[]
  total: number
  limit: number
  offset: number
}
