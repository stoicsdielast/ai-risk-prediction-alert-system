import type { RiskLevel, WeatherLocation } from './prototype'

export type DivisionCode = 'CENTRAL' | 'WESTERN' | 'NORTHERN' | 'EASTERN'

export type PredictionSource = 'SAMPLE' | 'MODEL'

/** A risk prediction as returned by the location API. */
export interface ApiPrediction {
  risk_level: RiskLevel
  confidence_percent: number
  label: string
  summary: string
  source: PredictionSource
  is_sample: boolean
  generated_at: string
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
  confidencePercent: number
  label: string
  summary: string
  isSample: boolean
  generatedAt: string
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
