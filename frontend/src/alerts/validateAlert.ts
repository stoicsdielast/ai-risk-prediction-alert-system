import type { PublicAlert } from '../types/alert'

export function isPublicAlert(value: unknown): value is PublicAlert {
  if (!value || typeof value !== 'object') return false
  const item = value as PublicAlert
  return Number.isSafeInteger(item.id) && item.id > 0 &&
    Number.isSafeInteger(item.location_id) && item.location_id > 0 &&
    item.location?.id === item.location_id &&
    typeof item.location.name === 'string' && item.location.name.trim().length > 0 &&
    ['LOW', 'MODERATE', 'HIGH', 'VERY_HIGH'].includes(item.severity) &&
    item.status === 'APPROVED' &&
    ['AI_RECOMMENDATION', 'MET_OFFICIAL'].includes(item.source) &&
    typeof item.message === 'string' && item.message.trim().length > 0 &&
    typeof item.created_at === 'string' && Number.isFinite(Date.parse(item.created_at)) &&
    typeof item.approved_at === 'string' && Number.isFinite(Date.parse(item.approved_at)) &&
    (item.is_demo === undefined || typeof item.is_demo === 'boolean')
}
