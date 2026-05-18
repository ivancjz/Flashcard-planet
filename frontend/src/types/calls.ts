export type ThresholdDirection = 'above' | 'below' | 'within_band'
export type ResolutionStatus = 'PENDING' | 'HIT' | 'MISS' | 'AMBIGUOUS' | 'VOIDED'
export type DriverAttribution =
  | 'MACRO' | 'META_SHIFT' | 'SUPPLY_SHOCK'
  | 'EVENT_DRIVEN' | 'INFLUENCER_PROVENANCE' | 'UNKNOWN'

export interface PublicPrediction {
  id: string
  predicted_at: string
  resolution_date: string
  asset_id: string
  prediction_text: string
  threshold_value: string
  threshold_currency: string
  threshold_direction: ThresholdDirection
  threshold_band_high: string | null
  stated_probability: number
  driver_attribution: DriverAttribution | null
  driver_confidence: number | null
  methodology_version: string
  resolution_status: ResolutionStatus
  resolved_at: string | null
  actual_value: string | null
  notes: string | null
}

export interface CallsListResponse {
  status_filter: string
  count: number
  predictions: PublicPrediction[]
}

export interface ReliabilityBin {
  prob_bin_low: number
  prob_bin_high: number
  n: number
  hit_rate: number
  ci_low: number
  ci_high: number
}

export interface CalibrationResponse {
  total_calls: number
  total_resolved: number
  brier_score: number | null
  brier_baseline: number
  reliability_bins: ReliabilityBin[]
  methodology_version: string
}
