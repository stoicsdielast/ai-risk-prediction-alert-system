import { apiRequest } from './client'
import type { ApiAlert } from '../types/alert'

export function getActiveAlerts(signal?: AbortSignal): Promise<ApiAlert[]> {
  return apiRequest<ApiAlert[]>('/api/alerts/active', { signal })
}
