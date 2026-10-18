import { apiRequest } from './client'
import type { ApiLocation } from '../types/location'

const PRIORITY_LOCATIONS_PATH = '/api/me/priority-locations'

export function getPriorityLocations(
  token: string,
  signal?: AbortSignal,
): Promise<ApiLocation[]> {
  return apiRequest<ApiLocation[]>(PRIORITY_LOCATIONS_PATH, { token, signal })
}

export function savePriorityLocation(token: string, slug: string): Promise<ApiLocation> {
  return apiRequest<ApiLocation>(
    `${PRIORITY_LOCATIONS_PATH}/${encodeURIComponent(slug)}`,
    { method: 'PUT', token },
  )
}

export function removePriorityLocation(token: string, slug: string): Promise<void> {
  return apiRequest<void>(
    `${PRIORITY_LOCATIONS_PATH}/${encodeURIComponent(slug)}`,
    { method: 'DELETE', token },
  )
}
