import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { PublicAlertProvider } from '../../alerts/PublicAlertProvider'
import { ALERT_REFRESH_MS } from '../../alerts/useAlertFeed'
import { createAlert, reviewAlert } from '../../api/alerts'
import { installAlertApi, sampleAdmin } from '../../test/alertApiFixture'
import { InAppAlerts } from './InAppAlerts'

vi.mock('../../auth/useAuth', () => {
  const user = { id: 99, name: 'Local community fixture', email: 'community@example.test', role: 'COMMUNITY', status: 'APPROVED' }
  return { useAuth: () => ({ user, token: 'community-fixture-token' }) }
})

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); localStorage.clear() })

it('synchronizes an isolated administrator demo approval to a saved-location community banner through polling', async () => {
  vi.useFakeTimers()
  localStorage.clear()
  vi.stubGlobal('Notification', undefined)
  const fixture = installAlertApi([])
  const backend = globalThis.fetch
  const fetchMock = vi.fn((input: RequestInfo | URL, options?: RequestInit) => {
    if (new URL(String(input)).pathname === '/api/me/subscriptions') {
      expect(new Headers(options?.headers).get('Authorization')).toBe('Bearer community-fixture-token')
      return Promise.resolve(new Response(JSON.stringify([{ id: 1, name: 'Suva', is_active: true }]), { headers: { 'Content-Type': 'application/json' } }))
    }
    return backend(input, options)
  })
  vi.stubGlobal('fetch', fetchMock)
  const view = render(<MemoryRouter><PublicAlertProvider><InAppAlerts />
    <Routes><Route path="/alerts" element={<article id="alert-41"><h1>Selected community alert</h1></article>} /><Route path="*" element={null} /></Routes>
  </PublicAlertProvider></MemoryRouter>)
  await act(async () => {})
  expect(screen.getByText('0 unread')).toBeInTheDocument()

  const pending = await createAlert('admin-fixture-token', { location_id: 1, severity: 'HIGH', message: 'TEST ONLY — Local isolated simulated alert, not an emergency warning.' })
  // All writes are to this test's in-memory fixture; this marks the record as demo.
  fixture.state.alerts.find(alert => alert.id === pending.id)!.is_demo = true
  expect(fixture.state.user.id).toBe(sampleAdmin.id)
  await act(async () => { await vi.advanceTimersByTimeAsync(ALERT_REFRESH_MS) })
  expect(screen.queryByLabelText('New simulated alert for Suva')).not.toBeInTheDocument()
  await reviewAlert('admin-fixture-token', pending.id, 'approve')
  await act(async () => { await vi.advanceTimersByTimeAsync(ALERT_REFRESH_MS) })
  const notice = screen.getByLabelText('New simulated alert for Suva')
  expect(within(notice).getByText(/Not an emergency warning/)).toBeInTheDocument()
  expect(within(notice).getByText('High')).toBeInTheDocument()
  expect(screen.getByText('1 unread')).toBeInTheDocument()
  await act(async () => { await vi.advanceTimersByTimeAsync(ALERT_REFRESH_MS) })
  expect(screen.getAllByLabelText('New simulated alert for Suva')).toHaveLength(1)
  await act(async () => { fireEvent.click(within(screen.getByLabelText('New simulated alert for Suva')).getByRole('link', { name: 'View alert' })) })
  expect(screen.getByRole('heading', { name: 'Selected community alert' })).toBeInTheDocument()
  expect(screen.getByText('0 unread')).toBeInTheDocument()
  expect(fetchMock.mock.calls.some(([input]) => /\/(claim|receipt|check)$/.test(new URL(String(input)).pathname))).toBe(false)
  view.unmount()
  const requests = fetchMock.mock.calls.length
  await act(async () => { await vi.advanceTimersByTimeAsync(ALERT_REFRESH_MS * 2) })
  expect(fetchMock).toHaveBeenCalledTimes(requests)
})
