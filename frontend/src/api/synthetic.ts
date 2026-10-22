import { apiRequest } from './client'
import type { RiskLevel } from '../types/prototype'

export const SYNTHETIC_NOTICE = 'Synthetic Data — Research Demonstration'
export interface SyntheticInfo {
  source_type: 'synthetic'
  status: 'ready' | 'not_imported'
  observations: number
  alerts_enabled: boolean
  example_timestamp?: string | null
  config: { start: string; end: string } | null
}
export interface SyntheticLocation {
  source_type: 'synthetic'
  location_id: number
  slug: string
  name: string
  division: string
  latitude: number
  longitude: number
  timestamp: string
  horizon_hours: number
  model_version: string
  probability: number | null
  risk_category: RiskLevel | null
  status: 'ok' | 'ongoing_simulated_flood' | 'insufficient_history'
  simulated_flood_active: boolean
  weather: Record<string, number | null>
}
export interface SyntheticFrame {
  source_type: 'synthetic'
  timestamp: string
  locations: SyntheticLocation[]
}
export interface SyntheticAlert {
  id: number
  source_type: 'synthetic'
  status: 'PENDING' | 'APPROVED' | 'REJECTED'
  location_name: string
  probability: number
  risk_category: RiskLevel
  timestamp: string
  message: string
}
export const getSyntheticInfo = () => apiRequest<SyntheticInfo>('/api/synthetic/info')
export async function getSyntheticFrame(timestamp: string) {
  const frame = await apiRequest<SyntheticFrame>(`/api/synthetic/frame?timestamp=${encodeURIComponent(timestamp)}`)
  if (frame.source_type !== 'synthetic' || frame.locations.some(location => location.source_type !== 'synthetic')) {
    throw new Error('Unexpected data source in synthetic replay')
  }
  return frame
}
export const getSyntheticAlerts = (token?: string) => apiRequest<SyntheticAlert[]>(
  token ? '/api/synthetic/admin/alerts' : '/api/synthetic/alerts', { token },
)
export const createSyntheticAlert = (locationId: number, timestamp: string, token: string) => apiRequest<SyntheticAlert>(
  '/api/synthetic/admin/alerts', { method: 'POST', token, body: JSON.stringify({ location_id: locationId, timestamp }) },
)
export const approveSyntheticAlert = (id: number, token: string) => apiRequest<SyntheticAlert>(
  `/api/synthetic/admin/alerts/${id}/approve`, { method: 'POST', token },
)

export function notifySyntheticApproval(alert: SyntheticAlert, optedIn: boolean): boolean {
  if (!optedIn || alert.source_type !== 'synthetic' || alert.status !== 'APPROVED' ||
    !['HIGH', 'VERY_HIGH'].includes(alert.risk_category) || !('Notification' in window) || Notification.permission !== 'granted') return false
  new Notification(`${SYNTHETIC_NOTICE}: ${alert.location_name}`, {
    body: `${alert.risk_category} simulated forecast. No emergency warning.`, tag: `synthetic-demo-${alert.id}`,
  })
  return true
}
