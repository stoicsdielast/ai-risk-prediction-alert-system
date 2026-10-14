import type { AlertStatus, RiskLevel } from './prototype'

export interface PublicAlert {
  id: number
  location_id: number
  location: { id: number; name: string }
  prediction_id: number | null
  severity: RiskLevel
  status: AlertStatus
  source: 'AI_RECOMMENDATION' | 'MET_OFFICIAL'
  message: string
  created_at: string
  approved_at: string | null
}

export interface AdminAlert extends PublicAlert {
  location: PublicAlert['location'] & { is_active: boolean }
  updated_at: string | null
  rejected_at: string | null
  suppressed_at: string | null
  suppression_reason: string | null
}

export interface AlertDraft {
  location_id: number
  severity: RiskLevel
  message: string
}

export type AlertAction = 'approve' | 'reject' | 'suppress'
