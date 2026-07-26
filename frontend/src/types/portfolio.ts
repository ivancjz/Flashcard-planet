export interface PortfolioLot {
  id: string
  asset_id: string
  quantity: number
  unit_cost_usd: string
  purchased_on: string
  created_at: string
  updated_at: string
}

export interface PortfolioPosition {
  asset_id: string
  name: string
  set_name: string | null
  card_number: string | null
  game: string
  quantity: number
  average_unit_cost_usd: string
  cost_basis_usd: string
  latest_raw_price_usd: string | null
  latest_price_at: string | null
  market_value_usd: string | null
  unrealized_pnl_usd: string | null
  unrealized_pnl_percent: string | null
  valuation_status: 'priced' | 'unpriced'
  lots: PortfolioLot[]
}

export interface PortfolioAllocation {
  game: string
  market_value_usd: string
  percentage: string
  priced_position_count: number
}

export interface PortfolioSummary {
  total_cost_basis: string
  priced_cost_basis: string
  total_market_value: string
  unrealized_pnl: string
  unrealized_pnl_percent: string | null
  position_count: number
  priced_position_count: number
  unpriced_position_count: number
  valuation_coverage_percent: string
  position_limit: number | null
}

export interface Portfolio {
  summary: PortfolioSummary
  allocations: PortfolioAllocation[]
  positions: PortfolioPosition[]
}

export interface PortfolioLotInput {
  asset_id: string
  quantity: number
  unit_cost_usd: string
  purchased_on: string
}

export type PortfolioLotPatch = Partial<
  Pick<PortfolioLotInput, 'quantity' | 'unit_cost_usd' | 'purchased_on'>
>

export interface PortfolioApiErrorDetail {
  code?: string
  message?: string
  position_limit?: number
  position_count?: number
  upgrade_url?: string
}
