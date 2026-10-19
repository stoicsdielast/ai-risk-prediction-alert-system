import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { PublicAlertProvider } from '../../alerts/PublicAlertProvider'
import { ALERT_REFRESH_MS } from '../../alerts/useAlertFeed'
import { CommunityAlertsPage } from '../../pages/CommunityAlertsPage'
import { installAlertApi, sampleAlert } from '../../test/alertApiFixture'
import { BrowserAlertControl } from './BrowserAlertControl'

class TestNotification {
  static permission: NotificationPermission = 'default'
  static requestPermission = vi.fn(async (): Promise<NotificationPermission> => {
    TestNotification.permission = 'granted'
    return 'granted'
  })
  static instances: TestNotification[] = []
  onclick: (() => void) | null = null
  onerror: (() => void) | null = null
  close = vi.fn()
  title: string
  options: NotificationOptions
  constructor(title: string, options: NotificationOptions) {
    this.title = title
    this.options = options
    TestNotification.instances.push(this)
  }
}
function LocationProbe() {
  const location = useLocation()
  return <output data-testid="route">{location.pathname}{location.hash}</output>
}
function renderControls() {
  return render(<MemoryRouter><PublicAlertProvider>
    <BrowserAlertControl /><CommunityAlertsPage /><LocationProbe />
  </PublicAlertProvider></MemoryRouter>)
}
beforeEach(() => {
  localStorage.clear()
  TestNotification.instances = []
  TestNotification.permission = 'default'
  TestNotification.requestPermission.mockClear()
  vi.stubGlobal('Notification', TestNotification)
  vi.stubGlobal('isSecureContext', true)
})
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.unstubAllEnvs() })

it('asks for permission only on a click and shows the granted status', async () => {
  installAlertApi([])
  renderControls()
  await screen.findByText('No active alerts')
  expect(TestNotification.requestPermission).not.toHaveBeenCalled()
  await userEvent.click(screen.getByRole('button', { name: 'Enable Browser Alerts' }))
  expect(TestNotification.requestPermission).toHaveBeenCalledTimes(1)
  expect(screen.getByText('✓ Browser alerts enabled')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Test Browser Notification' }))
  expect(TestNotification.instances[0].title).toBe('Flood Alert Test')
})

it('explains denied permission without repeatedly requesting it', async () => {
  TestNotification.permission = 'denied'
  installAlertApi([])
  renderControls()
  expect(screen.getByText(/permission was denied/)).toBeInTheDocument()
  await screen.findByText('No active alerts')
  expect(screen.queryByRole('button', { name: 'Enable Browser Alerts' })).not.toBeInTheDocument()
  expect(TestNotification.requestPermission).not.toHaveBeenCalled()
})

it('handles permission rejection without crashing the website', async () => {
  TestNotification.requestPermission.mockRejectedValueOnce(new Error('blocked'))
  installAlertApi([])
  renderControls()
  await userEvent.click(screen.getByRole('button', { name: 'Enable Browser Alerts' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('could not request permission')
  expect(screen.getByRole('button', { name: 'Enable Browser Alerts' })).toBeEnabled()
})

it('keeps website alerts usable in an unsupported browser', async () => {
  vi.stubGlobal('Notification', undefined)
  installAlertApi([sampleAlert({ status: 'APPROVED' })])
  renderControls()
  expect(screen.getByText(/does not support desktop notifications/)).toBeInTheDocument()
  expect(await screen.findByRole('heading', { name: 'Suva' })).toBeInTheDocument()
})

it('polls once for both UI and notifications, observes approval in a background tab, deduplicates and navigates on click', async () => {
  vi.useFakeTimers()
  TestNotification.permission = 'granted'
  vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden')
  vi.spyOn(window, 'focus').mockImplementation(() => {})
  const { state, fetchMock } = installAlertApi([sampleAlert()])
  const view = renderControls()
  await act(async () => {})
  expect(fetchMock).toHaveBeenCalledTimes(1)
  expect(TestNotification.instances).toHaveLength(0)
  state.alerts[0].status = 'APPROVED'
  state.alerts[0].approved_at = '2026-10-14T01:00:00Z'
  await act(async () => { await vi.advanceTimersByTimeAsync(ALERT_REFRESH_MS) })
  expect(screen.getByRole('heading', { name: 'Suva' })).toBeInTheDocument()
  expect(TestNotification.instances).toHaveLength(1)
  expect(fetchMock).toHaveBeenCalledTimes(2)
  await act(async () => { await vi.advanceTimersByTimeAsync(ALERT_REFRESH_MS) })
  expect(TestNotification.instances).toHaveLength(1)
  act(() => TestNotification.instances[0].onclick!())
  expect(screen.getByTestId('route')).toHaveTextContent('/alerts#alert-41')
  view.unmount()
  await act(async () => { await vi.advanceTimersByTimeAsync(ALERT_REFRESH_MS) })
  expect(fetchMock).toHaveBeenCalledTimes(3)
})

it('does not notify from stale data after a backend failure and recovers', async () => {
  vi.useFakeTimers()
  TestNotification.permission = 'granted'
  const { state } = installAlertApi([])
  renderControls()
  await act(async () => {})
  state.alerts.push(sampleAlert({ status: 'APPROVED' }))
  state.failure = { path: '/api/alerts/active', status: 500, detail: 'Unavailable' }
  await act(async () => { await vi.advanceTimersByTimeAsync(ALERT_REFRESH_MS) })
  expect(screen.getByRole('alert')).toHaveTextContent('Unavailable')
  expect(TestNotification.instances).toHaveLength(0)
  await act(async () => { await vi.advanceTimersByTimeAsync(ALERT_REFRESH_MS) })
  expect(TestNotification.instances).toHaveLength(1)
})

it('observes permissions changed in browser settings and hides the test button in production', async () => {
  vi.stubEnv('DEV', false)
  installAlertApi([])
  renderControls()
  await screen.findByText('No active alerts')
  TestNotification.permission = 'granted'
  fireEvent.focus(window)
  expect(screen.getByText('✓ Browser alerts enabled')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Test Browser Notification' })).not.toBeInTheDocument()
})
