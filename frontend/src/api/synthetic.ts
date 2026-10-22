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
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'RESOLVED' | 'CANCELLED'
  location_id: number
  model_version: string
  is_test: boolean
  location_name: string
  probability: number
  risk_category: RiskLevel
  timestamp: string
  message: string
  created_by?: number
  created_at?: string
  reviewed_by?: number | null
  reviewed_at?: string | null
  acknowledged_by?: number | null
  acknowledged_at?: string | null
  closed_by?: number | null
  closed_at?: string | null
  closure_reason?: string | null
}
export const getSyntheticInfo = () => apiRequest<SyntheticInfo>('/api/synthetic/info')
export async function getSyntheticFrame(timestamp: string) {
  const frame = await apiRequest<SyntheticFrame>(`/api/synthetic/frame?timestamp=${encodeURIComponent(timestamp)}`)
  if (frame.source_type !== 'synthetic' || frame.locations.some(location => location.source_type !== 'synthetic')) {
    throw new Error('Unexpected data source in synthetic replay')
  }
  return frame
}
export async function getSyntheticAlerts(token?: string) {
  const rows: SyntheticAlert[] = []
  for (let offset = 0; ; offset += 200) {
    const page = await apiRequest<SyntheticAlert[]>(`${token ? '/api/synthetic/admin/alerts' : '/api/synthetic/alerts'}?offset=${offset}&limit=200`, { token })
    if (!Array.isArray(page) || page.some(row => row.source_type !== 'synthetic')) throw new Error('Unexpected synthetic alert data')
    rows.push(...page)
    if (page.length < 200) return rows
  }
}
export const createSyntheticAlert = (locationId: number, timestamp: string, token: string, testAlert = false) => apiRequest<SyntheticAlert>(
  '/api/synthetic/admin/alerts', { method: 'POST', token, body: JSON.stringify({ location_id: locationId, timestamp, test_alert: testAlert }) },
)
export const approveSyntheticAlert = (id: number, token: string) => apiRequest<SyntheticAlert>(
  `/api/synthetic/admin/alerts/${id}/approve`, { method: 'POST', token },
)
export const manageSyntheticAlert = (id: number, token: string, action: 'acknowledge' | 'resolve' | 'cancel', reason?: string) => apiRequest<SyntheticAlert>(
  `/api/synthetic/admin/alerts/${id}/${action}`, { method: 'POST', token,
    ...(action !== 'acknowledge' ? { body: JSON.stringify({ reason: reason?.trim() }) } : {}) },
)

export function notifySyntheticApproval(alert: SyntheticAlert, optedIn: boolean): boolean {
  if (!optedIn || alert.source_type !== 'synthetic' || alert.status !== 'APPROVED' ||
    !['HIGH', 'VERY_HIGH'].includes(alert.risk_category) || !('Notification' in window) || Notification.permission !== 'granted') return false
  new Notification(`${SYNTHETIC_NOTICE}: ${alert.location_name}`, {
    body: `${alert.risk_category} simulated forecast. No emergency warning.`, tag: `synthetic-demo-${alert.id}`,
  })
  return true
}
