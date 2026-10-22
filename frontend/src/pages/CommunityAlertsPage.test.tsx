import { act, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { ALERT_REFRESH_MS } from '../alerts/useAlertFeed'
import { installAlertApi, sampleAlert } from '../test/alertApiFixture'
import { CommunityAlertsPage } from './CommunityAlertsPage'
import { PublicAlertProvider } from '../alerts/PublicAlertProvider'

function renderPage() {
  return render(<PublicAlertProvider><CommunityAlertsPage /></PublicAlertProvider>)
}

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

it('shows severity, location, message and timestamps without management controls', async () => {
  const { fetchMock } = installAlertApi([
    sampleAlert({ status: 'APPROVED', approved_at: '2026-10-14T01:00:00Z' }),
  ])
  renderPage()
  expect(await screen.findByRole('heading', { name: 'Suva' })).toBeInTheDocument()
  expect(screen.getByText('High')).toBeInTheDocument()
  expect(screen.getByText('TEST ONLY: Move to higher ground.')).toBeInTheDocument()
  expect(document.querySelector('time[datetime="2026-10-14T01:00:00Z"]')).toBeInTheDocument()
  expect(document.querySelector('time[datetime="2026-10-14T00:00:00Z"]')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument()
  expect(new Headers(fetchMock.mock.calls[0][1]?.headers).has('Authorization')).toBe(false)
})

it('automatically removes withdrawn alerts and stops polling on unmount', async () => {
  vi.useFakeTimers()
  const { state, fetchMock } = installAlertApi([
    sampleAlert({ status: 'APPROVED', approved_at: '2026-10-14T01:00:00Z' }),
  ])
  const view = renderPage()
  await act(async () => {})
  expect(screen.getByRole('heading', { name: 'Suva' })).toBeInTheDocument()
  state.alerts[0].status = 'SUPPRESSED'
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ALERT_REFRESH_MS)
  })
  expect(screen.getByRole('heading', { name: 'No active alerts' })).toBeInTheDocument()
  expect(screen.queryByText('TEST ONLY: Move to higher ground.')).not.toBeInTheDocument()
  view.unmount()
  const requests = fetchMock.mock.calls.length
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ALERT_REFRESH_MS * 2)
  })
  expect(fetchMock).toHaveBeenCalledTimes(requests)
})

it('marks stale alerts when refresh fails and recovers on the next refresh', async () => {
  vi.useFakeTimers()
  const { state } = installAlertApi([
    sampleAlert({ status: 'APPROVED', approved_at: '2026-10-14T01:00:00Z' }),
  ])
  renderPage()
  await act(async () => {})
  state.failure = { path: '/api/alerts/active', status: 500, detail: 'Test-only service outage' }
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ALERT_REFRESH_MS)
  })
  expect(screen.getByRole('alert')).toHaveTextContent('Displayed alerts may be out of date')
  expect(screen.getByRole('heading', { name: 'Suva' })).toBeInTheDocument()
  expect(screen.queryByText('No active alerts')).not.toBeInTheDocument()
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ALERT_REFRESH_MS)
  })
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

it('shows a network failure without pretending there are no alerts', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
  renderPage()
  expect(await screen.findByRole('alert')).toHaveTextContent('Cannot reach the server')
  expect(screen.queryByText('No active alerts')).not.toBeInTheDocument()
})
