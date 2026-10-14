import { apiRequest } from './client'
import type { AdminAlert, AlertAction, AlertDraft, PublicAlert } from '../types/alert'
import type { AlertStatus } from '../types/prototype'

const ADMIN_URL = '/api/admin/alerts'
const PAGE_SIZE = 200
export const ALERT_STATUSES: AlertStatus[] = ['PENDING', 'APPROVED', 'REJECTED', 'SUPPRESSED']

// Read every page so counts and community warnings are not capped at the API default.
async function readPages<T>(path: string, signal?: AbortSignal, token?: string): Promise<T[]> {
  const rows: T[] = []
  for (let offset = 0; ; offset += PAGE_SIZE) {
    const separator = path.includes('?') ? '&' : '?'
    const page = await apiRequest<T[]>(`${path}${separator}offset=${offset}&limit=${PAGE_SIZE}`, {
      token,
      signal,
    })
    rows.push(...page)
    if (page.length < PAGE_SIZE) return rows
  }
}

export async function getAdminAlerts(token: string, signal?: AbortSignal): Promise<AdminAlert[]> {
  const pages = await Promise.all(
    ALERT_STATUSES.map((status) =>
      readPages<AdminAlert>(`${ADMIN_URL}?status=${status}`, signal, token),
    ),
  )
  return [...new Map(pages.flat().map((alert) => [alert.id, alert])).values()].sort(
    (a, b) => Date.parse(b.created_at) - Date.parse(a.created_at) || b.id - a.id,
  )
}

export async function getPublicAlerts(signal?: AbortSignal): Promise<PublicAlert[]> {
  const rows = await readPages<PublicAlert>('/api/alerts/active', signal)
  return [...new Map(rows.map((alert) => [alert.id, alert])).values()]
}

export function createAlert(token: string, draft: AlertDraft) {
  return apiRequest<AdminAlert>(ADMIN_URL, { token, method: 'POST', body: JSON.stringify(draft) })
}

export function editAlert(
  token: string,
  id: number,
  draft: Pick<AlertDraft, 'message' | 'severity'>,
) {
  return apiRequest<AdminAlert>(`${ADMIN_URL}/${id}`, {
    token,
    method: 'PATCH',
    body: JSON.stringify(draft),
  })
}

export function reviewAlert(token: string, id: number, action: AlertAction, reason?: string) {
  return apiRequest<AdminAlert>(`${ADMIN_URL}/${id}/${action}`, {
    token,
    method: 'PATCH',
    ...(action === 'suppress' ? { body: JSON.stringify({ reason: reason?.trim() }) } : {}),
  })
}
