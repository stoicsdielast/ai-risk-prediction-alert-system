export type RiskLevel = 'LOW' | 'MODERATE' | 'HIGH' | 'VERY_HIGH'

export type AlertSeverity = RiskLevel

export type AlertStatus = 'PENDING' | 'APPROVED' | 'REJECTED' | 'SUPPRESSED'

export interface WeatherLocation {
  id: string
  name: string
  division: string
  latitude: number
  longitude: number
  riskLevel: RiskLevel
  condition: string
  temperatureC: number
  rainfall24hMm: number
  humidityPercent: number
  windKph: number
  updatedAt: string
  prediction: {
    label: string
    confidencePercent: number
    summary: string
  }
  officialWarning: string | null
}

export interface AlertRecord {
  id: string
  locationId: string
  locationName: string
  severity: AlertSeverity
  status: AlertStatus
  message: string
  createdAt: string
  source: 'AI_RECOMMENDATION' | 'MET_OFFICIAL'
}

export interface PredictionRecord {
  id: string
  locationName: string
  riskLevel: RiskLevel
  confidencePercent: number
  horizon: string
  generatedAt: string
}
