import type { RiskLevel, WeatherLocation } from './prototype'

export type DivisionCode = 'CENTRAL' | 'WESTERN' | 'NORTHERN' | 'EASTERN'

/** A location as returned by `GET /api/locations`. */
export interface ApiLocation {
  slug: string
  name: string
  division: DivisionCode
  division_label: string
  latitude: number
  longitude: number
}

/** A backend location prepared for the weather map. */
export interface MapLocation {
  id: string
  name: string
  division: string
  latitude: number
  longitude: number
  riskLevel: RiskLevel | null
  /** Prototype weather and prediction data, when the demo set has any. */
  conditions: WeatherLocation | null
}
