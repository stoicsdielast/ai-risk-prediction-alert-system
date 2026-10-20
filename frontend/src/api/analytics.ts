import { apiRequest } from './client'
import type { ModelPerformance, PredictionOverview, PredictionTrend, TrendSource } from '../types/analytics'

const BASE = '/api/admin/analytics'

export const getPredictionOverview = (token: string, days: number, signal?: AbortSignal) =>
  apiRequest<PredictionOverview>(`${BASE}/predictions/overview?days=${days}`, { token, signal })

export function getPredictionTrend(
  token: string, source: TrendSource, days: number, locationIds: number[], signal?: AbortSignal,
) {
  const query = new URLSearchParams({ source, days: String(days) })
  locationIds.forEach((id) => query.append('location_id', String(id)))
  return apiRequest<PredictionTrend>(`${BASE}/predictions/trend?${query}`, { token, signal })
}

export const getModelPerformance = (token: string, signal?: AbortSignal) =>
  apiRequest<ModelPerformance>(`${BASE}/models/performance`, { token, signal })
