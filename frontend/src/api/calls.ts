import type { CallsListResponse, CalibrationResponse, PublicPrediction } from '../types/calls'

const BASE = '/api/v1/calls'

export async function fetchCallsList(
  status: 'all' | 'pending' | 'resolved' = 'all'
): Promise<CallsListResponse> {
  const res = await fetch(`${BASE}/list?status=${status}`)
  if (!res.ok) throw new Error(`calls/list fetch failed: ${res.status}`)
  return res.json()
}

export async function fetchCalibration(): Promise<CalibrationResponse> {
  const res = await fetch(`${BASE}/calibration`)
  if (!res.ok) throw new Error(`calls/calibration fetch failed: ${res.status}`)
  return res.json()
}

export async function fetchCallDetail(predictionId: string): Promise<PublicPrediction> {
  const res = await fetch(`${BASE}/${predictionId}`)
  if (!res.ok) throw new Error(`calls/${predictionId} fetch failed: ${res.status}`)
  return res.json()
}
