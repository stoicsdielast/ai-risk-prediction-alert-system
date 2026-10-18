import { apiRequest } from './client'
import type { ApiLocation } from '../types/location'

export function getLocations(signal?: AbortSignal): Promise<ApiLocation[]> {
  return apiRequest<ApiLocation[]>('/api/locations', { signal })
}
