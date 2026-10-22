import type { PublicAlert } from '../types/alert'

export function isSimulatedAlert(alert: Pick<PublicAlert, 'is_demo' | 'prediction'>) {
  return Boolean(alert.is_demo || alert.prediction?.is_sample)
}

export function isExpiredAlert(alert: Pick<PublicAlert, 'status' | 'expires_at'>) {
  return alert.status === 'APPROVED' && Boolean(alert.expires_at && Date.parse(alert.expires_at) <= Date.now())
}
