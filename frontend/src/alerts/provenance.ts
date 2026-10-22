import type { PublicAlert } from '../types/alert'

export function isSimulatedAlert(alert: Pick<PublicAlert, 'is_demo' | 'prediction'>) {
  return Boolean(alert.is_demo || alert.prediction?.is_sample)
}
