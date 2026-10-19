export type WeatherDataset = 'genuine' | 'synthetic'

/** A weather observation as returned by the weather APIs. */
export interface ApiWeatherObservation {
  id: number
  location_id: number
  observed_at: string
  received_at: string
  source: string
  source_type: 'manual' | 'provider' | 'synthetic'
  rainfall_mm: number | null
  rainfall_period_minutes: number | null
  temperature_c: number | null
  humidity_pct: number | null
  pressure_hpa: number | null
  wind_speed_mps: number | null
  wind_direction_deg: number | null
  river_level_m: number | null
  river_discharge_m3s: number | null
  soil_moisture_pct: number | null
  upstream_rainfall_mm: number | null
  upstream_rainfall_period_minutes: number | null
  coastal_tide_m: number | null
  gauge_datum: string | null
  missing_fields: string[]
  stale: boolean
  age_seconds: number
  notice: string | null
}

/** `GET /api/weather/latest` response. */
export interface ApiLatestWeather {
  location_id: number
  status: 'no_data' | 'fresh' | 'stale'
  source_type: string
  notice: string | null
  observation: ApiWeatherObservation | null
}
