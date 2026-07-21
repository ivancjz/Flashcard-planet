// frontend/src/types/api.ts
export type Signal = 'BREAKOUT' | 'MOVE' | 'WATCH' | 'IDLE' | 'INSUFFICIENT_DATA'
export type Rarity = 'common' | 'uncommon' | 'rare' | 'holo' | 'ultra' | 'secret'

export interface SetOption {
  id: string
  name: string
  count: number
}

export interface RarityOption {
  value: string
  count: number
}

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
  price_delta_abs?: number | null
  signal: Signal
  current_price: number | null
}

export type MarketDirection = 'up' | 'down' | 'flat'
export type MarketSentiment = 'bullish' | 'neutral' | 'bearish' | 'insufficient_data'
export type MarketConfidence = 'high' | 'medium' | 'low' | 'insufficient'
export type MarketNumber = number | string
export type CatalystStatus = 'upcoming' | 'active' | 'expired'
export type CatalystImpactLabel = 'high' | 'medium' | 'low' | 'unscored'
export type CatalystConfidenceLabel = 'high' | 'medium' | 'low' | 'insufficient_data'

export interface Catalyst {
  id: string
  event_date: string
  active_until: string
  event_type: string
  description: string
  source_url: string
  affected_games: string[]
  affected_asset_ids: string[]
  affected_set_ids: string[]
  expected_window_days: number | null
  impact_score: number | null
  impact_label: CatalystImpactLabel
  confidence_score: MarketNumber | null
  confidence_label: CatalystConfidenceLabel
  status: CatalystStatus
  verified_at: string
}

export interface CatalystListResponse {
  catalysts: Catalyst[]
  total: number
  limit: number
  offset: number
  as_of: string
}

export interface MarketIndex {
  game: string
  label: string
  change_pct: MarketNumber
  direction: MarketDirection
  observed_assets: number
  current_assets: number
  confidence_label: MarketConfidence
}

export interface MarketTopMover {
  asset_id: string
  name: string
  game: string
  set_name: string | null
  latest_price: MarketNumber
  previous_price: MarketNumber
  percent_change: MarketNumber
  absolute_change: MarketNumber
  direction: MarketDirection
}

export interface MarketSignalSummary {
  label: string
  count: number
  average_confidence: MarketNumber | null
}

export interface MarketOverview {
  generated_at: string
  market_sentiment: MarketSentiment
  confidence_label: MarketConfidence
  indexes: MarketIndex[]
  top_movers: MarketTopMover[]
  signal_summary: MarketSignalSummary[]
  commentary: string
  evidence: string[]
}

export interface DailyMarketReport {
  id: string
  report_date: string
  generated_at: string
  status: string
  title: string
  market_sentiment: MarketSentiment
  confidence_label: MarketConfidence
  summary: string
  overview: MarketOverview
  catalysts: Catalyst[]
  evidence: string[]
}

export interface DailyMarketReportListResponse {
  reports: DailyMarketReport[]
  total: number
  limit: number
  offset: number
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
  price_delta_abs?: number | null
  liquidity_score: number | null
  volume_24h: number | null
  image_url: string | null
}

export interface PricePoint {
  date: string
  tcg_price: number | null
  ebay_price: number | null
}

export interface SignalHistoryEvent {
  id: string
  previous_label: Signal | null
  current_label: Signal
  price_at_event: number | null
  price_delta_pct: number | null
  price_delta_abs?: number | null
  computed_at: string
}

export interface CardDetail extends CardSummary {
  price_history: PricePoint[]
  spread_pct: number | null
  ai_analysis?: string | null
  signal_history?: SignalHistoryEvent[]
  driver?: string | null
  driver_confidence?: number | null
  driver_event_description?: string | null
  fundamental_delta_pct?: number | null
  hype_premium_pct?: number | null
}

export interface AlertEvent {
  id: string
  asset_id: string
  card_name: string
  previous_signal: Signal | null
  current_signal: Signal
  price_delta_pct: number | null
  price_delta_abs?: number | null
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
