import type { RiskLevel, WeatherLocation } from './prototype'

export type DivisionCode = 'CENTRAL' | 'WESTERN' | 'NORTHERN' | 'EASTERN'

/** A risk prediction as returned by the location API. */
export interface ApiPrediction {
  risk_level: RiskLevel
  /** P(flood) from 0 to 1. Not a calibrated confidence score. */
  flood_probability: number
  model_version: string
  is_sample: boolean
  predicted_at: string
}

/** A location as returned by `GET /api/locations`. */
export interface ApiLocation {
  slug: string
  name: string
  division: DivisionCode
  division_label: string
  latitude: number
  longitude: number
  /** `null` when no prediction is available for this location. */
  prediction: ApiPrediction | null
}

export interface MapPrediction {
  riskLevel: RiskLevel
  floodProbabilityPercent: number
  isSample: boolean
  predictedAt: string
}

/** A backend location prepared for the weather map. */
export interface MapLocation {
  id: string
  name: string
  division: string
  latitude: number
  longitude: number
  riskLevel: RiskLevel | null
  prediction: MapPrediction | null
  /** Prototype weather and official-warning data, when the demo set has any. */
  conditions: WeatherLocation | null
}
