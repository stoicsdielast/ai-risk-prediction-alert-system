import { apiRequest } from './client'
import type { RiskLevel } from '../types/prototype'

export interface ReplayExample {
  id: string
  selection: string
  station: { station_id: string; name: string; latitude: number; longitude: number }
  feature_date: string
  as_of: string
  mode: 'historical_replay'
  country: 'Bangladesh'
  features: Record<string, number>
}

export interface ResearchResult {
  status: 'ok' | 'data_unavailable'
  research_mode: true
  country: 'Bangladesh'
  mode: 'historical_replay'
  probability: number | null
  presentation_tier: RiskLevel | null
  model_version: string | null
  timestamp: string
  generated_at: string
  prediction_horizon_hours: number
  source: string
  disclaimer: string
  reason: string | null
  missing_features: string[]
}

export interface ResearchInfo {
  status: 'ok' | 'data_unavailable'
  model_version?: string
  selected_model?: string
  disclaimer: string
  reason?: string
  license_status?: string
}

export const getResearchInfo = () => apiRequest<ResearchInfo>('/api/predictions/model-info')
export const getReplayExamples = () => apiRequest<{ status: string; examples: ReplayExample[] }>('/api/predictions/replay-examples')

export async function runReplay(example: ReplayExample, token: string) {
  const response = await apiRequest<ResearchResult>('/api/predictions/flood-risk', {
    method: 'POST', token,
    body: JSON.stringify({ mode: example.mode, country: example.country,
      station_id: example.station.station_id, feature_date: example.feature_date,
      as_of: example.as_of, features: example.features }),
  })
  if (response.research_mode !== true || response.country !== 'Bangladesh' || response.mode !== 'historical_replay' ||
    !['ok', 'data_unavailable'].includes(response.status) ||
    (response.status === 'ok' && (typeof response.probability !== 'number' || !Number.isFinite(response.probability) || response.probability < 0 || response.probability > 1 ||
      !['LOW', 'MODERATE', 'HIGH', 'VERY_HIGH'].includes(response.presentation_tier ?? ''))) ||
    (response.status === 'data_unavailable' && response.probability !== null)) {
    throw new Error('Invalid research prediction response; no score is available.')
  }
  return response
}
