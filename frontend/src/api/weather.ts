import { apiRequest } from './client'
import type { ApiLatestWeather, WeatherDataset } from '../types/weather'

export function getLatestWeather(
  locationId: number,
  dataset: WeatherDataset = 'synthetic',
  signal?: AbortSignal,
): Promise<ApiLatestWeather> {
  return apiRequest<ApiLatestWeather>(
    `/api/weather/latest?location_id=${locationId}&dataset=${dataset}`,
    { signal },
  )
}
