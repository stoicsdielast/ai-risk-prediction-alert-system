import type { ApiLocation, ApiPrediction } from './location'
import type { RiskLevel } from './prototype'

export type AlertSource = 'AI_RECOMMENDATION' | 'MET_OFFICIAL'

/** An approved alert as returned by `GET /api/alerts/active`. */
export interface ApiAlert {
  id: number
  location_id: number
  location: ApiLocation
  prediction_id: number | null
  prediction: ApiPrediction | null
  severity: RiskLevel
  status: 'APPROVED'
  source: AlertSource
  message: string
  created_at: string
  approved_at: string | null
}
