import { apiRequest } from './client'
import type { PublicAlert } from '../types/alert'

export interface SavedLocation { id: number; name: string; is_active: boolean }
export interface NotificationPreference { browser_enabled: boolean; delivery_enabled: boolean }
export interface NotificationRecord {
  id: number; alert_id: number; location: string; message: string; is_demo: boolean
  status: 'PENDING' | 'DELIVERED' | 'FAILED' | 'CANCELLED'
  created_at: string; delivered_at: string | null; attempts: number
  last_error: string | null; next_attempt_at: string | null
}
export interface DeliveryClaim { id: number; token: string; alert: PublicAlert; expires_at: string }
export const getSavedLocations = (token: string, signal?: AbortSignal) =>
  apiRequest<SavedLocation[]>('/api/me/subscriptions', { token, signal })
export const saveLocation = (token: string, id: number, save: boolean) =>
  apiRequest(`/api/me/subscriptions/${id}`, { token, method: save ? 'PUT' : 'DELETE' })
export const getNotificationPreferences = (token: string, signal?: AbortSignal) =>
  apiRequest<NotificationPreference>('/api/me/notification-preferences', { token, signal })
export const setNotificationPreference = (token: string, enabled: boolean) =>
  apiRequest<NotificationPreference>('/api/me/notification-preferences', {
    token, method: 'PUT', body: JSON.stringify({ browser_enabled: enabled }),
  })
export const getNotifications = (token: string, pending = false, signal?: AbortSignal, offset = 0) =>
  apiRequest<NotificationRecord[]>(`/api/me/notifications?pending=${pending}&offset=${offset}`, { token, signal })
export const claimNotification = (token: string, id: number) =>
  apiRequest<DeliveryClaim>(`/api/me/notifications/${id}/claim`, { token, method: 'POST' })
export const checkNotification = (token: string, id: number, claim: string) =>
  apiRequest(`/api/me/notifications/${id}/check`, { token, method: 'POST', body: JSON.stringify({ token: claim }) })
export const acknowledgeNotification = (token: string, id: number, claim: string, outcome: 'DELIVERED' | 'FAILED', error?: string) =>
  apiRequest<NotificationRecord>(`/api/me/notifications/${id}/receipt`, {
    token, method: 'POST', body: JSON.stringify({ token: claim, outcome, error }),
  })
