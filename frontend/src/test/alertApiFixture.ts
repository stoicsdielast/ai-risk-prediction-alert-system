import { vi } from 'vitest'
import type { AdminAlert } from '../types/alert'
import type { User } from '../types/auth'

export const sampleAdmin: User = {
  id: 7,
  name: 'Test MET administrator',
  email: 'admin@example.test',
  role: 'MET_ADMIN',
  status: 'APPROVED',
}

export function sampleAlert(overrides: Partial<AdminAlert> = {}): AdminAlert {
  return {
    id: 41,
    location_id: 1,
    location: { id: 1, name: 'Suva', is_active: true },
    prediction_id: null,
    severity: 'HIGH',
    status: 'PENDING',
    source: 'MET_OFFICIAL',
    message: 'TEST ONLY: Move to higher ground.',
    created_at: '2026-10-14T00:00:00Z',
    approved_at: null,
    updated_at: null,
    rejected_at: null,
    suppressed_at: null,
    suppression_reason: null,
    ...overrides,
  }
}

/** In-memory API fixtures; sample alerts never reach the real database. */
export function installAlertApi(initial: AdminAlert[] = [sampleAlert()]) {
  const state = {
    alerts: structuredClone(initial),
    user: { ...sampleAdmin },
    failure: null as null | { path: string; method?: string; status: number; detail: string },
  }
  const fetchMock = vi.fn(async (input: RequestInfo | URL, options?: RequestInit) => {
    const url = new URL(String(input))
    const method = options?.method ?? 'GET'
    const json = (body: unknown, status = 200) =>
      new Response(JSON.stringify(body), {
        status,
        headers: { 'Content-Type': 'application/json' },
      })
    if (
      state.failure?.path === url.pathname &&
      (!state.failure.method || state.failure.method === method)
    ) {
      const failure = state.failure
      state.failure = null
      return json({ detail: failure.detail }, failure.status)
    }
    if (url.pathname === '/api/auth/me') return json(state.user)
    if (url.pathname === '/api/locations')
      return json([
        {
          id: 1,
          slug: 'suva',
          name: 'Suva',
          division: 'CENTRAL',
          division_label: 'Central Division',
          latitude: -18.14,
          longitude: 178.44,
          prediction: null,
        },
      ])
    if (url.pathname === '/api/alerts/active') {
      const offset = Number(url.searchParams.get('offset'))
      return json(
        state.alerts
          .filter((alert) => alert.status === 'APPROVED' && alert.location.is_active)
          .slice(offset, offset + 200),
      )
    }
    if (url.pathname === '/api/admin/alerts' && method === 'GET') {
      const offset = Number(url.searchParams.get('offset'))
      return json(
        state.alerts
          .filter((alert) => alert.status === url.searchParams.get('status'))
          .slice(offset, offset + 200),
      )
    }
    const body = options?.body ? JSON.parse(String(options.body)) : {}
    if (url.pathname === '/api/admin/alerts' && method === 'POST') {
      const alert = sampleAlert({
        ...body,
        id: Math.max(40, ...state.alerts.map((item) => item.id)) + 1,
      })
      state.alerts.unshift(alert)
      return json(alert, 201)
    }
    const match = url.pathname.match(
      /^\/api\/admin\/alerts\/(\d+)(?:\/(approve|reject|suppress))?$/,
    )
    if (match && method === 'PATCH') {
      const alert = state.alerts.find((item) => item.id === Number(match[1]))
      if (!alert) return json({ detail: 'Alert not found' }, 404)
      Object.assign(alert, body)
      if (match[2] === 'approve')
        Object.assign(alert, { status: 'APPROVED', approved_at: '2026-10-14T01:00:00Z' })
      if (match[2] === 'reject')
        Object.assign(alert, { status: 'REJECTED', rejected_at: '2026-10-14T01:00:00Z' })
      if (match[2] === 'suppress')
        Object.assign(alert, {
          status: 'SUPPRESSED',
          suppression_reason: body.reason,
          suppressed_at: '2026-10-14T01:00:00Z',
        })
      if (!match[2]) alert.updated_at = '2026-10-14T01:00:00Z'
      return json(alert)
    }
    throw new Error(`Unexpected fixture request: ${method} ${url.pathname}`)
  })
  vi.stubGlobal('fetch', fetchMock)
  return { state, fetchMock }
}
